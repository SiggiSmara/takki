"""The session loop — concurrency-model.md §§ The loop, TTS, Timers, Startup, Shutdown.

Glue, and only glue. Every decision about *what* a component means was taken in
sessions 6b-10 and is not re-taken here; what this module owns is the order
things are called in, and the three lifetimes those calls have:

* one `KeyIntroducer` and one `DrillGenerator` **per session** -- both hold
  session-local state that a fresh instance silently drops (ADR-023 § What the
  introducer remembers, ADR-024 § Where the ramp-up phase lives);
* a fresh `MilestoneDetector` **per check** -- it holds nothing, the stored
  `milestones` rows are the authority, and it costs one rolling-window query
  per Active grapheme, so it is called at a block boundary and never in the
  prompt loop (ADR-027 § Milestone Ladder);
* `AttemptCounter.start_prompt` / `press` **per prompt**, paired one-for-one
  with `DrillGenerator.record_attempt` (ADR-027 § First-Attempt Counting).
"""

import queue
import random
from collections.abc import Callable
from dataclasses import dataclass

from takki import config
from takki.audio.cues import SoundCuePlayer
from takki.audio.letters import LetterAudioSource
from takki.audio.tts_worker import SpeechFinished, TTSWorker
from takki.clock import Clock, FrameLimiter
from takki.display.focus import FocusEvent, FocusSource
from takki.events import Quit
from takki.focus_model import (
    FocusModel,
    FocusState,
    LessonCommand,
    RereadPrompt,
    RestartWord,
    TypedCharacter,
)
from takki.input import KeyEvent, KeyEventStream
from takki.input.taxonomy import KeyBindings
from takki.language import WordSource, warm
from takki.lesson.attempts import AttemptCounter, PressOutcome
from takki.lesson.drills import DrillBlock, DrillGenerator
from takki.lesson.introducer import (
    DEFAULT_STRATEGY,
    IntroductionStep,
    IntroductionStrategy,
    KeyIntroducer,
    describe,
)
from takki.lesson.key_state import KeyStates
from takki.lesson.milestones import MilestoneDetector
from takki.lesson.progression import layer_two_unlocked, ready_for_new_key
from takki.persistence import Store
from takki.platform.layout import Layout
from takki.speech import Speaker

InboundEvent = KeyEvent | FocusEvent | SpeechFinished | Quit

# A rung slug in, the line to speak out, or None to say nothing. Alpha says
# nothing: the slug is an identifier and never spoken, and the spoken name
# resolves through ADR-022's per-language YAML tier, which does not exist yet
# (ADR-027 § Milestone Ladder). What this seam pins down is the loop's own
# half of the problem -- when a celebration happens and in what order -- so
# that the tier, when it lands, has nothing left to decide about sequencing.
Celebrant = Callable[[str], str | None]


@dataclass(frozen=True)
class _Block:
    prompts: tuple[str, ...]
    # For each prompt, the index of the first prompt of the unit it belongs to.
    # Layer 1's answer to ADR-012's restart key, which abandons "the current
    # word": the nearest thing to a word here is ADR-024's unit, and a block
    # always ends on one (§ Block boundaries).
    unit_start: tuple[int, ...]


def _to_block(block: DrillBlock) -> _Block:
    starts: list[int] = []
    index = 0
    for unit in block.units:
        starts.extend([index] * len(unit))
        index += len(unit)
    return _Block(block.prompts, tuple(starts))


