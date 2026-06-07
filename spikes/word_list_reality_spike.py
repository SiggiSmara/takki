"""
Spike: word-list reality — Layer-2 availability and profanity prevalence

Resolves two corner cases logged in docs/roadmap.md:

  C13  Layer-2 starvation. ADR-010 unlocks Layer 2 at >=8 keys known and
       immediately gives it 40% of the session. But coverage at 8 keys ranges
       from ~5% upward, and Layer 2 starts with 3-letter words. Question: at the
       8-key unlock, do enough typeable 3-letter real words actually exist per
       language to sustain a Layer-2 session, or does Layer 2 unlock onto an
       almost-empty pool? If the latter, gate Layer 2 on word availability, not
       just key count.

  C9   Profanity prevalence. ADR-008 derives the word list algorithmically from
       wordfreq, which blends Twitter + subtitles. ADR-008 claims contested words
       "tend to be longer and lower-frequency." Question: how much profanity sits
       in the short (3-6 letter), high-frequency band a child meets first, and how
       early (by frequency rank) would a child hit one? Quantifies whether a
       default, per-language blocklist is warranted on top of the reactive
       custom_words.txt exclude file.

The "k keys known" axis reuses the real ADR-023 introduction order
(frequency-leader-per-hand, algorithm C) imported from
key_introduction_order_spike.py, so the key set at each step matches the engine.

Run from repo root (the headless dev box is fine — no hardware needed):
    uv run --with better-profanity python spikes/word_list_reality_spike.py

(better-profanity is only used by the C9 section; C13 runs without it.)

Output: a printed report plus spikes/results/word_list_reality_results.txt.
Paste the full stdout back into the Claude Code session.
"""

import sys
from pathlib import Path

from wordfreq import get_frequency_dict

SPIKES_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKES_DIR))

# Reuse the production-mirroring layout model and the chosen intro algorithm.
import key_introduction_order_spike as kio  # noqa: E402

RESULTS_PATH = SPIKES_DIR / "results" / "word_list_reality_results.txt"

# Beta languages first (en, de), then a spread that the coverage spike showed
# have low early coverage (es, fr, is, fi) plus a composite-heavy one (pl).
LAYOUT_BUILDERS = {
    "en": kio.build_en,
    "de": kio.build_de,
    "es": kio.build_es,
    "fr": kio.build_fr,
    "is": kio.build_is,
    "fi": kio.build_fi,
    "pl": kio.build_pl,
}

LAYER2_UNLOCK_KEYS = 8          # ADR-010 / config.py LAYER2_UNLOCK_KEY_COUNT
K_SWEEP = [8, 10, 12, 14, 16]
WORD_MIN_LEN, WORD_MAX_LEN = 3, 6   # Layer 2 progresses 3 -> 6 letters
READINESS_TIERS = [10, 25, 50]      # distinct 3-letter words considered "usable"

# C9 — profanity scan
C9_LANG = "en"                  # better-profanity ships an English list only
C9_TOP_N = 5000
C9_BANDS = [100, 500, 1000, 5000]


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")


# ----------------------------------------------------------- C13 helpers --

def working_words(freq_dict: dict, native_graphemes: frozenset[str]) -> list[tuple[str, float]]:
    """Alpha words of length 3-6 whose chars are all in the native alphabet,
    sorted by frequency descending. This is the Layer-2 candidate universe."""
    out = [
        (w.lower(), f)
        for w, f in freq_dict.items()
        if w.isalpha()
        and WORD_MIN_LEN <= len(w) <= WORD_MAX_LEN
        and frozenset(w.lower()) <= native_graphemes
    ]
    out.sort(key=lambda wf: wf[1], reverse=True)
    return out


def typeable_words(words: list[tuple[str, float]],
                   typeable: set[str]) -> list[tuple[str, float]]:
    return [(w, f) for (w, f) in words if frozenset(w) <= typeable]


