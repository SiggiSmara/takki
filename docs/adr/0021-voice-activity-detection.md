# ADR-021: Voice Activity Detection

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Use `webrtcvad` for end-of-utterance detection. With push-to-talk (ADR-020), start-of-speech is signalled by the talk key, so VAD is needed only to determine when the child has finished speaking. Neural VAD alternatives (`silero-vad`) are deferred.

### Rationale

VAD requirements are different under push-to-talk than under always-on listening:

- Start-of-speech is signalled by the talk key — no acoustic detection needed
- End-of-speech ("they stopped, send to Whisper now") is the only acoustic decision left
- End-of-utterance detection is exactly what energy + spectrum-based VAD is good at; the harder cases for VAD (distinguishing speech from speech-like noise during a long passive listening window) do not arise

`webrtcvad` is:

- A small native extension (~30 KB)
- The original Google WebRTC voice activity detector — mature, well-tested, widely deployed
- Pure C with thin Python bindings — no neural network, no model file, no GPU
- Fast enough to run frame-by-frame on the audio stream with negligible CPU cost

The cost of adding `silero-vad` (the obvious neural alternative) is substantial:

| | `webrtcvad` | `silero-vad` (via Torch) | `silero-vad` (via onnxruntime) |
|---|---|---|---|
| Install size | ~30 KB | ~200 MB (CPU-only Torch wheels) | ~50 MB |
| Bundle impact (PyInstaller) | negligible | +500 MB – 1 GB | ~60 MB |
| Cold-start time | instant | 1–2s Torch import | <500ms |
| ML runtime count | 0 | 2 (Torch + CTranslate2) | 2 (onnxruntime + CTranslate2) |
| Accuracy on quiet speech | OK | Better | Better |

For end-of-utterance under push-to-talk, the accuracy gain does not justify the added runtime weight. The most expensive part of the project's distribution story is already the PyInstaller bundle plus the bundled Whisper and Piper models. Adding 500 MB+ for a marginal VAD upgrade would dominate the install size for a feature most children will never notice working correctly.

### How It Works in Takki

1. Talk key pressed → audio recording begins at 16 kHz mono (matching Whisper's native rate)
2. Audio is fed to `webrtcvad` in 20ms frames
3. VAD reports speech/non-speech per frame
4. After N consecutive non-speech frames (default 800ms after the first speech frame is seen), recording ends
5. A maximum recording length (default 10 seconds) caps the recording if VAD fails to detect silence
6. The full recording is passed to Whisper for transcription

### Sensitivity Setting

`webrtcvad` exposes an aggressiveness setting of 0–3:

- 0 = least aggressive (more permissive — more likely to declare speech, less likely to cut off quiet speakers)
- 3 = most aggressive (more likely to declare silence, more likely to cut off quiet speech)

**Default: 2** (moderate). Configurable per profile. A quiet child or noisy school environment may need a lower setting; an environment with continuous background noise may need a higher one.

### Failure Modes

- **VAD never detects silence (continuous noise).** The 10-second cap ends the recording, Whisper transcribes, and the intent layer handles whatever it can. If Whisper returns garbage, the standard "I didn't catch that — try again" response fires.
- **VAD declares silence immediately (mic level too low).** Whisper receives a too-short audio clip and returns nothing meaningful. Same response: "I didn't catch that — try again." Repeated occurrences may prompt the app to suggest reducing VAD aggressiveness during a future setup pass.
- **VAD declares silence during a long pause mid-utterance.** Acceptable failure mode — the child can simply press the talk key again. With push-to-talk, a "false cut" is annoying but not destructive.

### Future Upgrade Path

If Beta pilot testing reveals that `webrtcvad` consistently fails on real child speech in real environments (quiet speakers, noisy classrooms, accented speech), the upgrade path is `silero-vad` loaded via `onnxruntime` — **not** via Torch. `onnxruntime` is a much smaller dependency than Torch and remains compatible with the bundle-size constraint.

The VAD interface sits behind a Protocol (ADR-019), so swapping implementations is a localised change.

### Alternatives Considered

- **Naive energy threshold.** Works in quiet environments but doesn't distinguish speech from noise. Sensitive to mic gain — a child with a quiet mic gets cut off; a child with a hot mic gets noise recorded as speech. `webrtcvad` is barely heavier and meaningfully more robust.
- **`silero-vad` via Torch.** Quality gain doesn't justify Torch dependency and bundle inflation. See table above.
- **`silero-vad` via onnxruntime.** Viable but adds an ML runtime we don't currently need. Reserved as the upgrade path if `webrtcvad` proves insufficient.
- **Streaming Whisper / continuous transcription.** Out of scope — we are not building a dictation tool. Voice input is for short navigation commands, not continuous speech-to-text.