class SessionLoop:
    def __init__(
        self,
        *,
        inbound: queue.Queue[InboundEvent],
        layout: Layout,
        source: WordSource,
        store: Store,
        profile_id: int,
        clock: Clock,
        frames: FrameLimiter,
        focus: FocusSource,
        keys: KeyEventStream,
        speech: TTSWorker,
        letters: LetterAudioSource,
        cues: SoundCuePlayer,
        rng: random.Random,
        bindings: KeyBindings | None = None,
        strategy: IntroductionStrategy = DEFAULT_STRATEGY,
        celebrant: Celebrant | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._inbound = inbound
        self._layout = layout
        self._source = source
        self._store = store
        self._profile_id = profile_id
        self._clock = clock
        self._frames = frames
        self._focus = focus
        self._keys = keys
        self._speech = speech
        self._cues = cues
        self._rng = rng
        self._strategy = strategy
        self._celebrant = celebrant
        self._now = now
        self._states = KeyStates(store, profile_id)
        self._attempts = AttemptCounter(store, profile_id, now)
        self._speaker = Speaker(speech, letters)
        # The gate speaks through the same Speaker the loop does: one object
        # knows what is audible, so the loop can hold a prompt behind a pause
        # or resume announcement instead of speaking over it.
        self._focus_model = FocusModel(focus, self._speaker, clock, bindings)

        self.running = False
        # No consumer in Alpha -- Layer 2 does not exist. Evaluated and held
        # anyway because the block boundary is where ADR-010 says the check
        # belongs ("checked after each introduction step"), and a predicate
        # nobody calls is a predicate nobody notices has stopped working.
        self.layer_two_unlocked = False
        self._session_id: int | None = None
        self._introducer: KeyIntroducer | None = None
        self._drills: DrillGenerator | None = None
        self._block = _Block((), ())
        self._index = 0
        self._prompt: str | None = None
        self._first_press = False
        self._prompt_due = False
        self._reprompt_due = False
        self._prompt_deadline: float | None = None
        self._reprompts = 0
        # True from the moment an introduction script starts speaking until the
        # prompt it precedes opens. The one thing a resume needs to know that
        # the prompt state cannot tell it: with no prompt open, "a script was
        # cut" and "a celebration was playing" look identical, and only the
        # first should be re-spoken (ADR-012 § Recovery).
        self._script_in_flight = False

    @property
    def prompt(self) -> str | None:
        """The grapheme the child is being asked for, or None when none is open."""
        return self._prompt

    # ---- startup and shutdown -----------------------------------------

    def start(self) -> None:
        """concurrency-model.md § Startup — everything expensive, before the loop.

        The caller has already created the window and the mixer, in that order,
        so by the time this runs the focus anchor exists and a cue can be
        played. What is left is the language layer's derived tables, which are
        a full corpus pass and are read from inside the loop, and the two
        session-lifetime objects that read them.
        """
        warm(self._source, self._layout)
        self._session_id = self._store.start_session(self._profile_id)
        self._introducer = KeyIntroducer(self._layout, self._source, self._states, self._strategy)
        self._drills = DrillGenerator(
            self._layout, self._source, self._states, self._clock, self._rng
        )
        self._keys.start()
        self.running = True
        # The first spoken line of the session comes out of here: a cold
        # profile's first block boundary introduces Stage 0's first step, and
        # its script is what the child hears. Nothing before this point speaks.
        self._begin_block()

    def stop(self) -> None:
        """Signal-handler entry point (concurrency-model.md § Shutdown)."""
        self.running = False

    def shutdown(self) -> None:
        if self._session_id is not None:
            self._store.end_session(self._session_id)
            self._session_id = None
        self._speech.enqueue_shutdown()
        self._keys.stop()
        self._speech.join(config.WORKER_JOIN_SECONDS)
        self._focus.close()

    # ---- the loop ------------------------------------------------------

    def run(self) -> None:
        while self.running:
            self.tick()
        self.shutdown()

    def tick(self) -> None:
        self._focus.poll()
        while True:
            try:
                event = self._inbound.get_nowait()
            except queue.Empty:
                break
            self._dispatch(event)
        self._check_deadlines()
        self._advance()
        self._frames.wait()

    def _dispatch(self, event: InboundEvent) -> None:
        if isinstance(event, Quit):
            self.running = False
            return
        if isinstance(event, SpeechFinished):
            self._speaker.on_finished(event)
        else:
            paused = self._focus_model.state is FocusState.PAUSED
            self._run(self._focus_model.handle(event))
            if paused and self._focus_model.state is FocusState.ACTIVE:
                self._on_resume()
            elif not paused and self._focus_model.state is FocusState.PAUSED:
                self._on_pause()
        # Here, not only at the end of tick(): a child typing ahead can have
        # two key events in one drain, and the second must find the next prompt
        # already open. This is what closes roadmap § D's "keystrokes typed
        # between prompts are dropped" window inside a block.
        self._advance()

    def _check_deadlines(self) -> None:
        self._run(self._focus_model.check_deadlines())
        if self._focus_model.state is FocusState.PAUSED:
            # A child who is not in Takki is not ignoring the prompt.
            return
        now = self._clock.monotonic()
        if self._prompt_deadline is not None and now >= self._prompt_deadline:
            self._on_timeout()

    def _advance(self) -> None:
        """Issue what is owed, once the child would actually hear it.

        Held while anything is speaking, so a letter never lands on top of an
        introduction script, a celebration or a resume announcement. ADR-012
        § TTS utterance sequencing asked what becomes of a prompt that falls
        due while a non-interruptible utterance is speaking, and this is the
        answer it now records: held -- not dropped, and not spoken over. The
        same rule covers the interruptible cases, so there is one behaviour to
        reason about rather than two.
        """
        if self._speaker.busy or self._focus_model.state is FocusState.PAUSED:
            # Nothing is issued at a child who is not in Takki: what is owed
            # waits for the resume, which is what re-speaks it.
            return
        if self._prompt_due:
            self._prompt_due = False
            self._reprompt_due = False
            self._start_prompt()
        elif self._reprompt_due:
            self._reprompt_due = False
            self._speak_prompt()

    # ---- prompts -------------------------------------------------------

    def _start_prompt(self) -> None:
        # The script has served its purpose the moment its prompt is audible.
        # `_advance` holds the prompt until the speaker is idle, so this clears
        # exactly when the script finished rather than when it was queued.
        self._script_in_flight = False
        target = self._block.prompts[self._index]
        self._prompt = target
        self._first_press = True
        self._reprompts = 0
        self._attempts.start_prompt(target)
        self._speak_prompt()

    def _speak_introduction(self, step: IntroductionStep) -> None:
        """Speak a step's script and mark it in flight until its prompt opens."""
        self._script_in_flight = True
        self._speaker.say(*(describe(intro) for intro in step.keys))

    def _speak_prompt(self) -> None:
        """Re-speak the open prompt, without touching its identity.

        Deliberately not `start_prompt`: re-latching would let the child's next
        keystroke count as a second first attempt (ADR-027 § Timeouts). Every
        route that re-speaks -- the re-read key, the auto-advance timeout, an
        auto-rejected keypress, and the return from PAUSED -- comes through
        here, so there is exactly one place for that to be got wrong.
        """
        assert self._prompt is not None
        self._speaker.letter(self._prompt)
        self._prompt_deadline = self._clock.monotonic() + config.PROMPT_TIMEOUT_SECONDS

    def _on_timeout(self) -> None:
        """Carry-forward "D auto-advance": a Layer-1 timeout re-prompts.

        Advancing would abandon the open prompt and put a different letter in
        front of a child who was still thinking about this one, with no signal
        that it happened -- against ADR-012's auto-reject model, whose point is
        that the child is always at a known position. Re-prompting keeps the
        position; it is bounded so a child who has walked away eventually gets
        silence rather than the same letter forever. The prompt stays open
        through the silence, so their first keystroke on returning is still a
        first attempt.
        """
        self._prompt_deadline = None
        if self._reprompts >= config.PROMPT_MAX_REPROMPTS:
            return
        self._reprompts += 1
        self._reprompt_due = True

    def _on_pause(self) -> None:
        # The deadline is disarmed rather than merely skipped: monotonic time
        # runs through a PAUSED interval, so a deadline left armed is already
        # in the past on the way back and would spend a re-prompt the child
        # never sat through. Re-armed by the resume's own re-prompt.
        self._prompt_deadline = None

    def _on_resume(self) -> None:
        """Carry-forward "D resume re-read": returning from PAUSED re-issues the prompt.

        ADR-012 § Recovery: a child who task-switched away mid-drill otherwise
        comes back to the resume announcement and silence, which is exactly the
        disoriented state the re-read key exists to serve. Queued rather than
        spoken now -- `_advance` holds it until the announcement finishes.
        """
        if self._prompt is not None:
            # A child who has come back is engaging again, so the budget they
            # spent before leaving is not held against them.
            self._reprompts = 0
            self._reprompt_due = True
        elif self._script_in_flight and self._introducer is not None:
            # An introduction script was cut by the focus loss. Re-speak it
            # **whole**, not from where it stopped: the child task-switched
            # away and lost the context, and a script resuming mid-sentence
            # teaches less than one heard again. Held, not dropped -- the same
            # rule `_advance` applies to prompts. Without this the remainder is
            # unrecoverable: `_on_reread` only reaches the script while no
            # prompt is open, and the prompt opens moments later.
            step = self._introducer.last_step
            if step is not None:
                self._speak_introduction(step)

    # ---- commands ------------------------------------------------------

    def _run(self, command: LessonCommand | None) -> None:
        if isinstance(command, TypedCharacter):
            self._on_character(command)
        elif isinstance(command, RereadPrompt):
            self._on_reread()
        elif isinstance(command, RestartWord):
            self._on_restart()

    def _on_character(self, typed: TypedCharacter) -> None:
        assert self._drills is not None
        target = self._prompt
        if target is None:
            # Nothing open to answer: a restart or a block boundary abandoned
            # the prompt and its replacement is held behind speech. The counter
            # is deliberately not asked -- it still holds the abandoned target
            # until `_start_prompt` re-latches, and this loop is the one place
            # that knows the prompt is gone. Type-ahead here writes nothing and
            # gets no feedback (roadmap § D).
            return
        outcome = self._attempts.press(typed.char, repeat=typed.repeat)
        if outcome is PressOutcome.IGNORED:
            # An auto-repeat of a key that never came up (ADR-027 § Held keys).
            return
        # ADR-012 § TTS interrupt on keypress -- and only for a press that
        # answers a prompt. Interrupting ahead of the two guards above would
        # let a type-ahead keystroke, or the auto-repeat of the key that just
        # ended a block, cut the introduction script for a letter the child has
        # not been told about yet, and then do nothing else.
        self._speaker.interrupt()
        if self._first_press:
            # Once per prompt, with the first press's outcome, paired
            # one-for-one with the counter's own write. A retry press must not
            # reach here or Phase C stops measuring first-attempt accuracy.
            self._first_press = False
            self._drills.record_attempt(target, outcome is PressOutcome.CORRECT)
        self._reprompts = 0
        self._cues.play("correct" if outcome is PressOutcome.CORRECT else "error")
        if outcome is PressOutcome.WRONG:
            # ADR-012 § Wrong character handling: auto-rejected, and the same
            # character is re-prompted. The prompt stays open and stays the
            # same prompt.
            self._reprompt_due = True
            return
        self._prompt = None
        self._prompt_deadline = None
        self._index += 1
        if self._index < len(self._block.prompts):
            self._prompt_due = True
        else:
            self._begin_block()

    def _on_reread(self) -> None:
        if self._prompt is not None:
            self._reprompt_due = True
            return
        # Nothing open -- between blocks, or an introduction script is still
        # speaking. ADR-023 § What an introduction step is: the re-read key is
        # how the child re-hears that script.
        assert self._introducer is not None
        step = self._introducer.last_step
        if step is not None:
            self._speak_introduction(step)

    def _on_restart(self) -> None:
        """ADR-012 § Recovery, in Layer 1: re-present the current unit.

        There is no word here to abandon; ADR-024's unit is the nearest thing,
        and a block always ends on one. The re-typed prompts are counted again,
        because each is a fresh prompt and ADR-027 counts prompts -- ADR-012's
        "the word is not counted toward session totals" has no Layer-1
        mechanism behind it and no schema to hold one.
        """
        if self._index >= len(self._block.prompts):
            return
        self._index = self._block.unit_start[self._index]
        self._prompt = None
        self._prompt_deadline = None
        self._prompt_due = True

    # ---- the block boundary --------------------------------------------

    def _begin_block(self) -> None:
        """The loop's block-boundary work, in the order a later reader needs.

        1. **Milestones.** A celebration is about what the child has just
           finished, so it is spoken before they are told about a new letter --
           and before the new letter changes the Active set underneath it.
        2. **Introduction.** Two gates, both required: ADR-024's ramp-up must
           have ended (`ramp_up is None`, the drill generator's call, not this
           module's) *and* ADR-010's `ready_for_new_key` must hold. Nothing
           gates it on the anchor rung -- see the note below.
        3. **Layer-2 unlock.** After the introduction, because the introduction
           is what changes the Active set it counts; reading it first would
           report a set one step stale.
        4. **The block.** Last, because its content depends on the ramp-up
           step 2 may just have started.

        **The curriculum does not wait for the anchor gate** (roadmap § D,
        "Does the curriculum wait for the anchor gate?"). Stage 0 is a strong
        opening, not a barrier: the gate needs two calendar days
        (`KNOWN_MIN_DISTINCT_DAYS`), so gating `introduce_next` on the rung
        would mean no child can leave six keys on their first day. The price is
        the one session 10 already priced -- a rung that can fire late and
        after `third`.
        """
        assert self._drills is not None
        self._celebrate(self._milestones().check())
        self._introduce()
        self.layer_two_unlocked = layer_two_unlocked(self._layout, self._states)
        self._block = _to_block(self._drills.next_block())
        self._index = 0
        self._prompt = None
        self._prompt_deadline = None
        self._prompt_due = bool(self._block.prompts)
        if not self._block.prompts:
            # Nothing left to introduce and nothing Active to drill. Reachable
            # only from an empty curriculum; without it the loop would spin
            # forever issuing no prompts.
            self.running = False

    def _milestones(self) -> MilestoneDetector:
        # Fresh per check: it holds no state, and the persisted rows are the
        # authority on what has already fired (ADR-027 § Milestone Ladder).
        return MilestoneDetector(
            self._store, self._profile_id, self._layout, self._states, self._now
        )

    def _celebrate(self, rungs: tuple[str, ...]) -> None:
        """Every rung earned since the last check, in ladder order, in one boundary.

        `check()` can hand back more than one at once, and a late anchor rung
        can arrive after `third` (ADR-027 § The Anchor Gate). They are spoken
        as consecutive non-interruptible utterances in a single sequence, so
        the speaker spaces them by each other's duration and none overlaps.
        None is held over to a later boundary: a deferred rung is one the child
        earned and never heard about, and there is no row to remember the debt.
        """
        if self._celebrant is None:
            return
        lines = [line for rung in rungs if (line := self._celebrant(rung)) is not None]
        if lines:
            self._speaker.say(*lines, interruptible=False)

    def _introduce(self) -> None:
        assert self._drills is not None and self._introducer is not None
        if self._drills.ramp_up is not None:
            return
        if not ready_for_new_key(self._layout, self._states):
            return
        step = self._introducer.introduce_next()
        if step is None:
            return
        self._drills.begin_step(step)
        self._speak_introduction(step)
