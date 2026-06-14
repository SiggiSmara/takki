"""
Spike: key-introduction ORDER comparison — engagement vs anchor cost

Quantifies the prize discussed in docs/research/anchor-and-introduction-order.md:
does growing the keyboard map from the F/J tactile bumps "by usefulness"
(vowels early) bring real words online sooner than drilling the whole home row
first — and what does it cost in anchor stability?

Five orderings are compared, per language:

  O1  home-row -> freq (status quo)
        ADR-023 algorithm C. Whole home-row anchor first, then
        frequency-leader-per-hand. The current design and the baseline.
  O2  F+J -> vowel-priority
        Anchor on the two index bumps only, then introduce keys with vowels
        pulled to the front, one per hand per round.
  O3  coverage-greedy (no anchor)
        No anchor at all; at each step add the key that unlocks the most real-
        word frequency. The engagement UPPER BOUND — what's achievable if we
        ignore anchoring and motor balance entirely.
  O4  whole-home-row -> vowel-first
        Same whole-home-row anchor as O1, but vowel-first afterwards. Isolates
        "what comes after the anchor" (vs O1) and "anchor size" (vs O2).
  O5  F+J -> full-finger-coverage  (the per-child-calibration order)
        Anchor on F+J, then round-robin across all eight fingers so every
        finger gets early reach (explore each finger's range, don't fill a
        row). The specific idle key per finger is left to per-child
        calibration in production; the spike stands in with the highest-
        frequency key per finger.

Three metrics per ordering (see the research note):

  1. Step at which N real 3-letter words come online (N = 1/10/25/50).
     "Real" = the spike's non-word filter applied (acronyms/initialisms and
     consonant-only strings removed), because the word-list reality spike
     showed wordfreq's short high-frequency band is contaminated with junk
     (sms, dsl, fff, fda, aka, French AZERTY's 100%-non-word home row).
  2. Weighted real-word coverage at each step (fraction of real 3-6 letter
     word frequency mass that is typeable).
  3. Anchor cost: how many home-row keys are known before the first off-home
     reach is forced (= position of the first non-home key in the order).

The layout model, native-alphabet filtering, coverage-curve machinery and the
status-quo / coverage-greedy algorithms are imported from
key_introduction_order_spike.py so the key sets match the engine.

Run from repo root (headless dev box is fine — no hardware needed):
    uv run python spikes/intro_order_comparison_spike.py

Optional stricter English real-word check (removes pronounceable acronyms like
fda/aka/afl by intersecting with a dictionary):
    uv run --with english-words python spikes/intro_order_comparison_spike.py

Output: a printed report plus spikes/results/intro_order_comparison_results.txt.
Paste the full stdout back into the Claude Code session.
"""

import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from wordfreq import get_frequency_dict

SPIKES_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKES_DIR))

import key_introduction_order_spike as kio  # noqa: E402

RESULTS_PATH = SPIKES_DIR / "results" / "intro_order_comparison_results.txt"

# Same language spread as the word-list reality spike. en is the Beta headline.
LAYOUT_BUILDERS = {
    "en": kio.build_en,
    "de": kio.build_de,
    "es": kio.build_es,
    "fr": kio.build_fr,
    "is": kio.build_is,
    "fi": kio.build_fi,
    "pl": kio.build_pl,
}

MIN_LEN, MAX_LEN = 3, 6           # Layer-2 word band (ADR-010)
REAL3_TIERS = [1, 10, 25, 50]     # distinct real 3-letter words "online"
COV_MILESTONES = [0.10, 0.25, 0.50, 0.75, 0.90]
FIRST_WORDS_LIMIT = 8

# Bases treated as vowels (after stripping diacritics). y included — it carries
# vowel duty in fi/is/de and its presence still signals a pronounceable token.
VOWEL_BASES = set("aeiouyåäöæøœ")

# Illustrative only: obvious English initialisms / internet-isms that survive
# the vowel test. NOT a real blocklist — the production fix is the ADR-008
# word-list filter. Kept short and English-scoped so the demo output is honest
# without claiming a curated dictionary.
INITIALISMS = {
    "aka", "fda", "afl", "fbi", "cia", "ceo", "abc", "cbs", "nfl", "nba",
    "lol", "lmao", "lmfao", "imo", "btw", "faq", "diy", "ceo", "usa", "url",
}


# --------------------------------------------------------- real-word filter --

def is_vowel_char(c: str) -> bool:
    base = unicodedata.normalize("NFD", c)[0]
    return base in VOWEL_BASES


