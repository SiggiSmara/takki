# ADR-002: Speech Recognition (Voice Control)

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** `faster-whisper` (local OpenAI Whisper implementation) as the sole speech recognition engine.

### Rationale

Voice control is a core feature — the app must be navigable without vision. The multilingual requirement makes this non-trivial. `faster-whisper` solves multiple constraints simultaneously:

- **Fully local** — no internet, no API keys, no privacy concerns (critical for children's data)
- **99+ languages** out of the box with no pre-training or language-specific setup
- **No ongoing cost** — important for a free open source project
- **Practical hardware requirements** — `tiny` and `base` are both bundled in the installer and auto-selected at startup by the CPU microbenchmark (see Model Auto-Selection below). `small` is not bundled: even on a modern Intel Core Ultra 7 it takes ~1.4s per utterance and is impractical without a CUDA-capable GPU. Measured latency on target hardware (AVX2, warm cache, mains power):

  | model | Ryzen 7 5700U | Intel Core Ultra 7 256V |
  |-------|--------------|------------------------|
  | tiny  | ~400ms       | ~230ms                 |
  | base  | ~730ms       | ~415ms                 |
  | small | ~2,300ms     | ~1,390ms               |

  On battery the Ryzen 5700U is ~2× slower (tiny ~800ms, base ~1.5s). Hardware below AVX2 (e.g. Celeron G555, SSE4.2 only) is below minimum spec — even `tiny` takes ~2.6s.

The model load time after the first run is under 1s (OS filesystem cache). Model load on first ever run is 16–19s due to Windows Defender scanning new files; subsequent runs are fast.

Whisper produces text transcriptions. Mapping transcriptions to actionable intents (e.g. "faster", "next", "stop") is handled by a separate intent recognition layer — see ADR-017. The microphone is closed by default and opens only via push-to-talk — see ADR-020 for the activation model and ADR-021 for end-of-utterance detection.

### Model Auto-Selection

*(Re-homed here from ADR-018 by [ADR-031](0031-no-llm-integration.md), 2026-07-05; content unchanged.)*

At startup a short CPU microbenchmark (512×512 float32 matrix multiplication, ~200ms) selects the Whisper model — no user decision required:

| matmul result | Whisper model | Typical latency |
|---------------|---------------|-----------------|
| < ~2ms        | `base`        | ~400–730ms      |
| ~2–10ms       | `tiny`        | ~400–800ms      |
| > ~10ms       | none          | below minimum spec; voice commands unavailable |

Thresholds are derived from measured spike data across three machines (Celeron G555, Ryzen 7 5700U, Intel Core Ultra 7 256V). The ~2ms threshold keeps `base` latency under ~800ms on mains power; above it, `tiny` provides comparable latency. The ~10ms floor reflects that SSE4.2-only CPUs (e.g. Celeron) cannot run even `tiny` within an acceptable latency budget.

The benchmark runs behind the `HardwareProbe` Protocol (ADR-019) and is implemented alongside the `faster-whisper` wrapper (Beta).

### Alternatives Considered

- **Windows Speech Recognition API:** Rejected. Requires per-language configuration, poor multilingual support, inconsistent accuracy.
- **Cloud APIs (Google, Azure):** Rejected. Require internet, API keys, ongoing cost, and raise data privacy concerns for children.
- **Pre-recorded command matching:** Rejected. Would require pre-recording commands in every supported language, which defeats the multilingual goal.
