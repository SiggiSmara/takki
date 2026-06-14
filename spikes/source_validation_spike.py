"""
Spike: word-source validation — does positive curation beat wordfreq+dictionary?

Validates the candidate vocabulary sources before the ADR-008 supersede (the
shift from negative-filtering to positive-curation, see
docs/research/anchor-and-introduction-order.md and the project note). It does not
decide the ADR; it produces the evidence the decision needs — including the
failure modes of the *fallback* (wordfreq ∩ dictionary), which turn out to be
real.

Four source STRATEGIES are compared per language, all on the same 3-6 letter
lowercase-alpha band so the comparison is fair:

  S1  wordfreq-only        ADR-008 status quo: top-N short words by frequency,
                           no real-word gate. (wordfreq is lowercased, so
                           ADR-008's "no proper nouns" can't actually be honoured
                           here — itself part of the problem.)
  S2  wordfreq ∩ dict      the fallback: S1 gated by a real dictionary.
  S3  curated              the preferred tier: a curated children's / sight-word
                           list (Dolch for en). File order = acquisition order.
  S4  curated ∪ fallback   seed-then-extend: curated core first, then S2 tail.

Real-word gate (the dictionary):
  Affix-aware hunspell lookup via `spylls` against the wooorm/dictionaries
  hunspell data (en: SCOWL-based; de: igerman98, GPL-2/3). Affix-aware matters:
  a base-form-only set rejects inflections (en `has/years/women`, de
  `war/kann/muss`). And because wordfreq is lowercased while German nouns are
  capitalised, the gate also tries the capitalised form (`haus`→`Haus`).
  Both quirks are findings the ADR must account for, not just spike plumbing.

Metrics:
  * real-word rate     — fraction dictionary-real, for the top-N of each strategy,
                         plus an S1 contamination-by-depth curve.
  * appropriateness    — top-N words flagged by better-profanity (Gap B; English
                         only — mirrors the C9 finding).
  * burial analysis    — where the curated (pedagogically-chosen) words sit in
                         wordfreq's ranking. Answers "would wordfreq-only surface
                         these words early, or does it front-load abstract
                         function words and bury the concrete ones?"
  * first-40 side by side — the words each strategy would actually teach first.
                         The human-eyeball artifact.

Curated lists: loaded from spikes/data/curated/*.txt (see that README). English
ships Dolch (public domain). German awaits the sourced Bundesländer union, so it
runs S1/S2 only until grundwortschatz_de.txt is dropped in.

Run from repo root (headless dev box is fine — fetches hunspell data once if online):
    uv run --with spylls --with better-profanity python spikes/source_validation_spike.py

Output: a printed report plus spikes/results/source_validation_results.txt.
Paste the full stdout back into the Claude Code session.
"""

import sys
import urllib.request
from pathlib import Path

from wordfreq import get_frequency_dict

SPIKES_DIR = Path(__file__).resolve().parent
RESULTS_PATH = SPIKES_DIR / "results" / "source_validation_results.txt"
CURATED_DIR = SPIKES_DIR / "data" / "curated"
DICT_DIR = SPIKES_DIR / "data" / "dict"

MIN_LEN, MAX_LEN = 3, 6
TOP_N = 200            # comparison window for rate/appropriateness metrics
FIRST_N = 40          # side-by-side display
GATE_DEPTH = 5000     # how deep into wordfreq we apply the (cached) gate
DEPTHS = [200, 1000, 3000]
RANK_BUCKETS = [100, 300, 1000, 3000]

WOOORM = ("https://raw.githubusercontent.com/wooorm/dictionaries/"
          "main/dictionaries/{lang}/index.{ext}")

LANGS = {
    "en": {"curated": "dolch_en.txt", "approp": True},
    "de": {"curated": "grundwortschatz_de.txt", "approp": False},
}


