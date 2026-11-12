"""ADR-024 — Layer 1 drill content and lesson granularity.

The ramp-up's ladder after an introduction step (Reach, Choose, Travel),
general-practice blocks planned by each key's need, and blocks sized by the
child's own pace. No audio and no timers; the ladder's records are written by
`StepLadder`.
"""

import math
import random
from collections import deque
from collections.abc import Callable
from collections.abc import Set as AbstractSet
from fractions import Fraction

from takki import config
from takki.clock import Clock
from takki.language import WordSource
from takki.lesson.introducer import IntroductionStep, Rest, home_anchor_keys
from takki.lesson.key_state import Evidence, KeyStates, accuracy_bound
from takki.lesson.prompts import Prompt, PromptKind
from takki.lesson.rampup import StepLadder
from takki.persistence import Level, Store
from takki.platform.layout import Layout, PhysicalKey

# A unit is one bigram or short sequence, and each of its members is one prompt
# (ADR-027 § First-Attempt Counting: one attempt per prompt). A composite is a
# single prompt carrying two keystrokes, so a block's prompt count and its
# keystroke count are not the same number -- see the ADR-024 amendment.
Unit = tuple[str, ...]

# ADR-024 § Steady-state drill generation (alpha-plan #12e). Constants in code
# rather than config on the developer's call: they are tuning knobs for whoever
# works on the engine, not settings a parent should meet.
#
# The most of one block any single key may be planned for, so a struggling key
# cannot turn a block into a one-letter drill. A Fraction so that "a third of 15
# slots" is 5 and not 4.999...
MAX_KEY_SHARE = Fraction(1, 3)


def presses_needed(evidence: Evidence, bar: float) -> int:
    """A key's need in presses: the larger of its Known-floor gap and its accuracy shortfall."""
    # One number in the unit the plan hands out, so a key short on both is not
    # queued behind either reason. The floor is the dose and counts presses as
    # they happened; the shortfall reads evidence that ages (ADR-027).
    gap = max(0, config.KNOWN_MIN_ATTEMPTS - evidence.attempts)
    return max(gap, _presses_to_confirm(evidence.correct, evidence.weight, bar))


def _presses_to_confirm(correct: float, attempts: float, bar: float) -> int:
    # The window's own forgetting is ignored -- old misses dropping out would
    # make it sooner -- so this over-estimates a struggling key's need, which
    # MAX_KEY_SHARE absorbs. The bound rises with every correct press and tends
    # to 1, so for any bar below 1 the doubling search ends.
    def confirmed(extra: int) -> bool:
        return accuracy_bound(correct + extra, attempts + extra) >= bar

    if confirmed(0):
        return 0
    low, high = 0, 1
    while not confirmed(high):
        low, high = high, high * 2
    while high - low > 1:
        middle = (low + high) // 2
        low, high = (low, middle) if confirmed(middle) else (middle, high)
    return high