def analyze_language(lang: str) -> dict:
    layout = LAYOUT_BUILDERS[lang]()
    freq_dict = get_frequency_dict(lang)
    native = kio.native_layout(freq_dict, layout)
    g_freq = kio.grapheme_frequencies(freq_dict, native)
    order = kio.algo_freq_per_hand(native, g_freq)
    native_graphemes = frozenset(native.graphemes.keys())

    words = working_words(freq_dict, native_graphemes)
    total_3to6_freq = sum(f for _, f in words) or 1.0
    words_3l = [(w, f) for (w, f) in words if len(w) == 3]

    # Per-k snapshot.
    per_k: list[dict] = []
    for k in K_SWEEP:
        known = set(order[:k])
        typeable = kio.typeable_now(known, native)
        tw = typeable_words(words, typeable)
        tw_3l = [(w, f) for (w, f) in tw if len(w) == 3]
        per_k.append({
            "k": k,
            "known_keys": order[:k],
            "n_typeable_graphemes": len(typeable),
            "n_words_3l": len(tw_3l),
            "n_words_3to6": len(tw),
            "wcov_3to6": sum(f for _, f in tw) / total_3to6_freq,
            "sample_3l": [w for w, _ in tw_3l[:15]],
        })

    # Readiness: smallest k where distinct typeable 3-letter words >= tier.
    readiness: dict[int, int | None] = {tier: None for tier in READINESS_TIERS}
    for k in range(1, len(order) + 1):
        known = set(order[:k])
        typeable = kio.typeable_now(known, native)
        n3 = sum(1 for (w, _) in words_3l if frozenset(w) <= typeable)
        for tier in READINESS_TIERS:
            if readiness[tier] is None and n3 >= tier:
                readiness[tier] = k
        if all(v is not None for v in readiness.values()):
            break

    return {
        "lang": lang,
        "alpha_size": len(native_graphemes),
        "n_native_3to6_words": len(words),
        "n_native_3l_words": len(words_3l),
        "per_k": per_k,
        "readiness": readiness,
    }


def print_c13(results: list[dict]) -> None:
    section("C13 — Layer-2 word availability at the >=8-key unlock")
    print("  At k = 8 keys known (the Layer-2 unlock point):\n")
    hdr = f"  {'lang':>4}  {'alpha':>5}  {'graphemes':>9}  {'3L words':>8}  {'3-6L words':>10}  {'3-6L wcov':>9}  verdict"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in results:
        snap = next(s for s in r["per_k"] if s["k"] == LAYER2_UNLOCK_KEYS)
        n3 = snap["n_words_3l"]
        verdict = "OK" if n3 >= READINESS_TIERS[1] else ("THIN" if n3 >= READINESS_TIERS[0] else "STARVED")
        print(f"  {r['lang']:>4}  {r['alpha_size']:>5}  "
              f"{snap['n_typeable_graphemes']:>9}  {n3:>8}  "
              f"{snap['n_words_3to6']:>10}  {snap['wcov_3to6']:>8.1%}  {verdict}")

    section("C13 — readiness: smallest k reaching N distinct typeable 3-letter words")
    hdr = f"  {'lang':>4}  " + "  ".join(f">={t:<3} @k".rjust(8) for t in READINESS_TIERS)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in results:
        cells = []
        for tier in READINESS_TIERS:
            v = r["readiness"][tier]
            cells.append(f"{v if v is not None else 'n/a':>8}")
        print(f"  {r['lang']:>4}  " + "  ".join(cells))
    print(f"\n  (Layer-2 unlocks at k={LAYER2_UNLOCK_KEYS}. Where a tier is reached only")
    print("   at k > 8, Layer 2 would unlock onto fewer than that many 3-letter words.)")

    section("C13 — k-sweep per language (3-letter / 3-6-letter typeable word counts)")
    for r in results:
        print(f"\n  {r['lang']}  (native alphabet {r['alpha_size']} keys, "
              f"{r['n_native_3l_words']} native 3-letter words total)")
        for snap in r["per_k"]:
            keys = "".join(k if len(k) == 1 else f"[{k}]" for k in snap["known_keys"])
            print(f"    k={snap['k']:>2}  keys={keys:<22}  "
                  f"3L={snap['n_words_3l']:>4}  3-6L={snap['n_words_3to6']:>5}  "
                  f"wcov={snap['wcov_3to6']:>6.1%}")
        unlock = next(s for s in r["per_k"] if s["k"] == LAYER2_UNLOCK_KEYS)
        print(f"    sample typeable 3-letter words at k=8 (top by freq): "
              f"{', '.join(unlock['sample_3l']) or '(none)'}")


