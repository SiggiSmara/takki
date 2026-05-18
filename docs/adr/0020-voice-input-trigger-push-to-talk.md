# ADR-020: Voice Input Trigger — Push-to-Talk

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Voice input is gated by a dedicated push-to-talk key. The microphone is closed by default and opens only when the child presses the talk key. A short ascending chirp marks the start of listening; a short descending chirp marks the end. Wake-word and always-listening approaches are explicitly rejected.

### Rationale

The competing approaches all fail on at least one project constraint:

- **Always-listening.** Mic permanently hot. Contradicts the offline/privacy stance — even if no audio leaves the device, a parent or school IT explaining Takki cannot honestly say "the mic only opens when the child asks it to." That guarantee is a meaningful trust signal for the target audience.
- **Wake word ("Hey Takki").** Local wake-word engines (Porcupine, OpenWakeWord) are available and would preserve offline operation. But wake-word engines are trained predominantly on adult speech and have documented poor activation rates on children's voices. A child who already has limited feedback channels and has to repeat "Hey Takki" four times before the mic opens is a frustrated child. There is also no visual indicator a VI child can use to distinguish "the system heard the wake word but didn't understand the command" from "the system didn't hear the wake word at all" — both produce silence.
- **Push-to-talk.** Explicit control by the child. Audio cues (chirp on / chirp off) give a VI child unambiguous feedback that the mic is hot. The key itself is a learnable interaction — for a typing tutor, this is curriculum-adjacent rather than friction. Privacy guarantee is concrete: the mic is open exactly when the child holds or has just pressed the talk key.

The "extra key to learn" cost is genuinely small. VI children develop strong touch-locating muscle memory; a single dedicated key at a fixed location is well within the same skill set the app is teaching.

### Default Talk Key

**Right Ctrl** is the default. It is configurable per profile.

The key was selected against these constraints:

- Must not conflict with screen reader modifier conventions (Caps Lock and Insert are off-limits — these are used by NVDA, JAWS, and Windows Narrator and may collide if a screen reader is later installed alongside Takki)
- Must not conflict with characters the child types during lessons (rules out alphabet keys, Spacebar, Enter)
- Must be reliably findable by touch (rules out function keys on laptop keyboards where they share with brightness/volume, and Pause/Break which is missing on many keyboards)
- Single-press behaviour must be a no-op in normal use (so that accidental presses outside of intent-to-talk are harmless)
- Right Shift was considered and rejected — pressed often enough during typing that accidental triggering during practice is plausible.

No strong cross-tool convention exists in the VI community for this specific interaction; voice-input tools in the accessibility space (Talon Voice, Dragon) typically default to "configure your own." The Right Ctrl default will be validated during the Beta pilot, and the per-profile configurability means changing the default later is reversible without code change.

### Trigger Behaviour

**Press-and-release with auto-close** is the default:

1. Child presses and releases the talk key
2. Chirp-on plays (~150ms, ascending tone)
3. Microphone opens; recording begins
4. End-of-utterance is detected by VAD (see ADR-021) — typically 800ms of silence after speech
5. Chirp-off plays (~150ms, descending tone)
6. Recording ends; audio is passed to Whisper for transcription
7. Transcription is passed to the intent recognition pipeline (ADR-017)

A maximum recording length (default 10 seconds) caps any open-ended recording if VAD fails.

**Press-and-hold** is supported as a per-profile alternative. In this mode the mic is open while the key is held; release ends the recording immediately and skips the VAD-driven silence detection. Some children find walkie-talkie style more intuitive; some find press-and-release lower effort. The choice is part of profile setup.

### Audio Feedback Design

Chirp tones are distinct from the lesson engine's correct/error tones (ADR-012). They are:

- Short (~150ms each) — not interrupting the child's flow
- Tonally distinct from sound cues used elsewhere
- Identical across sessions and across lessons — predictable cue, not a varying signal

Together with the chirp-on/chirp-off pair, this gives a VI child unambiguous, time-bounded feedback about when the mic is hot. The mic is never in an ambiguous state from the child's perspective.

### Interaction With the Lesson Engine

- **During a lesson:** the talk key opens the mic for navigation commands (repeat, faster, slower, exit). The lesson pauses while listening. If a child presses the talk key mid-word, the current word is held in place, the command is resolved, then practice resumes from the same position. The word is not abandoned and progress is not lost.
- **During TTS output:** pressing the talk key cancels the current TTS utterance (consistent with the keypress-interrupts-TTS rule in ADR-012) and opens the mic immediately. The child should not have to wait for the prompt to finish before being able to interrupt.
- **During setup:** the talk key opens an additional command channel for universal escape intents (go back, help, skip). The setup script itself opens the mic during specific question prompts ("What's your name?", "What color do you want?") without the child needing the talk key.

### Alternatives Considered

- **Always-listening with intent threshold filter.** Rejected — keeps mic open, conflicts with privacy stance.
- **Wake word.** Rejected — see Rationale; child-speech activation rates are poor and the silent-failure mode is bad UX for VI children.
- **Push-to-mute (mic on by default, child turns it off).** Rejected — same privacy issue as always-listening, with worse defaults.
- **Touch a specific keyboard zone (multi-key combo).** Rejected — not different from a single key in practice, more complex to learn.
- **Hardware button (USB push-to-talk dongle).** Rejected for v1 — adds a peripheral dependency. May reconsider for v2 if pilot feedback suggests it.
