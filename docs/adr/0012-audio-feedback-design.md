# ADR-012: Audio Feedback Design

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Two-tier audio feedback — TTS for spoken content, bundled sound cues for immediate correctness feedback. Five named cues are defined; each can be overridden with a custom `.wav` file via `takki_config.yaml` (ADR-025). Alpha ships with programmatically generated tones so no binary assets are committed to source; Beta replaces these with real bundled `.wav` files.

### Rationale

For a visually impaired child, the timing and nature of feedback is critical:

**Immediate sound cues** (not TTS): Five named cues cover all feedback events in the lesson engine and push-to-talk pipeline:

| Cue name | Event | Alpha default tone |
|---|---|---|
| `correct` | Key accepted on first attempt | 880 Hz, 200 ms, 30 ms fade |
| `error` | Key rejected (wrong character) | 220 Hz, 180 ms, 20 ms fade |
| `boundary` | Disabled key pressed (e.g. Backspace) | 440 Hz, 100 ms, 10 ms fade |
| `chirp_on` | Microphone opened (push-to-talk) | 660 → 1100 Hz sweep, 150 ms |
| `chirp_off` | Microphone closed | 1100 → 660 Hz sweep, 150 ms |

Each cue is loaded at startup from a `.wav` file. The path for each cue resolves as: `takki_config.yaml` override path → bundled `assets/sounds/<cue>.wav` → programmatically generated tone (Alpha fallback). The generated tone is a pure sine wave (linear frequency sweep for chirps) produced in pure Python via `wave` + `struct`, with no additional dependencies. Tone parameters are defined in `config.py` (ADR-025).

A short pleasant chime for a correct keypress, a gentle low tone for incorrect. These play within milliseconds of the keypress — fast enough to feel like direct cause and effect. Implemented via `pygame.mixer` with small bundled `.wav` files. TTS latency (even with fast local models) is too slow for this feedback loop. Confirmed on Windows: `pygame.mixer` initialises and plays audio without `pygame.display` — no window is opened (pygame 2.6.1, SDL 2.28.4, 22050 Hz stereo).

The talk-key chirp tones (chirp-on / chirp-off, see ADR-020) use the same `pygame.mixer` pipeline. They are tonally distinct from the correct/error cues so the child never confuses "mic is open" with "you typed correctly."

### Sound cue channel policy

*(Decided 2026-08-22. Closes the "sound channels" carry-forward that gated alpha session 4.)*

**One reserved `pygame.mixer` channel per cue class; monophonic within a class; newest wins.**

| Channel | Cue class | Cues |
|---|---|---|
| reserved 0 | keypress feedback | `correct`, `error`, `boundary` |
| reserved 1 | push-to-talk state | `chirp_on`, `chirp_off` |

Channels are reserved via `pygame.mixer.set_reserved()` so the general pool can never steal them. A new cue within a class replaces whatever that class is currently playing; classes never contend with each other.

Rationale:

- **Channel starvation is not the real risk.** Cues are 100–200 ms against a default pool of 8 channels, so exhausting it needs roughly 40 cues per second — far beyond any child's typing rate. The risks that actually bite are overlap and cross-class theft.
- **Overlapping identical tones muddy rather than double.** Two `correct` chimes (both 880 Hz sine) overlapping read as a single louder, phasing chime. For a child whose only channel is audio, an ambiguous cue is worse than a truncated one.
- **A stolen chirp is a correctness bug, not a cosmetic one.** If `chirp_on` is dropped or cut short by a typing cue, the child does not know the microphone is open — which is exactly the signal ADR-020's push-to-talk model depends on. Separate reservation makes that impossible.
- **Newest wins.** A cue arriving late and referring to a keypress two presses ago actively misinforms. Stale feedback is worse than no feedback.
- **Determinism.** Exactly one cue per class is audible at any instant, so `FakeSoundCues` records a linear sequence and the engine tests (alpha sessions 7–10) assert on it without timing dependence.