# ------------------------------------------------------------ C9 section --

def print_c9() -> None:
    section(f"C9 — profanity prevalence in the short high-frequency band ({C9_LANG})")
    try:
        from better_profanity import profanity
    except ImportError:
        print("  SKIPPED: better-profanity not installed.")
        print("  Re-run with: uv run --with better-profanity python spikes/word_list_reality_spike.py")
        return

    profanity.load_censor_words()

    layout = LAYOUT_BUILDERS[C9_LANG]()
    freq_dict = get_frequency_dict(C9_LANG)
    native = kio.native_layout(freq_dict, layout)
    native_graphemes = frozenset(native.graphemes.keys())

    words = working_words(freq_dict, native_graphemes)[:C9_TOP_N]
    # contains_profanity on a single token ~= whole-word match against the
    # library's English wordset (better-profanity splits on whitespace, so the
    # Scunthorpe substring problem is mostly avoided — note it anyway).
    flagged = [
        (rank, w, f)
        for rank, (w, f) in enumerate(words, start=1)
        if profanity.contains_profanity(w)
    ]

    print(f"  Scanned the top {len(words)} English words of length {WORD_MIN_LEN}-{WORD_MAX_LEN}")
    print("  (alphabetic, native-alphabet-only), ranked by wordfreq frequency.\n")

    print(f"  {'band (top N by freq)':>22}  {'# profanity hits':>16}")
    print("  " + "-" * 40)
    for band in C9_BANDS:
        n = sum(1 for (rank, _, _) in flagged if rank <= band)
        print(f"  {('top ' + str(band)):>22}  {n:>16}")

    print(f"\n  Total flagged in top {len(words)}: {len(flagged)}")
    if flagged:
        first = flagged[0]
        print(f"  Earliest hit: rank #{first[0]} (\"{first[1]}\") — i.e. a child working")
        print(f"  down the frequency list could meet it within the first ~{first[0]} words.")
        print("\n  Flagged words with frequency rank (for blocklist design):")
        for rank, w, _f in flagged[:30]:
            print(f"    #{rank:<5} {w}")
        if len(flagged) > 30:
            print(f"    ... and {len(flagged) - 30} more")
    print("\n  Caveats: better-profanity ships an English list only — de/fr/pl/is")
    print("  would each need a native-speaker blocklist (a per-language contribution")
    print("  surface, same shape as the intent/encouragement YAML in ADR-022). Matching")
    print("  is whole-word so substring false positives are rare but not impossible.")


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
    orig_stdout = sys.stdout
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        sys.stdout = _Tee(orig_stdout, fh)
        try:
            print("Word-list Reality Spike")
            print(f"Python: {sys.version.split()[0]}")
            print(f"Platform: {sys.platform}")
            print(f"Languages (C13): {', '.join(LAYOUT_BUILDERS)}")
            print(f"Word length band: {WORD_MIN_LEN}-{WORD_MAX_LEN}   Layer-2 unlock: k={LAYER2_UNLOCK_KEYS}")

            section("C13 — analysing languages")
            results = []
            for lang in LAYOUT_BUILDERS:
                print(f"  {lang} ...", end="", flush=True)
                r = analyze_language(lang)
                results.append(r)
                unlock = next(s for s in r["per_k"] if s["k"] == LAYER2_UNLOCK_KEYS)
                print(f" alpha={r['alpha_size']}  3L@8keys={unlock['n_words_3l']}  "
                      f"3-6L@8keys={unlock['n_words_3to6']}")

            print_c13(results)
            print_c9()

            print("\n" + "=" * 70)
            print("  DONE")
            print("=" * 70)
            print(f"\n  Results written to {RESULTS_PATH}")
            print("  Paste the full output above back into the Claude Code session.")
        finally:
            sys.stdout = orig_stdout


if __name__ == "__main__":
    main()
