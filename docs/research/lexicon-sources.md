# Research note: word-lexicon sources and licenses

> **Status:** Research (inputs to [vocabulary-source-plan.md](vocabulary-source-plan.md) / the ADR-008 supersede)
> **Date:** 2026-06-14
> **Scope:** children's lexicons first, general frequency lexicons second, plus research infrastructure (CLARIN et al.). Focus on whether each can be **redistributed inside Takki** (a freely-distributed app), not just "is it free to look at."

## The finding that reframes the licence question

The binding constraint is **non-commercial / academic-only licensing — not MIT-vs-GPL.**

- **Usable in the product:** public domain, permissive (MIT/BSD/Apache), and **copyleft** (GPL, CC-BY, CC-BY-SA). The copyleft ones only ask for attribution and (for SA/GPL) share-alike; they permit *any* use, including bundling in a free app.
- **Not usable:** **CC-BY-NC** (non-commercial) and **CLARIN ACA/RES** (academic/research-only). **No application licence fixes these** — they forbid the redistribution/any-purpose use we need.

Consequence for the earlier MIT→GPL question: switching to GPL only unlocks the *copyleft* data, which is already the easy case (copyleft data is bundle-compatible via aggregation + attribution anyway). It does **nothing** for the NC/academic research lexicons — and the best *children's* lexicons tend to be exactly those. So the app-licence choice is a values/clarity decision, not the thing that unblocks the good children's data.

## 1. Children's lexicons (specialised, age-targeted)