def is_real_word(w: str, dict_set: set[str] | None) -> bool:
    """Heuristic 'is this a real word' test for the contaminated short band.

    Universal rules (all languages): reject all-same-letter strings (aaa, fff)
    and consonant-only strings (sms, dsl) — the latter is the bulk of the home-
    row junk and all of the French-AZERTY home row. Plus a tiny illustrative
    initialism blocklist. When a dictionary is supplied (English, optional) the
    word must additionally appear in it, which removes pronounceable acronyms.
    """
    if len(set(w)) == 1:
        return False
    if not any(is_vowel_char(c) for c in w):
        return False
    if w in INITIALISMS:
        return False
    if dict_set is not None and w not in dict_set:
        return False
    return True


def load_english_dict() -> set[str] | None:
    p = Path("/usr/share/dict/words")
    if p.exists():
        return {
            ln.strip().lower()
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines()
            if ln.strip().isalpha()
        }
    try:
        from english_words import get_english_words_set
        return get_english_words_set(["web2"], lower=True)
    except Exception:
        try:
            from english_words import english_words_lower_set
            return set(english_words_lower_set)
        except Exception:
            return None


# ------------------------------------------------------ corpus / word pools --

def build_real_word_corpus(layout, freq_dict, dict_set):
    """kio.CorpusIndex over real words of length MIN_LEN..MAX_LEN only."""
    char_set = frozenset(layout.graphemes.keys())
    prereqs: list[frozenset[str]] = []
    freqs: list[float] = []
    penalties: list[float] = []
    key_to_words: dict[str, list[int]] = defaultdict(list)
    total = 0.0
    for w, f in freq_dict.items():
        if not w.isalpha():
            continue
        wl = w.lower()
        if not (MIN_LEN <= len(wl) <= MAX_LEN):
            continue
        if not frozenset(wl) <= char_set:
            continue
        if not is_real_word(wl, dict_set):
            continue
        pre = frozenset(k for c in wl for k in layout.graphemes[c].prereq_keys)
        strokes = sum(layout.graphemes[c].keystrokes for c in wl)
        idx = len(prereqs)
        prereqs.append(pre)
        freqs.append(f)
        penalties.append(len(wl) / strokes)
        for k in pre:
            key_to_words[k].append(idx)
        total += f
    return kio.CorpusIndex(prereqs, freqs, penalties, dict(key_to_words),
                           total or 1.0)


def three_letter_pools(freq_dict, native_graphemes, dict_set):
    """(real_3l_sorted_by_freq, raw_3l_count) — raw count shows contamination."""
    real: list[tuple[str, float]] = []
    raw = 0
    for w, f in freq_dict.items():
        if not w.isalpha() or len(w) != 3:
            continue
        wl = w.lower()
        if not frozenset(wl) <= native_graphemes:
            continue
        raw += 1
        if is_real_word(wl, dict_set):
            real.append((wl, f))
    real.sort(key=lambda x: -x[1])
    return real, raw


# ------------------------------------------------------ selection helpers --

def is_vowel_key(name: str, layout) -> bool:
    return (kio.is_letter_key(name, layout)
            and is_vowel_char(layout.graphemes[name].char))


def _take_anchor(layout, out: list[str], used: set[str]) -> None:
    for n in ("f", "j"):
        if n in layout.keys and n not in used:
            out.append(n)
            used.add(n)


def _append_leftover(layout, g_freq, out: list[str], used: set[str]) -> None:
    leftover = sorted(
        [n for n in layout.keys if n not in used],
        key=lambda n: -kio.key_aggregate_freq(n, layout, g_freq),
    )
    out.extend(leftover)
    used.update(leftover)


def _side_candidates(layout, used, side_fingers):
    return [n for n, k in layout.keys.items()
            if n not in used and k.finger in side_fingers
            and kio.is_letter_key(n, layout)]


# ----------------------------------------------------------- the orderings --

def ordering_o1(layout, corpus, g_freq) -> list[str]:
    return kio.algo_freq_per_hand(layout, g_freq)


def ordering_o2(layout, corpus, g_freq) -> list[str]:
    out: list[str] = []
    used: set[str] = set()
    _take_anchor(layout, out, used)
    while True:
        progressed = False
        for side in (kio.LEFT_FINGERS, kio.RIGHT_FINGERS):
            cands = _side_candidates(layout, used, side)
            if not cands:
                continue
            best = max(cands, key=lambda n: (is_vowel_key(n, layout),
                                             kio.key_aggregate_freq(n, layout, g_freq)))
            out.append(best)
            used.add(best)
            progressed = True
        if not progressed:
            break
    _append_leftover(layout, g_freq, out, used)
    return out