The policy is expressed per cue *class* rather than as two hardcoded channels: the acknowledgement click proposed under [§ Open questions and future work](#open-questions-and-future-work) would add a third class.

**Mixer initialisation is pinned in `config.py`,** not left to the pygame default: 22050 Hz stereo (confirmed on Windows, above) plus an explicit buffer size, which sets the floor on cue latency — 512 samples is ≈ 23 ms at 22050 Hz. This ADR promises cues "within milliseconds"; the number must not drift silently with a pygame version bump.

**Cues and TTS do not interact.** A keypress calls `tts.stop()` and then plays its cue; both are non-blocking calls from the main thread ([concurrency-model.md](../concurrency-model.md)). A cue never waits on speech, and speech never delays a cue.

**TTS for spoken content:** Everything else — what to type next, encouragement, instructions, milestone announcements, menu navigation — uses Piper TTS (or SAPI fallback). This content is not latency-sensitive.

**Encouragement variety:** The rule-based feedback generator cycles through a set of varied encouragement phrases per language. The generator sits behind a Protocol boundary (ADR-019), so a downstream fork could substitute a generative implementation — Takki itself ships rule-based only ([ADR-031](0031-no-llm-integration.md)).

**Progress encouragement — two-phase design:** Between key milestones, the app motivates continued practice by describing what unlocking the next key would gain. This uses two phases:

*Phase 1 — coverage gain framing* (most of the journey, while the coverage curve is steep):
> "Learn your next letter and you'll be able to type X% more everyday words."

X is the marginal coverage gain from the next letter in frequency order. The letter itself is not named — the lesson engine controls introduction order, and revealing the next letter encourages the child to skip ahead rather than consolidate current keys. This framing is most effective while marginal gains are large (the steep middle of the coverage curve).

*Phase 2 — countdown framing* (when ≤ 6 letters remain in the native alphabet):
> "Only 5 letters of the alphabet left!"

Triggered when `remaining = alpha_size − keys_mastered ≤ 6`. The coverage framing is dropped at this point because marginal gains are tiny in the tail and the countdown is more motivating. Knowing you are nearly done is a stronger motivator than being told the next letter unlocks 0.3% more words.

**Word presentation protocol:**

- *Character drills (Layer 1):* Each character is announced individually by TTS, then the child types it. The next character follows after a correct keypress or a configurable timeout.

- *Real words, early (Layer 2, pre-Diamond):* The whole word is spoken first, then spelled letter by letter: *"house — h, o, u, s, e"*. The child then types. The whole-word reading reinforces correct pronunciation; the spelling reinforces phoneme-grapheme mapping. Both are intentional — this is the design that distinguishes real words from the pseudo-word approach that was considered and rejected (see ADR-010).

- *Real words, dictation mode (Layer 2, Diamond+):* The spelling step is withheld. Only the whole word is spoken. The child must recall the spelling from memory. Successful typing without the spelling prompt is the readiness signal for the Diamond milestone.

**TTS interrupt on keypress:**

When the child types while TTS is still speaking the prompt, the TTS is cancelled immediately and the keypress is processed normally. Confident typers — especially older or more fluent children — should not be slowed by the prompt audio they already know. The sound cue and any re-prompt that follow play against silence, not over a tail of unfinished speech. The cancellation is per-utterance: only the current spoken prompt is interrupted, not the application's audio pipeline.

This applies in both layers and to any non-essential TTS (encouragement, between-word remarks). Universal voice commands and milestone announcements complete their utterance and are not interrupted by keypresses, since they are not part of the current type-this-character loop.

### TTS utterance sequencing and cancellation

*(Decided 2026-08-22. Closes a gap found while reviewing alpha session 4: `TTSWorker.stop()` cancels the utterance in flight, but nothing said what becomes of a prompt's remaining utterances.)*

**Multi-utterance prompts are sequenced by the core, one utterance at a time.** The word presentation protocol above — *"house — h, o, u, s, e"* — is six utterances, not one. The core holds the remainder as ordinary main-thread state and enqueues the next only when `SpeechFinished` arrives, so the TTS worker's command queue never carries a backlog.

Cancelling is therefore two steps at two levels:

| Level | Call | Cancels |
|---|---|---|
| Worker | `TTSEngine.stop()` | the utterance currently audible — the single sanctioned cross-thread call ([concurrency-model.md](../concurrency-model.md)) |
| Core | clear the pending sequence | the utterances not yet spoken — a plain field on the thread that owns it |

Having the worker drain its own command queue inside `stop()` was considered and rejected: it races the worker popping the next command, and it makes `stop()` do two unrelated things. Keeping the backlog in core state means there is no cross-thread queue to drain and no lock to reason about.

**Utterance ids guard the completion race.** A keypress can arrive microseconds after the worker finished naturally and posted `SpeechFinished(N, completed)` — that event is still sitting in the inbound queue while the core starts the next prompt. The core ignores any `SpeechFinished` whose id is not the one in flight; without that check the stale event would advance the *new* sequence by one, skipping an utterance that was never spoken. This is the concrete case behind concurrency-model.md's "a cancel racing a natural completion cannot double-advance a prompt."

**Sequences are interruptible or not,** which formalises the paragraph above as a flag the core carries alongside the pending sequence:

- *Interruptible* — the type-this-character loop: character and word prompts, the spelling step, encouragement, between-word remarks. A keypress stops what is audible and clears the remainder.
- *Not interruptible* — milestone announcements and voice-command responses. The keypress is processed normally (accepted or auto-rejected, with its cue), but the speech runs to completion.

This refines "the cancellation is per-utterance" above: the audio pipeline is never torn down, but an interrupted *prompt* loses its unspoken remainder, not only the utterance in flight.

**Left open,** because it needs the lesson engine's state machine in view (alpha session 11): what happens when a prompt becomes due while a non-interruptible utterance is still speaking. Holding it, dropping it, and speaking it afterwards are all defensible.

**Wrong character handling — auto-reject:**

When the child types an incorrect character, the keypress is auto-rejected: it is never committed to the typed sequence. The error tone fires immediately (low-latency sound cue, not TTS). TTS then re-prompts the current character. The child simply tries again. This means every character that has been accepted is correct by definition — the child is always at a known position with a clean sequence behind them.

Auto-reject applies in both layers. In Layer 1 the drill repeats the same character prompt. In Layer 2 the same character position in the word is re-prompted.

**Backspace — considered and rejected:**

With auto-reject in place, backspace has no meaningful use case. The only situations where backspace seems useful — "I typed the wrong character," "I want to rethink from an earlier position" — are either already handled (wrong characters are discarded automatically) or better served by other controls. Going back one character does not help a child who is disoriented; re-reading the full prompt does. Backspace is therefore disabled entirely. Pressing it plays the boundary tone so the child knows the key registered but had no effect.

This was a deliberate decision. Future contributors should not reintroduce backspace without revisiting the auto-reject model — the two are in tension, and the combination creates more complexity than it resolves.

**Recovery — re-read key:**

A dedicated re-read key (configurable, default Escape) re-speaks the full current prompt and position at any time: *"house — typed: h, o — next: u"*. This is the recovery path for a child who has lost track, mis-heard a character, or simply wants to reorient. It does not reset progress on the current word.

A separate restart key (configurable, default Escape **held**) abandons the current word and re-presents it from the beginning. The word is not counted toward session totals.

**Tap versus hold (resolved 2026-08-22).** The two actions share one key by default and are separated by hold duration, not by double-tap: a tap — released before `RESTART_HOLD_MS` (default 800 ms) — re-reads; holding past that threshold restarts, firing at the threshold while the key is still down so the child gets the confirmation at the moment the gesture qualifies. Double-tap was rejected because it would delay *every* re-read by the double-tap window in order to see whether a second tap arrives, and re-read is the recovery path for a child who is already disoriented — the common, urgent action must not pay for the rare, destructive one. Double-tap also asks for a motor-timing skill that varies widely among the target users, where hold-until-it-happens is self-paced and self-correcting: releasing early simply yields the re-read.

Two implementation consequences. **Key auto-repeat must be ignored** — holding a key makes the OS emit repeated press events (ADR-005/session 5 pass them through faithfully), so the hold timer starts on the first press and is cleared only by the release; intervening repeats are not new presses. And the threshold is a **deadline checked each tick** against the `Clock` Protocol, never a timer thread ([concurrency-model](../concurrency-model.md) § Timers).

`reread_key` and `restart_key` remain independently configurable per profile ([ADR-011](0011-persistence-and-state.md)) and app-wide ([ADR-025](0025-configuration-system.md)). Binding them to two *different* keys is fully supported and turns the gesture off: when they differ, each key fires its action on press and no hold timing runs. Sharing one key is only the default.

**Resuming from PAUSED does not re-read — open** (raised 2026-08-22 by alpha session 6b). When focus returns, the focus model announces the resume and nothing else; it does not re-issue the prompt. A child who task-switched away mid-word comes back to silence and has to press the re-read key to find out where they are, which is precisely the disoriented state this section exists to serve. Emitting a re-read on resume is the obvious fix and was deliberately *not* built into the focus model, because what a re-read says — prompt, position, characters already typed — is engine state, so the decision belongs with the engine (sessions 9–10) rather than with the gate. Decide it there, alongside the auto-advance carry-forward.

**Escape's gesture budget is full.** Two actions on one key is the ceiling, so nothing further may be layered onto Escape by duration. This is a live constraint, not a style note: [ADR-028 § Open questions](0028-composite-input-and-keyboard-ownership.md) item 1 originally sketched a Beta emergency exit as "hold Escape 5 seconds," which would fire a word restart in passing at `RESTART_HOLD_MS` on every exit attempt and would turn an over-long re-read hold into a walk toward quitting the app. That item is now flagged to pick a different key. Anyone retuning `RESTART_HOLD_MS` should check that flag before assuming the threshold is theirs alone to move.

**WPM measurement:** Execution time is measured from the child's first keystroke to their last accepted keystroke on a given word. Prompt delivery time is excluded entirely. WPM is only computed and surfaced in progress reporting once the child is in dictation mode (Diamond milestone reached).

**Clean word definition:** A word is "clean" if it was completed with no auto-rejections and no restarts — every character accepted on the first attempt. This is the metric used for progression thresholds and the child summary, not raw completion rate.

### Open questions and future work

**Adaptive feedback density — three interlocking pieces, none decided.** Proposed 2026-08-22; tracked as roadmap C15. This needs the rolling accuracy window ([ADR-027](0027-key-and-accuracy-state-model.md)) and the rolling pace measure ([ADR-024](0024-drill-content-and-lesson-granularity.md)), so it cannot land before those exist — Beta at the earliest. None of it changes the `SoundCuePlayer` surface: suppression is the engine choosing not to call `play()`.

**1. Fade the `correct` cue as proficiency rises.** Feedback on every trial is known to help acquisition and *hurt retention* — the guidance hypothesis (Salmoni, Schmidt & Walter 1984; Winstein & Schmidt 1990 on faded feedback schedules): a learner given a signal after every repetition comes to lean on it instead of building an internal model. The information argument agrees — at 95% first-attempt accuracy the `correct` chime fires roughly 19 times for every `error` tone, carrying almost no information while occupying the child's only channel. Shape: a per-profile setting ([ADR-025](0025-configuration-system.md) tier 3) that the app *suggests* once thresholds trip, offered only at a natural endpoint (drill completion, session end, milestone) per [ADR-010](0010-lesson-structure-and-progression.md) — never mid-drill.

> **Trigger on accuracy and pace, not on cue overlap.** The point at which chimes would begin to overlap is a function of cue *duration*, which is user-configurable and changes when Beta swaps generated tones for real `.wav` files — a 400 ms replacement chime would silently halve the threshold. Accuracy is the signal that actually makes the cue uninformative; pace is a secondary gate.

The `correct` cue does real work for keys that are **not yet Known** (ADR-027) — that is where it is genuine scaffolding rather than noise. A per-key fade (silent on Known keys, chiming on keys still in training) is the sharper variant and reuses a state model that already exists; the counter-risk is that cue behaviour varying within a single drill may disorient a child who cannot see which key is which. Which shape wins is undecided.

**2. Two-chime keypress feedback: an acknowledgement click, then the outcome cue.** A very short click (mechanical-keyswitch-like, order of 10–20 ms) fires the instant an accepted keypress lands, followed by the `correct`/`error` cue. This separates two facts the current single-cue design conflates: *the keystroke reached Takki* and *the keystroke was right*. It is what makes piece 1 safe — with `correct` suppressed, silence would otherwise be ambiguous between "you got it right" and "nothing reached the app" (focus theft per [ADR-028](0028-composite-input-and-keyboard-ownership.md), a dead key, a hung process). The tactile feel of the key does not close this gap: it confirms the key moved, not that the application received it.

The acknowledgement is its own cue class and so takes a third reserved channel. A click and a tone occupy different spectral space, so the outcome cue overlapping the tail of a click reads as an attack transient rather than as mud.

**3. Hard upper bound on cue duration once cues are user-configurable.** When `takki_config.yaml` can point a cue at an arbitrary `.wav` (ADR-025), a multi-second file breaks the assumptions above: it masks the TTS prompt for the next character, bleeds across drill-block boundaries, and makes the monophonic newest-wins policy truncate constantly. Validate `Sound.get_length()` at load — a system boundary, which is where validation belongs — and on violation fall back to the bundled or generated cue with a warning rather than truncating, since a hard cut produces its own click artifact. The cap belongs in the same change that introduces cue-file overrides, not in a later pass. The same boundary check covers the generated-tone parameters (`TONE_*` in `config.py`, also overridable): a fade longer than half the tone's duration makes the fade-in and fade-out windows overlap, so the tone jumps to near-full amplitude partway through and ends on the click the fade exists to prevent.
