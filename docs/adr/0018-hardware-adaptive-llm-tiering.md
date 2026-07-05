# ADR-018: Hardware-Adaptive LLM Tiering

**Status:** Superseded by [ADR-031](0031-no-llm-integration.md) — the LLM tier model is removed entirely. The Whisper Model Auto-Selection section below survives unchanged and is re-homed to [ADR-002](0002-speech-recognition.md), which is now its canonical location.  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** At setup, Takki detects hardware capability and proactively offers the best LLM tier the machine can comfortably run. Re-evaluates on major events (new hardware, app update, user request). User is never required to know about parameters, quantization, or model selection.

### Rationale

Hardware capability varies enormously across target users — from 10-year-old school computers to modern home machines. The cost of getting this wrong in either direction is real: offering an LLM that won't run smoothly creates frustration; not offering one when the machine can handle it loses available quality.

Asking the user to figure this out themselves is the wrong answer. Most parents and teachers don't know what a parameter count is. The right pattern is: the app does the work, gives a recommendation, the user accepts or declines.

This shifts the LLM from an opt-in technical decision to a guided recommendation. Most users will say yes if offered, because the framing is "make the app better" rather than "configure a language model."

### Hardware Detection

Detection runs at install time and stores the result. Re-runs only on specific triggers (see below).

The detector combines several signals:

- **Available RAM** — `psutil.virtual_memory().available`, measured with Takki running so the number reflects actual headroom, not theoretical total.
- **CPU capability** — A short microbenchmark (small matrix multiplication, ~200ms run) gives a real-world capability number. More reliable than CPU model heuristics, which age poorly.
- **GPU presence** — Detected but only counted if a discrete CUDA-capable GPU with sufficient VRAM is present. Integrated graphics are ignored.
- **Disk space** — Available space in the app data directory. No point recommending a 4 GB model on a machine with 2 GB free.

The combination produces a single recommended tier (0, 1, 2, or 3). Tiers are defined in ADR-004.

### Whisper Model Auto-Selection

The same CPU microbenchmark that gates LLM tiers also selects the Whisper model at startup — no user decision required. Both `tiny` and `base` are bundled in the installer; the app picks the best one the hardware can run comfortably:

| matmul result | Whisper model | Typical latency |
|---------------|---------------|-----------------|
| < ~2ms        | `base`        | ~400–730ms      |
| ~2–10ms       | `tiny`        | ~400–800ms      |
| > ~10ms       | none          | below minimum spec; voice commands unavailable |

Thresholds are derived from measured spike data across three machines (Celeron G555, Ryzen 7 5700U, Intel Core Ultra 7 256V). The ~2ms threshold ensures `base` latency stays under ~800ms on mains power; above it, `tiny` provides comparable latency. The ~10ms floor reflects that SSE4.2-only CPUs (e.g. Celeron) cannot run even `tiny` within an acceptable latency budget.

`small` is explicitly excluded from the installer — it requires 1.4s+ even on the fastest tested CPU and offers no practical benefit over `base` for the narrow intent recognition task without a CUDA GPU.

### Tier Recommendation Flow

After language and visual settings are established, the app presents the recommendation:

**Tier 1 recommended (modest hardware):**
> *"I checked your computer and you have enough power for a smart helper that makes my setup easier and helps me understand you better. It would take about 800 megabytes of download. Want to add it?"*

**Tier 2 or 3 recommended (capable hardware):**
> *"I checked your computer and you have plenty of power. I can use a smart helper that makes me much better at understanding what you say. It would take about 2 gigabytes of download. Or I can use a smaller one that's about 800 megabytes. Or I can run without it. Which would you like?"*

**Tier 0 recommended (constrained hardware):**
> *"Your computer doesn't quite have the room for an extra helper, so I'll run in my simpler mode. Don't worry — I still work great this way."*

The reassurance on Tier 0 is essential. Silent absence of the offer would leave the user wondering if they're missing something.

### Re-Evaluation Triggers

Hardware changes over time — users upgrade RAM, replace machines, install in school labs on different machines. Triggers for re-evaluation:

- **Migration to new hardware** — if the stored machine ID changes, re-check
- **Major Takki update** — re-evaluate in case tier thresholds or available models have changed
- **User request** — settings option "Check if my computer can use a better helper" runs the check on demand
- **Failed LLM operation** — if the configured tier consistently fails to meet latency targets, suggest downgrading

The opposite direction is just as important: if a user upgrades their machine, Takki should notice at next startup and offer the better tier — *"It looks like your computer got faster! I can use a smarter helper now if you'd like."*

### What This Decision Does Not Cover

Tier definitions themselves (which model maps to which tier, what RAM thresholds gate each tier) are covered in ADR-004. This ADR covers the detection mechanism and the user interaction pattern.

### Alternatives Considered

- **Manual user selection:** Rejected. Asks the user to understand technical details that have nothing to do with their goal.
- **Static minimum requirements:** Rejected. Either too conservative (excludes capable users who would benefit) or too aggressive (recommends LLMs to users whose hardware can't run them well).
- **Always-offer regardless of hardware:** Rejected. Frustrating UX on constrained hardware; user installs a slow model, has a bad experience, may abandon the app.
- **Hide the option entirely on low-end hardware:** Rejected. Tier 0 reassurance is preferred over silent absence.