A clear family of grade-level "children's reader" lexicons exists, built the same way (corpora of children's books / school readers, age-banded), but each instance is licensed differently:

| Resource | Lang | What | Licence | Usable in product? |
|---|---|---|---|---|
| **childLex** | de | 10M-word children's-book corpus, age bands 6–8 / 9–10 / 11–12 | **GPL-3.0** (confirmed via OSF API) | **Yes** ✓ (copyleft, *not* NC) — GPL-in-MIT tension; ship per [ADR-015](../adr/0015-piper-voice-model-distribution.md) |
| **ChildPoeDE** | de | 1082 German children's *poems*; word-frequency table + token metadata (onomatopoeia, sonority) | **CC0** (Zenodo; poem texts withheld) | **Yes** ✓ — niche/small, supplementary; the one friction-free de source |
| **MANULEX** | fr | grade-level lexicon from 54 elementary readers | **CC-BY-NC-SA 3.0** | **No** — NC. Permission on request (bernard.lete@manulex.org) |
| **LEXIN** | es | kindergarten / grade-1 reader lexicon | academic resource, licence unconfirmed | **Assume no** until verified |
| **ESCOLEX** | pt (PT) | grade-level lexicon from 171 elementary/middle textbooks, ages 6–11 (P-PAL group) | academic, licence unconfirmed | verify (assume restricted); pt not a current target |
| **TCBLex** | fi | 11M-token children's literary texts, ages 7–15, 14 age/genre sub-lexicons, incl. age-of-first-encounter | **CC-BY-4.0** (Zenodo `10.5281/zenodo.15655580`) | **Yes** ✓ — best-licensed of the family |
| **CYP-LEX** | en (UK) | books read by children / young people, UK | academic, licence unconfirmed | verify |
| Dolch sight words | en | 220 service words + 95 nouns (1936/48) | **Public domain** | **Yes** ✓ (already used) |
| Fry "Instant Words" | en | 1000 high-frequency words | compilation copyright unclear | verify before use |
| Children's Printed Word DB | en (UK) | 5–9 yr printed-word frequencies | academic | verify |
| Oxford Children's Corpus | en | large children's corpus | **proprietary/commercial** | no |
| CHILDES / TalkBank | many | *spoken* child language | academic (CC-BY-NC-SA-style rules) | no (and it's spoken, not reading) |

Takeaway: **German and Finnish are well-covered** — childLex (de, **GPL-3.0**) and **TCBLex (fi, CC-BY)** are usable. **French (MANULEX) is NC**; Spanish (LEXIN) likely restricted → author permission or skip. English relies on the **public-domain Dolch** core (the UK CYP-LEX exists but its licence is unconfirmed).

## 2. General frequency lexicons

| Resource | Coverage | Licence | Usable? |
|---|---|---|---|
| **wordfreq** | ~40 langs | Apache-2.0 (code) + **CC-BY-SA-4.0** (data) | **Yes** ✓ — our [ADR-007](../adr/0007-language-data-word-frequency.md) source. Note: **frozen ~2021** (SUNSET), won't be updated |
| **SUBTLEX-US** | en | Brysbaert grants distribution for **any purpose** w/ attribution (≈CC-BY-SA) | **Yes** ✓ (already inside wordfreq) |
| SUBTLEX-UK | en | CC-BY | yes |
| SUBTLEX-CY (Welsh), some others | per lang | **CC-BY-NC** | no — varies per paper, check each |
| **FrequencyWords** (hermitdave, OpenSubtitles) | many | MIT (code) + **CC-BY-SA-4.0** (data) | **Yes** ✓ |
| Lexique | fr | open ("GNU-like"; likely CC-BY-SA/ODbL) | likely yes — verify |
| Leipzig Corpora Collection | many | commonly **CC-BY-NC** | likely no — verify |
| dlexDB (DWDS-based) | de | academic | verify |
| **SCOWL** (en hunspell) | en | permissive (BSD-ish, mixed) | **Yes** ✓ — the gate dict |
| **igerman98** (de hunspell) | de | **GPL-2/3** | yes (copyleft) — but GPL-in-MIT-binary tension; ship separately per [ADR-015](../adr/0015-piper-voice-model-distribution.md) |
| Wiktionary / Wikidata lexemes | many | CC-BY-SA / CC0 | **Yes** ✓ |

## 3. Initiatives / infrastructure

- **CLARIN** (clarin.eu) — European research infrastructure; ~60 wordlists across languages. Three licence categories: **PUB** (publicly redistributable, incl. in products), **ACA** (research-only, federated login), **RES** (research + rights-holder permission). **Only PUB is product-usable.** Treat CLARIN as a discovery layer filtered to PUB. National nodes are relevant to our languages: **Kielipankki** (fi), **CLARIN-D** (de), **CLARIN-PL** (pl), **CLARIN-IS** (is).
- **Icelandic LT Programme / málföng.is (CLARIN-IS)** — Iceland's national programme deliberately released its language resources under **open licences (CC-BY / MIT)**. A bright spot for `is`, which otherwise has thin commercial resources — verify per resource.
- **openlexicon** (openlexicon.fr, github `chrplr/openlexicon`) — aggregates many lexicon datasets (SUBTLEX, Lexique, Manulex, …) **with per-dataset licence READMEs**. Best single meta-source for cross-checking licences.
- **OPUS / OpenSubtitles** — the raw corpus behind FrequencyWords. **META-SHARE / ELRA / LDC** — catalogues, often paid/restrictive (ACA/RES-like).

## 4. Implications for Takki

- **A product-usable stack already exists and is good:** wordfreq + SUBTLEX-US + FrequencyWords (all CC-BY-SA, attribution + share-alike) for frequency; SCOWL / hunspell (+ igerman98 GPL) for the real-word gate; **Dolch (PD)** + **childLex (de, GPL-3.0)** + **TCBLex (fi, CC-BY)** for children's curation; Wiktionary (CC-BY-SA) supplementary.
- **For NC children's lexicons** (MANULEX fr, possibly LEXIN es): (a) request author permission (MANULEX explicitly offers it), (b) derive a child-appropriate ordering from product-usable general data (SUBTLEX/wordfreq/FrequencyWords) + curation, or (c) use **official curricular Grundwortschätze** — German curricular lists issued as decrees may be **amtliche Werke (§5 UrhG) = not copyrighted** (verify per state); this could make the "union of Bundesländer" both high-quality *and* licence-clean.
- **How these corpora get built (EU TDM):** modern children's lexicons (e.g. TCBLex) are mined from copyrighted books under the EU **text-and-data-mining exception** (Directive 2019/790 Art. 3) — a *research-organisation* right — then released as the aggregate lexicon (often CC-BY) but not the full corpus. Implication: Takki **cannot rely on the research-TDM exception itself** (it isn't a research org); consume already-released open lexicons rather than mine books.
- **Beta (en + de) is covered** with confirmed-usable sources: Dolch (PD) + childLex (de) + wordfreq/SUBTLEX + SCOWL/igerman98. **Finnish** now also has a CC-BY children's lexicon (TCBLex) — a sign the newer ones are landing on permissive licences.
- **On the licence switch:** **DECIDED (2026-06-14) — Takki went MIT→GPLv3.** Most usable lexicon data is copyleft (CC-BY-SA / GPL), and German's best sources (childLex, igerman98) are GPL, so GPLv3 lets them bundle cleanly. NC/academic data stays excluded under any app licence.
- **To verify next:** LEXIN (es), ESCOLEX (pt), CYP-LEX (en/UK), Lexique (fr), Leipzig licences; whether target German curricular Grundwortschätze qualify as §5 UrhG.

## Sources

- childLex — [paper](https://link.springer.com/article/10.3758/s13428-014-0528-1), [author downloads](https://sites.google.com/view/saschaschroeder/downloads), [OSF](https://osf.io/tqgjs/)
- [MANULEX](https://www.manulex.org/) (CC-BY-NC-SA-3.0); [LEXIN paper](https://link.springer.com/article/10.3758/BRM.41.4.1009)
- [TCBLex](https://pmc.ncbi.nlm.nih.gov/articles/PMC12528317/) (CC-BY-4.0; [Zenodo](https://doi.org/10.5281/zenodo.15655580); [code](https://github.com/TurkuNLP/TCBLex)); [ESCOLEX paper](https://link.springer.com/article/10.3758/s13428-013-0350-1); [CYP-LEX paper](https://www.researchgate.net/publication/376755434)
- [ChildPoeDE](https://openhumanitiesdata.metajnl.com/articles/10.5334/johd.102) — frequency table/metadata **CC0** ([Zenodo](https://zenodo.org/record/7936860)); poem texts withheld
- [wordfreq](https://github.com/rspeer/wordfreq) (Apache + CC-BY-SA, SUNSET); [FrequencyWords](https://github.com/hermitdave/FrequencyWords) (MIT + CC-BY-SA)
- SUBTLEX — [crr.ugent.be](http://crr.ugent.be/programs-data/subtitle-frequencies); [openlexicon SUBTLEX-US README](https://github.com/chrplr/openlexicon/blob/master/datasets-info/SUBTLEX-US/README-SUBTLEXus.md)
- CLARIN — [licence categories](https://www.clarin.eu/content/licenses-and-clarin-categories), [licensing framework](https://www.clarin.eu/content/clarin-licensing-framework), [wordlists family](https://www.clarin.eu/resource-families/lexical-resources-wordlists)
- [openlexicon](http://openlexicon.fr/)