def ordering_o3(layout, corpus, g_freq) -> list[str]:
    """Coverage-greedy with no anchor — the engagement upper bound."""
    out: list[str] = []
    known: set[str] = set()
    word_missing: list[set[str]] = [set(p) for p in corpus.word_prereqs]
    while True:
        candidates = [n for n in layout.keys if n not in known]
        if not candidates:
            break
        unlock_gain, contrib = kio._score_candidates(word_missing, corpus)
        best = kio._coverage_pick(candidates, unlock_gain, contrib, layout)
        out.append(best)
        known.add(best)
        for wi in corpus.key_to_words.get(best, ()):
            word_missing[wi].discard(best)
    return out


def ordering_o4(layout, corpus, g_freq) -> list[str]:
    out = kio.home_row_order(layout)
    used = set(out)
    while True:
        progressed = False
        for side in (kio.LEFT_FINGERS, kio.RIGHT_FINGERS):
            cands = _side_candidates(layout, used, side)
            if not cands:
                continue
            best = max(cands, key=lambda n: (is_vowel_key(n, layout),
                                             kio.key_aggregate_freq(n, layout, g_freq)))
            out.append(best)
            used.add(best)
            progressed = True
        if not progressed:
            break
    _append_leftover(layout, g_freq, out, used)
    return out


def ordering_o5(layout, corpus, g_freq) -> list[str]:
    """F+J anchor, then round-robin across all eight fingers for early
    full-finger coverage. Per-child calibration owns the idle key in
    production; the highest-frequency key per finger stands in here."""
    out: list[str] = []
    used: set[str] = set()
    _take_anchor(layout, out, used)
    finger_cycle = [kio.L_IDX, kio.R_IDX, kio.L_MID, kio.R_MID,
                    kio.L_RING, kio.R_RING, kio.L_PINK, kio.R_PINK]
    while True:
        progressed = False
        for finger in finger_cycle:
            cands = [n for n, k in layout.keys.items()
                     if n not in used and k.finger == finger
                     and kio.is_letter_key(n, layout)]
            if not cands:
                continue
            best = max(cands, key=lambda n: kio.key_aggregate_freq(n, layout, g_freq))
            out.append(best)
            used.add(best)
            progressed = True
        if not progressed:
            break
    _append_leftover(layout, g_freq, out, used)
    return out


ORDERINGS = {
    "O1 home-row->freq (status quo)": ordering_o1,
    "O2 F+J->vowel-priority": ordering_o2,
    "O3 coverage-greedy (no anchor)": ordering_o3,
    "O4 whole-home-row->vowel-first": ordering_o4,
    "O5 F+J->full-finger-coverage": ordering_o5,
}


# ------------------------------------------------------------ metrics --

def is_home_key(name: str, layout) -> bool:
    k = layout.keys[name]
    return k.row == 3 and 1 <= k.col <= 10


def anchor_cost(order: list[str], layout) -> int:
    for i, n in enumerate(order):
        if not is_home_key(n, layout):
            return i
    return len(order)


def real_word_readiness(order, layout, real3, tiers):
    res = {t: None for t in tiers}
    for k in range(1, len(order) + 1):
        typeable = kio.typeable_now(set(order[:k]), layout)
        n = sum(1 for w, _ in real3 if frozenset(w) <= typeable)
        for t in tiers:
            if res[t] is None and n >= t:
                res[t] = k
        if all(v is not None for v in res.values()):
            break
    return res


def coverage_milestone_steps(order, corpus, milestones):
    g_curve, _ = kio.coverage_curves(order, corpus)
    out = {}
    for t in milestones:
        out[t] = next((i + 1 for i, c in enumerate(g_curve) if c >= t), None)
    return out


def first_words_online(order, layout, real3, limit):
    seen: set[str] = set()
    timeline: list[tuple[int, str]] = []
    for k in range(1, len(order) + 1):
        typeable = kio.typeable_now(set(order[:k]), layout)
        for w, _ in real3:
            if w in seen:
                continue
            if frozenset(w) <= typeable:
                seen.add(w)
                timeline.append((k, w))
        if len(timeline) >= limit:
            break
    return timeline[:limit]


# ------------------------------------------------------------ reporting --

