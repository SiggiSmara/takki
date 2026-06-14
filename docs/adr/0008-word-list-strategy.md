# ADR-008: Word List Strategy

**Status:** Superseded in part by [ADR-029](0029-word-selection-and-curation.md) — the word-*selection* decision is replaced; the family-override file and no-LLM-filtering stance are retained.  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Algorithmic default derived from `wordfreq` (top N words, 3-6 letters, no proper nouns). Parent/teacher override via a plain text file with addition and exclusion syntax. No LLM filtering. No bundled curriculum word lists.

### Rationale

**On age-appropriateness filtering:**

Age-appropriateness is not a linguistic property — it is a cultural and values judgement that varies by family, community, and country. LLM filtering was explicitly evaluated and rejected because:
- LLMs have baked-in Anglo-American cultural bias
- Results are inconsistent between runs (not reproducible)
- Over-filtering removes common useful words; under-filtering causes parent complaints
- The app should not be making values decisions on behalf of families

The algorithmic filter (frequency + length) produces a vocabulary that is overwhelmingly uncontroversial in practice — the genuinely contested words tend to be longer and lower-frequency.

**On bundled curriculum word lists:**

National curriculum vocabulary lists (e.g., German Grundwortschatz, UK National Curriculum word lists) were considered but rejected as the primary approach because:
- Licensing varies by country and requires per-language legal research
- Maintenance burden when lists are updated by education ministries
- Inconsistency between countries in what constitutes a "curriculum list"

They remain a valid contribution path — a contributor can supply a curated word list for their language — but are not required.

**On parent override:**

The plain text override file supports two operations:

```
# Words to add (personally meaningful words for this child)
oma
opa
luna

# Words to exclude
- krieg
- tod
```

The file is processed at every startup. The result is confirmed audibly so visually impaired parents using screen readers know it was applied. This puts values decisions where they belong — with the family — without requiring any code changes.
