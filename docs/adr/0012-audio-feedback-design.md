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

**Wrong character handling — auto-reject:**

When the child types an incorrect character, the keypress is auto-rejected: it is never committed to the typed sequence. The error tone fires immediately (low-latency sound cue, not TTS). TTS then re-prompts the current character. The child simply tries again. This means every character that has been accepted is correct by definition — the child is always at a known position with a clean sequence behind them.

Auto-reject applies in both layers. In Layer 1 the drill repeats the same character prompt. In Layer 2 the same character position in the word is re-prompted.

**Backspace — considered and rejected:**

With auto-reject in place, backspace has no meaningful use case. The only situations where backspace seems useful — "I typed the wrong character," "I want to rethink from an earlier position" — are either already handled (wrong characters are discarded automatically) or better served by other controls. Going back one character does not help a child who is disoriented; re-reading the full prompt does. Backspace is therefore disabled entirely. Pressing it plays the boundary tone so the child knows the key registered but had no effect.

This was a deliberate decision. Future contributors should not reintroduce backspace without revisiting the auto-reject model — the two are in tension, and the combination creates more complexity than it resolves.

**Recovery — re-read key:**

A dedicated re-read key (configurable, default Escape) re-speaks the full current prompt and position at any time: *"house — typed: h, o — next: u"*. This is the recovery path for a child who has lost track, mis-heard a character, or simply wants to reorient. It does not reset progress on the current word.

A separate restart key (configurable, default Escape held or double-tap) abandons the current word and re-presents it from the beginning. The word is not counted toward session totals.

**WPM measurement:** Execution time is measured from the child's first keystroke to their last accepted keystroke on a given word. Prompt delivery time is excluded entirely. WPM is only computed and surfaced in progress reporting once the child is in dictation mode (Diamond milestone reached).

**Clean word definition:** A word is "clean" if it was completed with no auto-rejections and no restarts — every character accepted on the first attempt. This is the metric used for progression thresholds and the child summary, not raw completion rate.
