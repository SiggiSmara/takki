# ADR-031: No LLM Integration

**Status:** Accepted  
**Date:** 2026-07-05

> Part of the [Takki architecture](../architecture.md). Supersedes [ADR-004](0004-llm-integration.md) (LLM integration) and [ADR-018](0018-hardware-adaptive-llm-tiering.md) (hardware-adaptive LLM tiering) — ADR-018's Whisper model auto-selection survives and re-homes to [ADR-002](0002-speech-recognition.md). Amends [ADR-017](0017-voice-command-and-intent-recognition.md) (Layer 4 removed), [ADR-019](0019-testing-strategy-and-io-isolation.md) (`LLMRunner` dropped), [ADR-012](0012-audio-feedback-design.md), and [ADR-021](0021-voice-activity-detection.md) (passing mentions).

---

**Decision:** Takki ships with **no LLM integration** — not as a core dependency, not as an optional download, not as a hardware-gated fallback. ADR-004's "No LLM at all" alternative, judged *viable* at the time, is now adopted. The intent pipeline (ADR-017) is Layers 1–3 rule-based only. `llama-cpp-python`, the tier model (0–3), the tier-offer setup flow, hardware-based tier detection, and the per-tier model downloads are all removed from the plan. The Protocol boundary (ADR-019) remains the path for anyone who disagrees: an LLM intent fallback is a downstream fork's Protocol implementation, not a Takki feature.

### Rationale

The design had already said no to an LLM at every decision point but one:

- No LLM word filtering ([ADR-008](0008-word-list-strategy.md), reaffirmed by [ADR-029](0029-word-selection-and-curation.md))
- No LLM encouragement generation (ADR-004 itself — the latency budget is zero)
- No cloud/online LLM (ADR-004 — privacy, offline principle)
- No fine-tuned Takki model (ADR-004 — deferred as not worth the infrastructure)
- No LLM by default (Tier 0 was the default for every user)

The single surviving use was a *tertiary* fallback for intent recognition — firing only when Layers 1–3 all miss, only on machines that pass a hardware gate, only if the user accepted a large optional download. Removing it makes the design say one thing instead of five variations of it.

**The failure mode it addressed is already handled twice.** When all layers miss, ADR-017 specifies an explicit "I didn't catch that — try again" (better than guessing wrong, by ADR-017's own analysis), and after three failed attempts at the same step the app switches to a simpler interaction (spoken-number selection). A child who says "can you slow down a bit" and isn't understood says "slower" on the second try. The LLM bought a slightly smoother recovery from a rare miss — a recovery path that already exists in rule-based form.

**What it cost:**

- **The largest artifacts in the product, for its least-exercised feature.** Tier downloads ran 700 MB–5 GB against a ~340 MB installer. The download offer also contradicted minimal setup friction: an onboarding interruption asking a parent to approve a gigabyte-scale download for a feature they cannot evaluate.
- **Whole subsystems existing only to serve it.** Hardware capability detection, the tier recommendation flow with its four re-evaluation triggers, per-tier model download and storage management, and `llama-cpp-python` (a native-code wheel) inside the PyInstaller bundle.
- **CI and maintenance weight.** Nightly "all LLM tiers" runs; prompt and quality maintenance across four tier models and ~40 languages.
- **Wrong-match risk where it hurts most.** Children's speech transcribed imperfectly by Whisper, then unmatched by Layers 1–3, is exactly the input where a generic instruction-tuned model is most likely to guess. ADR-017's setup failure-mode analysis ranks wrong-match success as worse than clear failure; Layer 4 was the layer most prone to it, and its 1–3 s latency meant even a *correct* guess arrived awkwardly late for a child.

**The benefit was hypothetical.** There is no evidence Layers 1–3 plus context-aware intent scoping are insufficient. The MEOWCROPHONE result that motivated the pipeline (46.4% → 82.8% for child speech) attributes the gain to the layered rule-based matching — phonetic matching in particular — not to generative fallback. If the Beta pilot shows systematic gaps, the honest fixes are richer keyword/synonym YAML (a native-speaker contribution path that costs nothing at runtime) and better context scoping, before anything model-shaped.

### What survives, and where it moves

- **Whisper model auto-selection** (matmul microbenchmark → `tiny`/`base`/none) was specified in ADR-018 only because it shared the CPU microbenchmark with tier detection. It is unaffected by this decision and re-homes to [ADR-002](0002-speech-recognition.md), which was always its natural owner. Implementation moves from V1 (where it sat coupled to the tier offer) to the Beta `faster-whisper` wrapper — it is needed the moment Whisper lands.
- **`HardwareProbe`** (ADR-019) stays: it is the seam for the microbenchmark that drives Whisper selection and the below-minimum-spec ("no voice commands") determination.
- **The fork path.** ADR-019's Protocol boundary is the public extension surface. A downstream fork that wants an LLM intent layer, generated encouragement, or a cloud adapter implements the relevant Protocol; nothing in Takki's architecture obstructs it, and nothing in Takki's repo maintains it.

### Consequences — document amendments

- **ADR-004** → Superseded. Its *negative* decisions (no cloud LLM, no encouragement generation, no word filtering) are carried forward here.
- **ADR-018** → Superseded. Whisper auto-selection section re-homed to ADR-002.
- **ADR-017** → Layer 4 removed; pipeline is Layers 1–3 + explicit no-match response + three-strikes simpler-path fallback, all previously designed.
- **ADR-019** → `LLMRunner`/`LlamaCppRunner`/`ScriptedLLMRunner` dropped from the Protocol catalog; "all LLM tiers" dropped from nightly CI; `llama-cpp-python` dropped from the dependency list. `HardwareProbe` retained.
- **ADR-012, ADR-021** → passing LLM mentions (optional encouragement plugin, install-size comparison) corrected.
- **architecture.md** → component diagram, design principles, out-of-scope table, ADR index updated.
- **roadmap.md** → V1 items "hardware capability detection", "LLM tier offer flow + `llama-cpp-python` + per-tier model download", and "intent pipeline Layer 4" removed; Whisper auto-selection folded into the Beta `faster-whisper` wrapper step.
- **CLAUDE.md** → LLM rules and technology-table row replaced with the no-LLM rule.

### Alternatives Considered

- **Keep the tiered optional fallback as designed:** Rejected for the costs above. Five subsystems and the product's largest downloads serving a rare, already-mitigated failure mode.
- **Keep Layer 4 but only at a single small tier (drop tiers 2–3):** Rejected. Retains every subsystem (detection, offer flow, download, packaging, fork-grade maintenance) while shrinking the only part that was cheap to vary.
- **Fine-tuned Takki-specific intent model:** Already deferred in ADR-004; rejected with the rest. If the pilot exposes systematic intent gaps, richer YAML synonym banks are the first response, not model training.
- **Cloud/online LLM:** Rejected in ADR-004; that rejection is unchanged and carried forward.
