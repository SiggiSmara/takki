# Curated word-list candidates (spike inputs)

Drop-in curated children's / sight-word lists used by
`spikes/source_validation_spike.py` to validate the positive-curation paradigm
(see the vocabulary research / planned ADR-008 supersede).

**Format:** one word per line, `#` for comments. File order is treated as the
curated *acquisition order*. The spike filters every list to 3–6 letter
lowercase alphabetic words so all strategies are compared on the same band.

**License rule:** only commit lists that are clearly redistributable. The fetched
hunspell *dictionaries* (the real-word gate) are NOT here — they live in
`spikes/data/dict/` and are gitignored.

## Present

- `dolch_en.txt` — Dolch sight words (1936/1948), **public domain**. The English
  curated candidate.

## Pending sourcing

- `grundwortschatz_de.txt` — **not yet sourced.** Plan: the *union of all
  Bundesländer* Grundwortschatz lists (inter-Land contestedness is a non-issue;
  the count of Länder including a word doubles as the consensus introduction
  order). Blocked on the per-source licensing pass, not on content. Until it
  exists, the spike validates German with the dictionary gate only.