def section(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")


# --------------------------------------------------------- candidate pools --

def short(w: str) -> bool:
    return w.isalpha() and MIN_LEN <= len(w) <= MAX_LEN


def wordfreq_short_ranked(lang: str) -> list[str]:
    fd = get_frequency_dict(lang)
    best: dict[str, float] = {}
    for w, f in fd.items():
        wl = w.lower()
        if short(wl) and f > best.get(wl, 0.0):
            best[wl] = f
    return [w for w, _ in sorted(best.items(), key=lambda x: -x[1])]


def load_curated(lang: str) -> list[str] | None:
    path = CURATED_DIR / LANGS[lang]["curated"]
    if not path.exists():
        return None
    seen: set[str] = set()
    out: list[str] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        w = ln.lower()
        if short(w) and w not in seen:
            seen.add(w)
            out.append(w)
    return out


# ------------------------------------------------------- dictionary gate --

def ensure_hunspell(lang: str) -> bool:
    DICT_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("dic", "aff"):
        p = DICT_DIR / f"{lang}.{ext}"
        if not p.exists():
            try:
                print(f"    fetching {lang}.{ext} ...", end="", flush=True)
                urllib.request.urlretrieve(WOOORM.format(lang=lang, ext=ext), p)
                print(" done")
            except Exception as e:
                print(f" FAILED ({e})")
                return False
    return True


def load_gate(lang: str):
    """Returns is_real(word)->bool (affix-aware, casing-tolerant) or None."""
    if not ensure_hunspell(lang):
        return None
    from spylls.hunspell import Dictionary
    d = Dictionary.from_files(str(DICT_DIR / lang))
    cache: dict[str, bool] = {}

    def is_real(w: str) -> bool:
        r = cache.get(w)
        if r is None:
            r = d.lookup(w) or d.lookup(w.capitalize())
            cache[w] = r
        return r

    return is_real


# ------------------------------------------------------------ strategies --

def build_strategies(ranked, is_real, curated):
    s1 = ranked
    if is_real is None:
        s2 = []
    else:
        s2 = [w for w in ranked[:GATE_DEPTH] if is_real(w)]
    strategies = {"S1 wordfreq-only": s1, "S2 wordfreq∩dict": s2}
    if curated:
        cur_set = set(curated)
        strategies["S3 curated"] = curated
        strategies["S4 curated∪fallback"] = curated + [w for w in s2
                                                        if w not in cur_set]
    return strategies


# ------------------------------------------------------------ metrics --

def real_word_rate(pool, is_real, n):
    head = pool[:n]
    if not head or is_real is None:
        return None
    return sum(1 for w in head if is_real(w)) / len(head)


def approp_hits(pool, profanity, n):
    if profanity is None:
        return None
    return [w for w in pool[:n] if profanity.contains_profanity(w)]


def junk_examples(pool, is_real, n, limit=15):
    if is_real is None:
        return []
    return [w for w in pool[:n] if not is_real(w)][:limit]


def burial(curated, ranked, is_real):
    rank = {w: i + 1 for i, w in enumerate(ranked)}
    present = [(w, rank[w]) for w in curated if w in rank]
    absent = [w for w in curated if w not in rank]
    not_real = [w for w in curated if is_real is not None and not is_real(w)]
    ranks = sorted(r for _, r in present)
    buckets = {b: sum(1 for r in ranks if r <= b) for b in RANK_BUCKETS}
    return {
        "n": len(curated),
        "present": len(present),
        "absent": absent,
        "not_real": not_real,
        "buckets": buckets,
        "median": ranks[len(ranks) // 2] if ranks else None,
    }


# ------------------------------------------------------------ reporting --

def print_language(lang, profanity):
    cfg = LANGS[lang]
    section(f"{lang} — source validation")
    ranked = wordfreq_short_ranked(lang)
    is_real = load_gate(lang)
    curated = load_curated(lang)

    print(f"  wordfreq short (3-6) alpha words: {len(ranked)}")
    print(f"  dictionary gate: {'ABSENT' if is_real is None else 'spylls hunspell (affix-aware)'}")
    if curated is None:
        print(f"  curated list: ABSENT ({cfg['curated']}) — running S1/S2 only.")
    else:
        in_dict = (sum(1 for w in curated if is_real(w)) / len(curated)
                   if is_real else None)
        print(f"  curated list: {len(curated)} words (3-6 band) from {cfg['curated']}")
        if in_dict is not None:
            print(f"  curated ∩ dictionary: {in_dict:.0%} "
                  f"(sanity — curated should be almost all real)")

    strategies = build_strategies(ranked, is_real, curated)

    # Metric table -----------------------------------------------------------
    section(f"{lang} — metrics over top {TOP_N}")
    hdr = f"  {'strategy':<22}  {'real-word rate':>14}  {'approp. hits':>12}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for name, pool in strategies.items():
        rwr = real_word_rate(pool, is_real, TOP_N)
        hits = approp_hits(pool, profanity, TOP_N)
        rwr_s = "n/a" if rwr is None else f"{rwr:.0%}"
        hits_s = "n/a" if hits is None else str(len(hits))
        note = "" if len(pool) >= TOP_N else f"  (only {len(pool)} words)"
        print(f"  {name:<22}  {rwr_s:>14}  {hits_s:>12}{note}")

    # S1 contamination by depth ---------------------------------------------
    if is_real is not None:
        cells = "   ".join(
            f"top{d}: {real_word_rate(strategies['S1 wordfreq-only'], is_real, d):.0%}"
            for d in DEPTHS)
        print(f"\n  S1 real-word rate by depth:  {cells}")
        junk = junk_examples(strategies["S1 wordfreq-only"], is_real, GATE_DEPTH)
        print(f"  non-words S1 admits (within top {GATE_DEPTH}, gate removes): "
              f"{', '.join(junk) if junk else '(none)'}")

    if profanity is not None:
        s1_hits = approp_hits(strategies["S1 wordfreq-only"], profanity, TOP_N)
        print(f"\n  S1 appropriateness hits in top {TOP_N}: "
              f"{', '.join(s1_hits) if s1_hits else '(none)'}")
        if curated:
            c_hits = approp_hits(strategies["S3 curated"], profanity, len(curated))
            print(f"  S3 curated appropriateness hits (whole list): "
                  f"{', '.join(c_hits) if c_hits else '(none)'}")

    # Burial analysis --------------------------------------------------------
    if curated and is_real is not None:
        b = burial(curated, ranked, is_real)
        section(f"{lang} — burial: where curated words sit in wordfreq ranking")
        print(f"  curated words (3-6 band): {b['n']}   "
              f"present in wordfreq: {b['present']}   absent: {len(b['absent'])}")
        if b["median"] is not None:
            print(f"  median wordfreq rank of curated words: {b['median']}")
        print("  curated words within wordfreq top-N:  "
              + "   ".join(f"≤{k}: {b['buckets'][k]}" for k in RANK_BUCKETS))
        if b["absent"]:
            print(f"  wordfreq never lists (3-6 band): {', '.join(b['absent'][:20])}"
                  f"{' ...' if len(b['absent']) > 20 else ''}")
        if b["not_real"]:
            print(f"  dictionary rejects (gate gaps): {', '.join(b['not_real'][:20])}")

    # First-N side by side ---------------------------------------------------
    section(f"{lang} — first {FIRST_N} words each strategy would teach")
    for name, pool in strategies.items():
        print(f"\n  {name}:")
        words = pool[:FIRST_N]
        for i in range(0, len(words), 10):
            print("    " + "  ".join(f"{w:<9}" for w in words[i:i + 10]).rstrip())


# ---------------------------------------------------------------- main --

class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s: str) -> int:
        for st in self.streams:
            st.write(s)
        return len(s)

    def flush(self) -> None:
        for st in self.streams:
            st.flush()


def main() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        from better_profanity import profanity
        profanity.load_censor_words()
    except Exception:
        profanity = None

    orig = sys.stdout
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        sys.stdout = _Tee(orig, fh)
        try:
            print("Word-Source Validation Spike")
            print(f"Python: {sys.version.split()[0]}   Platform: {sys.platform}")
            print(f"Languages: {', '.join(LANGS)}   band: {MIN_LEN}-{MAX_LEN}   "
                  f"top-N: {TOP_N}")
            approp_state = ("active" if profanity else
                            "ABSENT (Gap-B metric skipped — add --with "
                            "better-profanity)")
            print(f"better-profanity: {approp_state}")
            for lang in LANGS:
                print_language(lang, profanity if LANGS[lang]["approp"] else None)
            print("\n" + "=" * 78)
            print("  DONE")
            print("=" * 78)
            print(f"\n  Results written to {RESULTS_PATH}")
            print("  Paste the full output above back into the Claude Code session.")
        finally:
            sys.stdout = orig


if __name__ == "__main__":
    main()