def section(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")


def analyze_language(lang: str, dict_set):
    layout = LAYOUT_BUILDERS[lang]()
    freq_dict = get_frequency_dict(lang)
    native = kio.native_layout(freq_dict, layout)
    g_freq = kio.grapheme_frequencies(freq_dict, native)
    native_graphemes = frozenset(native.graphemes.keys())

    use_dict = dict_set if lang == "en" else None
    corpus = build_real_word_corpus(native, freq_dict, use_dict)
    real3, raw3 = three_letter_pools(freq_dict, native_graphemes, use_dict)

    rows = {}
    for label, fn in ORDERINGS.items():
        order = fn(native, corpus, g_freq)
        rows[label] = {
            "order": order,
            "anchor_cost": anchor_cost(order, native),
            "readiness": real_word_readiness(order, native, real3, REAL3_TIERS),
            "cov": coverage_milestone_steps(order, corpus, COV_MILESTONES),
            "first_words": first_words_online(order, native, real3,
                                              FIRST_WORDS_LIMIT),
        }

    return {
        "lang": lang,
        "alpha": len(native_graphemes),
        "n_real3": len(real3),
        "n_raw3": raw3,
        "rows": rows,
    }


def print_language(r) -> None:
    section(f"{r['lang']} — ordering comparison  "
            f"(native alphabet {r['alpha']} keys)")
    print(f"  real 3-letter words: {r['n_real3']} of {r['n_raw3']} raw "
          f"(filter removed {r['n_raw3'] - r['n_real3']} non-words/acronyms)\n")

    hdr = (f"  {'ordering':<32}  {'anchor':>6}  "
           f"{'1st':>4}{'>=10':>5}{'>=25':>5}{'>=50':>5}  "
           f"{'cov50':>6}{'cov75':>6}{'cov90':>6}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for label, d in r["rows"].items():
        rd = d["readiness"]
        cv = d["cov"]

        def cell(v):
            return f"{v:>5}" if v is not None else "  n/a"
        print(f"  {label:<32}  {d['anchor_cost']:>6}  "
              f"{rd[1] if rd[1] else 'n/a':>4}"
              f"{cell(rd[10])}{cell(rd[25])}{cell(rd[50])}  "
              f"{cell(cv[0.50])[1:]:>6}{cell(cv[0.75])[1:]:>6}{cell(cv[0.90])[1:]:>6}")

    print("\n  anchor = home-row keys learned before the first off-home reach.")
    print("  1st/>=N = step at which that many real 3-letter words are typeable.")
    print("  covXX = step at which XX% of real 3-6 word frequency is typeable.\n")

    print("  First real 3-letter words to come online (word@step):")
    for label, d in r["rows"].items():
        fw = "  ".join(f"{w}@{k}" for k, w in d["first_words"]) or "(none)"
        print(f"    {label:<32}  {fw}")


def print_cross_language(results) -> None:
    section("Cross-language summary — step to 25 real 3-letter words")
    labels = list(ORDERINGS.keys())
    hdr = f"  {'lang':>4}  " + "".join(f"{lab.split()[0]:>7}" for lab in labels)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in results:
        cells = []
        for lab in labels:
            v = r["rows"][lab]["readiness"][25]
            cells.append(f"{v if v is not None else 'n/a':>7}")
        print(f"  {r['lang']:>4}  " + "".join(cells))
    print("\n  NB: the dictionary filter (--with english-words) only refines en;")
    print("  other languages use the heuristic, so their counts still include some")
    print("  non-words. Treat cross-language word-step numbers as indicative. Anchor")
    print("  cost below is filter-independent and so is exact across languages.")

    section("Cross-language summary — anchor cost (home keys before first reach)")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in results:
        cells = [f"{r['rows'][lab]['anchor_cost']:>7}" for lab in labels]
        print(f"  {r['lang']:>4}  " + "".join(cells))


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
    dict_set = load_english_dict()
    orig_stdout = sys.stdout
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        sys.stdout = _Tee(orig_stdout, fh)
        try:
            print("Key-Introduction Order Comparison Spike")
            print(f"Python: {sys.version.split()[0]}   Platform: {sys.platform}")
            print(f"Languages: {', '.join(LAYOUT_BUILDERS)}")
            print(f"Orderings: {', '.join(o.split()[0] for o in ORDERINGS)}")
            print(f"Word band: {MIN_LEN}-{MAX_LEN} letters   "
                  f"real-3L tiers: {REAL3_TIERS}")
            if dict_set:
                print(f"English real-word filter: dictionary active "
                      f"({len(dict_set)} entries) — pronounceable acronyms removed")
            else:
                print("English real-word filter: heuristic only (vowel + "
                      "not-all-same + initialism list).")
                print("  For the stricter check run: "
                      "uv run --with english-words python "
                      "spikes/intro_order_comparison_spike.py")

            results = []
            for lang in LAYOUT_BUILDERS:
                print(f"\n  analysing {lang} ...", end="", flush=True)
                r = analyze_language(lang, dict_set)
                results.append(r)
                print(f" real3={r['n_real3']}/{r['n_raw3']}")

            for r in results:
                print_language(r)
            print_cross_language(results)

            print("\n" + "=" * 78)
            print("  DONE")
            print("=" * 78)
            print(f"\n  Results written to {RESULTS_PATH}")
            print("  Paste the full output above back into the Claude Code session.")
        finally:
            sys.stdout = orig_stdout


if __name__ == "__main__":
    main()