def plan_targets(needs: dict[str, int], slots: int, rng: random.Random) -> dict[str, int]:
    """How many of a block's slots each key is the target of."""
    # Shared by need, never beyond a key's need or the cap; slots nobody needs
    # go round the keys evenly. The cap never falls below an even share, or a
    # two-key set could not fill its block.
    counts = dict.fromkeys(sorted(needs), 0)
    if not counts or slots <= 0:
        return counts
    cap = max(1, math.floor(slots * MAX_KEY_SHARE), -(-slots // len(counts)))
    # One slot each first, neediest first, so every key in need moves forward
    # every block. D'Hondt alone does not promise that: a key one press from
    # Known loses every slot to keys that need dozens, and that one press is
    # what frees its slot for the next letter (ADR-010).
    served = sorted((name for name in counts if needs[name] > 0), key=lambda n: -needs[n])[:slots]
    for name in served:
        counts[name] = 1
    for _ in range(slots - len(served)):
        # D'Hondt: the next slot goes to the most need per slot already given.
        # `max` keeps the first of a tie, and `counts` is in name order.
        eligible = [name for name in counts if counts[name] < min(cap, needs[name])]
        if not eligible:
            break
        best = max(eligible, key=lambda name: needs[name] / (counts[name] + 1))
        counts[best] += 1
    spare = slots - sum(counts.values())
    while spare and (room := [name for name in counts if counts[name] < cap]):
        rng.shuffle(room)
        for name in room[:spare]:
            counts[name] += 1
        spare -= min(spare, len(room))
    return counts


class Block:
    """What the session loop works through between two block boundaries."""

    def current(self) -> Prompt | None:
        """The prompt to open, or None once the block is done."""
        raise NotImplementedError

    def close(self) -> None:
        """The open prompt has been answered; the next `current` moves on."""
        raise NotImplementedError

    def restart(self, heard: bool) -> None:
        """The restart key: the current unit is presented again (ADR-012 § Recovery).

        `heard` is whether a prompt is open, that is, has been spoken to the
        child; a prompt drawn and still held behind speech has not been.
        """
        raise NotImplementedError


class DrillBlock(Block):
    """A block planned whole: general practice, a sequence of counted units."""

    def __init__(self, units: tuple[Unit, ...]) -> None:
        self.units = units
        self._index = 0
        # For each prompt, the index of the first prompt of its unit: Layer 1's
        # answer to the restart key, which abandons "the current word".
        self._unit_start = tuple(start for start, unit in _starts(units) for _ in unit)

    @property
    def prompts(self) -> tuple[str, ...]:
        return tuple(prompt for unit in self.units for prompt in unit)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DrillBlock) and other.units == self.units

    __hash__ = None  # type: ignore[assignment]

    def current(self) -> Prompt | None:
        prompts = self.prompts
        if self._index >= len(prompts):
            return None
        return Prompt(PromptKind.COUNTED, prompts[self._index])

    def close(self) -> None:
        self._index += 1

    def restart(self, heard: bool) -> None:
        if self._index < len(self._unit_start):
            self._index = self._unit_start[self._index]


def _starts(units: tuple[Unit, ...]) -> list[tuple[int, Unit]]:
    starts: list[tuple[int, Unit]] = []
    index = 0
    for unit in units:
        starts.append((index, unit))
        index += len(unit)
    return starts


class _LadderBlock(Block):
    """A ladder block, drawn prompt by prompt (ADR-024 § Lesson granularity, restated).

    A re-ask depends on the child's answer, so nothing past the open prompt is
    decided in advance. At Reach the block is whole cycles, each member's
    letter and then the rest cue, so it ends with the hand at rest. At Choose
    and Travel it may end after any prompt, but not with a re-ask still owed.
    """

    def __init__(self, generator: "DrillGenerator", level: Level, target: int) -> None:
        self._generator = generator
        self._level = level
        self._target = target
        self._issued = 0
        self._open: Prompt | None = None
        self._cycle: list[Prompt] = []
        self._cycles = generator.reach_cycles(target) if level == "reach" else 0
        self._done = False

    def current(self) -> Prompt | None:
        if self._open is None and not self._done:
            self._open = self._next()
            self._done = self._open is None
        return self._open

    def close(self) -> None:
        self._open = None
        self._issued += 1

    def restart(self, heard: bool) -> None:
        # Only the open prompt is re-presented: at the ladder's levels every
        # prompt is a unit of its own. A drawn letter the child has heard comes
        # back as a re-ask, because they now know what is coming (decided
        # 2026-11-12, #12m session (6)). One drawn and held behind speech has
        # not been heard, and stays a draw: otherwise a restart in that gap
        # would make a listened press uncounted.
        if heard and self._open is not None and self._open.kind is PromptKind.COUNTED:
            self._open = Prompt(PromptKind.REASK, self._open.grapheme)

    def _next(self) -> Prompt | None:
        generator = self._generator
        if self._level == "reach":
            if not self._cycle:
                # The step's level is read live, at a cycle's end: a step that
                # has climbed starts its next level at the next block.
                if self._cycles <= 0 or generator.level != "reach":
                    return None
                self._cycles -= 1
                self._cycle = generator.reach_cycle()
            return self._cycle.pop(0)
        reask = generator.pending_reask()
        if reask is not None:
            return reask
        if self._issued >= self._target or generator.level != self._level:
            return None
        return generator.draw()


class DrillGenerator:
    """Drill blocks for one session (ADR-024).

    The step's place on the ladder is **not** held here: it is recorded by
    `StepLadder` and read back, so a child at Travel is still at Travel next
    session (ADR-024 § What survives a restart). What is held here is the
    session-local things that really are session-local: the draw's last
    letters and owed re-asks, the pace measure and the per-key session counts.
    """

    def __init__(
        self,
        layout: Layout,
        source: WordSource,
        key_states: KeyStates,
        clock: Clock,
        rng: random.Random,
        store: Store,
        profile_id: int,
        session_id: int,
        rest: Callable[[], Rest],
    ) -> None:
        self._layout = layout
        self._source = source
        # ADR-024's bar skips the speed term for the two bump letters: in their
        # own step the only comparison it could make is one index finger
        # against the other. Known still applies it.
        self._bumps = frozenset(home_anchor_keys(layout))
        self._states = key_states
        self._store = store
        self._profile_id = profile_id
        self._session_id = session_id
        self._rest = rest
        self._clock = clock
        self._rng = rng
        self._ladder: StepLadder | None = None
        self._session_attempts: dict[str, int] = {}
        # Both derived tables are a full pass over the corpus, and the block
        # generator reads them several times per block.
        self._weights: dict[str, float] = source.grapheme_weights(layout)
        self._bigrams: dict[str, float] = dict(sorted(source.bigram_weights(layout).items()))
        self._cells = {(key.row, key.col): name for name, key in layout.keys.items()}
        self._pace: deque[tuple[int, float]] = deque(maxlen=config.PACE_BLOCKS)
        self._block_open = False
        self._baseline_cache: dict[str, float | None] = {}
        # The draw (ADR-024 § The draw: repeats and misses). Held across
        # blocks: a block boundary is not a reason to forget what was just asked.
        self._last_drawn: str | None = None
        self._run = 0
        self._reask: str | None = None
        self._reasks_left = 0
        # The letter whose re-asks have just ended: the draw moves away from it.
        self._avoid: str | None = None
        self._paced_attempts = 0
        self._block_seconds = 0.0
        # None until the block's first answer: see `record_answer`.
        self._answered_at: float | None = None

    @property
    def ramp_up(self) -> StepLadder | None:
        return self._ladder

    @property
    def level(self) -> Level | None:
        return None if self._ladder is None else self._ladder.level

    @property
    def session_complete(self) -> bool:
        """ADR-024 § Per-key session floor — a soft signal, not an interrupt."""
        active = self._active()
        return bool(active) and all(
            self._session_attempts.get(name, 0) >= config.SESSION_KEY_FLOOR for name in active
        )

    def begin_step(self, step: IntroductionStep) -> bool:
        """Start ADR-024's ladder for a step the introducer has just emitted.

        False when the step needs no ramp-up because every member has already
        met the bar -- only reachable for a strategy that hands over a key the
        child has already drilled. The caller must not speak an introduction
        for a step that starts nothing.
        """
        if not 1 <= len(step.keys) <= 2:
            # ADR-028 § Pair ramp-up covers a solo member and a pair. A step of
            # another shape is an amendment there, not something to guess at.
            raise ValueError(f"a step carries one or two graphemes, not {len(step.keys)}")
        # Whether a member takes Reach is read from today's rest keys, when
        # the step begins or resumes.
        members = [(intro.grapheme, self._takes_reach(intro.grapheme)) for intro in step.keys]
        self._ladder = StepLadder(self._store, self._profile_id, self._session_id, members)
        self._reask = None
        self._avoid = None
        # A brand-new step has no records, so this begins its first level.
        # Reading rather than asserting it is what makes `resume_step` below
        # the same code path as a fresh introduction.
        self._refresh()
        return self.ramp_up is not None

    def resume_step(self, step: IntroductionStep) -> bool:
        """Re-enter a step's ladder where the child's records put it.

        Called once at session start (alpha-plan #12d). Returns False and
        starts nothing when no member has a single press, Reach or counted:
        that is an introduction the child never answered, and ADR-023 § What
        the introducer remembers owes them the whole script again, which the
        introducer's own path gives. A step still at Reach is begun again from
        nothing (ADR-024), which `StepLadder` does by reading only this
        session's Reach run.
        """
        if not any(
            self._store.reach_presses(self._profile_id, intro.grapheme)
            or self._lifetime_attempts(intro.grapheme)
            for intro in step.keys
        ):
            return False
        return self.begin_step(step)

    def next_block(self) -> Block:
        if self._block_open:
            self._pace.append((self._paced_attempts, self._block_seconds))
        self._block_open = True
        self._paced_attempts = 0
        self._block_seconds = 0.0
        self._answered_at = None
        target = self._target_prompts()
        ladder = self._ladder
        # Read here, at the boundary, where the session holds the key states
        # and the windows are being read anyway. Left to the first judged
        # keystroke it is a pass over every Active key on the keypress path.
        self._baseline_cache = (
            {} if ladder is None else {name: self._read_baseline(name) for name in ladder.graphemes}
        )
        if ladder is None or ladder.level is None:
            return DrillBlock(tuple(self._steady_units(target)))
        return _LadderBlock(self, ladder.level, target)

    def record_answer(self, prompt: Prompt, correct: bool) -> None:
        """A prompt's first press, once per prompt, after `AttemptCounter` has written it.

        Every kind of prompt is an answer for pace: answering it took the
        child's time (ADR-024 § Lesson granularity, restated). Only a counted
        prompt is an attempt, for the session floor and the ladder's Choose,
        Travel and the bar; only a Reach prompt moves Reach.
        """
        now = self._clock.monotonic()
        # Pace is measured over the gaps between one answer and the next, and a
        # gap longer than the cap is not one of them -- the child had stopped
        # typing (a PAUSED interval, a walk-away, a conversation), and monotonic
        # time runs through all of those. Such an answer contributes neither
        # time nor count. A block's first answer has no answer before it, so it
        # opens the measure and is not a gap: what lies between the block being
        # built and that answer is whatever the session says first, an
        # introduction script or a celebration, and none of it is typing.
        previous, self._answered_at = self._answered_at, now
        if previous is not None and now - previous <= config.PACE_IDLE_GAP_SECONDS:
            self._block_seconds += now - previous
            self._paced_attempts += 1
        grapheme = prompt.grapheme
        if prompt.kind is PromptKind.REST or grapheme is None:
            return
        if prompt.kind is PromptKind.COUNTED:
            self._session_attempts[grapheme] = self._session_attempts.get(grapheme, 0) + 1
            if not correct and self.level in ("choose", "travel"):
                # A missed letter is asked again (ADR-024 § The draw).
                self._reask = grapheme
                self._reasks_left = config.MISS_REPEATS
        elif prompt.kind is PromptKind.REASK and grapheme == self._reask:
            self._reasks_left -= 1
            if correct or self._reasks_left <= 0:
                self._reask = None
                self._avoid = grapheme
        ladder = self._ladder
        if ladder is None or grapheme not in ladder.graphemes:
            # A bump letter or a partner. It is practice, and it counts for the
            # session floor and ceiling, but the ladder is the new letter's.
            return
        if prompt.kind in (PromptKind.COUNTED, PromptKind.REACH):
            self._refresh()

    # ---- the ladder ----------------------------------------------------

    def _refresh(self) -> None:
        """Record any event the latest press met, then read the step's level.

        Called after the press has been written, so the row the child just
        produced is included: the session loop writes through `AttemptCounter`
        before it tells this generator.
        """
        ladder = self._ladder
        if ladder is None:
            return
        ladder.refresh(self._baseline)
        if ladder.level is None:
            self._ladder = None  # General practice: the members join its pool.

    def _baseline(self, grapheme: str) -> float | None:
        """ADR-027: what this member's speed is judged against, the baseline Known reads.

        Cached and refreshed at a block boundary. The pool moves on the scale
        of days -- its keys have 90 presses across two calendar days -- so
        reading it per keystroke would buy nothing and cost a window read per
        Active key.
        """
        if grapheme not in self._baseline_cache:
            self._baseline_cache[grapheme] = self._read_baseline(grapheme)
        return self._baseline_cache[grapheme]

    def _read_baseline(self, grapheme: str) -> float | None:
        return None if grapheme in self._bumps else self._states.speed_baseline(grapheme)

    def _lifetime_attempts(self, grapheme: str) -> int:
        stat = self._store.key_stats(self._profile_id).get(grapheme)
        return stat.attempt_count if stat is not None else 0

    def _fingers(self, grapheme: str) -> list[PhysicalKey]:
        """The keys a letter is typed with, in keystroke order: a composite's modifier first."""
        return [self._layout.keys[name] for name in self._layout.graphemes[grapheme].prereq_keys]

    def _takes_reach(self, grapheme: str) -> bool:
        """ADR-024: a letter with no reach has no Reach level.

        A letter has one when any key it is typed with is off its finger's rest
        key. So a rest letter and the bump letters have none, and a composite
        has one unless its modifier and its base are both rest keys, which
        needs a dead key as a rest key: ADR-033 allows it, and nothing can land
        on one yet. A finger with no current rest key has nowhere to come back
        to, so a letter on it gets no Reach (argued; nothing removes a rest key
        today).
        """
        rest = self._rest()
        keys = self._fingers(grapheme)
        cells = [rest.get(key.finger) for key in keys]
        if any(cell is None for cell in cells):
            return False
        return any(
            (key.row, key.col) != (cell.row, cell.col)
            for key, cell in zip(keys, cells, strict=True)
            if cell is not None
        )

    def _cue(self, grapheme: str) -> Prompt:
        """The rest cue after `grapheme`: every finger the letter was typed with, back where it rests.

        Decided 2026-11-12 (#12m session (6)): "rest" means all the fingers
        back, and it is confirmed by a press with each finger the letter used.
        """
        rest = self._rest()
        owed: list[str] = []
        fingers: list[str] = []
        for key in self._fingers(grapheme):
            cell = rest[key.finger]
            if key.finger in fingers:
                continue
            fingers.append(key.finger)
            owed.append(self._cells[(cell.row, cell.col)])
        return Prompt(PromptKind.REST, owed=tuple(owed), fingers="+".join(fingers))

    def reach_cycles(self, target: int) -> int:
        """Whole Reach cycles for a block: the pace target, capped by what the level still needs."""
        ladder = self._ladder
        assert ladder is not None
        reaching = [g for g in ladder.graphemes if ladder.takes_reach(g)]
        # Each cycle is a letter and its cue for every member that reaches.
        per_cycle = 2 * len(reaching)
        owed = max(ladder.owed(g) for g in reaching)
        return max(1, min(max(1, owed), -(-target // per_cycle)))

    def reach_cycle(self) -> list[Prompt]:
        """One Reach cycle: each reaching member's letter, then the rest cue, left hand first.

        A member that has met Reach's rule keeps being prompted while its
        partner catches up; its presses feed its own reach reading and nothing
        else (ADR-024, "Pairs").
        """
        ladder = self._ladder
        assert ladder is not None
        cycle: list[Prompt] = []
        for grapheme in ladder.graphemes:
            if ladder.takes_reach(grapheme):
                cycle += [Prompt(PromptKind.REACH, grapheme), self._cue(grapheme)]
        return cycle

    def pending_reask(self) -> Prompt | None:
        return None if self._reask is None else Prompt(PromptKind.REASK, self._reask)

    def draw(self) -> Prompt:
        """One prompt of Choose or Travel, each letter of the set equally likely (ADR-024).

        Within two rules: a prompt follows itself at most MAX_SAME_IN_A_ROW
        times, and after a letter's re-asks the draw moves to another letter.
        A re-ask is not a draw, so it is outside the cap.
        """
        letters = sorted(self._draw_set())
        allowed = [name for name in letters if name != self._avoid] or letters
        if self._run >= config.MAX_SAME_IN_A_ROW:
            allowed = [name for name in allowed if name != self._last_drawn] or allowed
        choice = self._rng.choice(allowed)
        self._run = self._run + 1 if choice == self._last_drawn else 1
        self._last_drawn = choice
        self._avoid = None
        return Prompt(PromptKind.COUNTED, choice)

    def _draw_set(self) -> set[str]:
        """Choose: the step's letters and the two bump letters. Travel: its letters and partners."""
        ladder = self._ladder
        assert ladder is not None
        step = set(ladder.graphemes)
        if ladder.level == "choose":
            return step | self._bumps
        return step | self._partners(step)

    def _partners(self, step: AbstractSet[str]) -> set[str]:
        # ADR-024 § Travel: TRAVEL_PARTNERS other Active letters, the ones the
        # language uses most, ranked by each letter's own frequency. While the
        # bump letters are the only other Active ones, this is Choose's set.
        pool = self._active() - set(step)
        ranked = sorted(pool, key=lambda name: (-self._weight(name), name))
        return set(ranked[: config.TRAVEL_PARTNERS])

    # ---- content -------------------------------------------------------

    def _steady_units(self, target: int) -> list[Unit]:
        # ADR-024 § Steady-state drill generation (alpha-plan #12e): each block
        # is planned. *Which* key a unit practises is decided by the learner's
        # need; the bigram that carries it is still the language's, so
        # same-finger bigrams and a word's own double letter are practised, not
        # avoided -- they exist in the language and avoiding them is a debt that
        # comes due in Layer 2.
        active = self._active()
        if not active:
            # Nothing has been introduced yet. An empty block is the honest
            # answer -- the caller's next act is an introduction, and the same
            # state is what `session_complete` guards against.
            return []
        slots = max(1, -(-target // 2))
        # ADR-010's soft ceiling: a key drilled SESSION_KEY_CEILING times this
        # sitting is no longer planned as a target. It still turns up inside
        # other keys' bigrams. If every key is there, nobody is excluded -- the
        # block has to be about something.
        targetable = {
            name
            for name in active
            if self._session_attempts.get(name, 0) < config.SESSION_KEY_CEILING
        } or active
        slow = self._states.slow_keys()
        needs = {name: self._need(name, name in slow) for name in targetable}
        counts = plan_targets(needs, slots, self._rng)
        pool = self._pool(active)
        groups = [
            [self._carrier(name, pool, active) for _ in range(counts[name])]
            for name in sorted(counts)
        ]
        return self._spread([group for group in groups if group])

    def _need(self, grapheme: str, slow: bool) -> int:
        evidence = self._states.evidence(grapheme)
        need = presses_needed(evidence, config.KNOWN_MIN_ACCURACY)
        if slow:
            # Only speed keeps it from Known, and speed comes from practice.
            # Without this it would be planned for nothing and hold its slot.
            need = max(need, config.SLOW_KEY_NEED)
        # A key that lacks only another day is one press from Known, and Known
        # is what frees its slot for the next letter (ADR-010). Only until it
        # has been pressed this session: after that today is one of its days,
        # and a further press buys nothing.
        waiting = (
            evidence.distinct_days < config.KNOWN_MIN_DISTINCT_DAYS
            and grapheme not in self._session_attempts
        )
        return max(need, 1) if waiting else need

    def _carrier(self, grapheme: str, pool: dict[str, float], active: AbstractSet[str]) -> Unit:
        carriers = {bigram: weight for bigram, weight in pool.items() if grapheme in bigram}
        if carriers:
            bigram = self._choose(carriers)
            return (bigram[0], bigram[1])
        # No corpus bigram carries this letter over the Active set -- true early
        # in the curriculum, where the child has a handful of letters that never
        # co-occur. Pair it with the heaviest other Active letter instead.
        # Name in the sort key, like every other selection here: zero-weight
        # graphemes exist by construction (`rank_graphemes`), so ties are
        # guaranteed, and without it they would resolve by set iteration order
        # and break reproducibility from the seed.
        others = sorted(active - {grapheme}, key=lambda name: (-self._weight(name), name))
        return (grapheme, others[0] if others else grapheme)

    def _spread(self, groups: list[list[Unit]]) -> list[Unit]:
        # Each group's units evenly through the block, from a random phase, so
        # a key with five units meets the child five times across the block
        # rather than five times running.
        placed: list[tuple[float, int, int, Unit]] = []
        for index, group in enumerate(groups):
            phase = self._rng.random()
            placed += [((i + phase) / len(group), index, i, unit) for i, unit in enumerate(group)]
        return [unit for *_, unit in sorted(placed)]

    # ---- pace ----------------------------------------------------------

    def _target_prompts(self) -> int:
        # ADR-024 § Lesson granularity: target_keystrokes = target_seconds x
        # the child's rolling pace. Measured in prompts answered, which is what
        # the engine can count (ADR-027) and what the block is built out of.
        prompts = sum(count for count, _ in self._pace)
        seconds = sum(elapsed for _, elapsed in self._pace)
        if prompts == 0 or seconds <= 0:
            return config.FIRST_BLOCK_PROMPTS
        return max(1, round(config.BLOCK_TARGET_SECONDS * prompts / seconds))

    # ---- language layer ------------------------------------------------

    def _active(self) -> set[str]:
        # ADR-027 § Key States aligns the terminology: ADR-024's
        # "previously-known keys" are keys the child has been *introduced* to,
        # which is Active. Reading it as Known (90 attempts over 2 days) would
        # leave every early key without an anchor.
        return self._states.active_keys() & set(self._layout.graphemes)

    def _weight(self, grapheme: str) -> float:
        return self._weights.get(grapheme, 0.0)

    def _pool(self, graphemes: AbstractSet[str]) -> dict[str, float]:
        # `self._bigrams` is sorted at construction so sampling is reproducible
        # from the seed alone, whatever order the source hands its weights in.
        return {
            bigram: weight for bigram, weight in self._bigrams.items() if set(bigram) <= graphemes
        }

    def _choose(self, pool: dict[str, float]) -> str:
        keys = sorted(pool)
        return self._rng.choices(keys, weights=[pool[key] for key in keys])[0]
