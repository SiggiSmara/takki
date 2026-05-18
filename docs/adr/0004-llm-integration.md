# ADR-004: LLM Integration

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Local LLM only, optional, hardware-adaptive (see ADR-018). Never used for real-time encouragement. Used only as a tertiary fallback for intent recognition (see ADR-017) when the rule-based pipeline returns no confident match, primarily during setup. Online/cloud LLMs are explicitly out of scope.

### Rationale

LLMs add genuine value in specific places but introduce risk if overused. After detailed evaluation:

**Where LLMs help (and are used):**
- Fallback intent recognition during setup, when the child uses phrasing not anticipated by the rule-based pipeline
- Tertiary fallback during steady-state voice navigation, for unusual phrasings

**Where LLMs are explicitly NOT used:**

*Real-time encouragement generation.* Latency budget is essentially zero — the child completes a word and expects positive feedback immediately. Even on capable hardware, local LLM generation of a short encouragement phrase takes seconds; on the target older hardware it takes 4–10 seconds. This breaks the encouragement loop entirely. Encouragement uses a rule-based phrase bank per language with light randomization (see ADR-012). The "variety problem" is solved by authoring enough phrases — 30–50 per language is sufficient for any practical session length.

*Word list filtering for age-appropriateness.* LLMs have baked-in cultural bias, inconsistent results between runs, and impose value judgements that belong to parents and teachers, not the software. See ADR-008.

*Online/cloud LLM integration.* Rejected entirely. The benefits are concentrated in setup (a one-time event), but cloud integration requires the user to configure API keys, accept network dependency, and accept that their child's voice transcriptions leave the device. The trade is wrong: the users who would most benefit from a smoother setup are the least likely to do additional configuration to get there. Cloud LLM support would also contradict the fully-offline principle, add testing and maintenance burden, and create privacy concerns disproportionate to its benefit. Users who want this can fork the project.

### LLM Tier Model

Three optional tiers, with the offered tier determined automatically by hardware detection at setup (see ADR-018):

**Tier 0 — No LLM (default for all users)**
- Rule-based intent recognition (ADR-017) and rule-based encouragement
- Works on any 8 GB RAM machine of any reasonable age
- No download, no runtime cost beyond the base app

**Tier 1 — Small LLM (1–1.5B parameters)**
- For machines with ~3 GB+ free RAM after Takki loads, CPU roughly 7+ years old or newer
- Model: Llama 3.2 1B Q4 or Qwen 2.5 1.5B Q4 in GGUF format
- Download: ~700 MB – 1.2 GB on demand
- Intent recognition latency: 1–3 seconds on target hardware

**Tier 2 — Medium LLM (3–4B parameters)**
- For machines with ~5 GB+ free RAM after Takki loads, CPU roughly 5+ years old or newer
- Model: Llama 3.2 3B Q4 or Gemma 3 4B Q4
- Download: ~2–2.5 GB on demand
- Intent recognition latency: under 1.5 seconds; quality noticeably better than Tier 1

**Tier 3 — Larger LLM (7–8B parameters)**
- For modern machines or machines with a capable discrete GPU
- Model: Qwen 2.5 7B Q4 or Llama 3.1 8B Q4
- Download: ~4–5 GB on demand
- Intent recognition latency: under 1 second; approaches frontier-model quality on narrow tasks

The runtime is `llama-cpp-python` — pure Python bindings to `llama.cpp`, fully offline, cross-platform.

### Why Not Fine-Tune a Takki-Specific Model

Considered and deferred. A fine-tuned 1B model can achieve 99%+ intent accuracy on narrow domains (e-commerce benchmarks confirm this), but requires synthetic dataset generation per language, single-GPU training infrastructure, and ongoing maintenance as intents evolve. For a hobby project at this stage, generic instruction-tuned models are good enough as a fallback layer behind the rule-based pipeline. Fine-tuning remains a viable future direction if usage grows and the rule-based pipeline shows systematic gaps.

### Alternatives Considered

- **LLM as core dependency:** Rejected. Breaks fully-offline principle, adds hardware requirements, excludes families with older equipment.
- **No LLM at all:** Viable; would work but loses the fallback option for unusual phrasings during setup. The hardware-adaptive opt-in pattern means no user is forced to use an LLM, so this provides upside without imposing cost on constrained machines.
- **Cloud/online LLM:** Rejected. See above.
