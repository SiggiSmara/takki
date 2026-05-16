"""
Spike: wordfreq startup time and vocabulary coverage curve

Tests two things:
  1. How long does get_frequency_dict() take per language? (startup cost)
  2. At what key count do we reach 10% / 25% (Silver) / 50% (Gold) / 75% coverage?

Run from repo root:
    uv run python spikes/wordfreq_coverage_spike.py

What this validates:
  - Are the Silver/Gold milestone key counts (1/3 and 2/3 of native alphabet)
    well-distributed across languages?
  - Is per-language load time acceptable at startup?
  - Does the native-alphabet detection correctly exclude loanword characters?

Only Latin-script languages are tested — non-Latin scripts (ar, ru, el, hi, etc.)
are out of scope for v1 per ADR-006.

Native alphabet detection
-------------------------
In the real app the authoritative character set comes from the keyboard layout
(Windows scan codes via the platform interface). Here we approximate it from
corpus statistics: a character is "native" if it appears in words that collectively
make up at least MIN_NATIVE_COVERAGE of the 3+ letter alphabetic text. This
correctly excludes loanword-only characters (e.g. é in English from café/résumé)
while keeping all genuine alphabet members including diacritics (e.g. ð in Icelandic).

Coverage definition
-------------------
Coverage = frequency-weighted fraction of 3-or-more-letter, native-alphabet-only
words that are typeable with the child's current key set.

  - ≥ 3 chars: excludes single-letter articles and 2-letter prepositions that
    skew the metric without reflecting vocabulary mastery.
  - Native-alphabet-only: excludes loanwords with foreign characters
    (café, résumé) that the child will never be asked to type.
"""

import sys
import time
from wordfreq import get_frequency_dict

LANGUAGES = [
    "en", "es", "de", "fr", "it", "pt",  # major Western European
    "nl", "sv", "da", "nb",               # Germanic / Nordic
    "is",                                  # Icelandic (highly inflected)
    "pl", "cs", "sk", "sl",               # Slavic Latin-script
    "hu", "fi", "tr",                     # other Latin-script
    "ro", "ca", "id",                     # remaining Latin-script
]

THRESHOLDS = [0.10, 0.25, 0.50, 0.75]

# A character is "native" to the language if it appears in words that
# collectively account for at least this fraction of 3+char alphabetic text.
# 0.1% cleanly separates genuine alphabet members from loanword-only characters.
MIN_NATIVE_COVERAGE = 0.001


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def detect_native_alphabet(alpha: dict[str, float]) -> frozenset[str]:
    """
    Approximate the keyboard's native character set from corpus statistics.

    In the real implementation this is replaced by the keyboard layout
    (get_home_row_keys() + full scan codes), which is authoritative.
    """
    total_freq = sum(alpha.values())
    if total_freq == 0:
        return frozenset()

    char_weight: dict[str, float] = {}
    for w, freq in alpha.items():
        for c in frozenset(w.lower()):
            char_weight[c] = char_weight.get(c, 0.0) + freq

    return frozenset(
        c for c, w in char_weight.items()
        if w / total_freq >= MIN_NATIVE_COVERAGE
    )


def build_coverage_curve(freq_dict: dict) -> dict:
    """
    Returns a dict with:
      curve          — [(letter, cumulative_coverage), ...] in frequency order
      native_alpha   — frozenset of native characters
      native_words   — count of words in the filtered working set

    Two-pass approach:
      Pass 1: compute native alphabet from all 3+ char alpha words
      Pass 2: filter to words composed entirely of native characters,
              then build the coverage curve over that clean set

    This means loanwords (café, résumé) are excluded from both the
    coverage denominator and the word list — consistent with Layer 2.
    """
    # Pass 1: initial alpha filter — length and alpha only
    alpha_raw = {w: f for w, f in freq_dict.items() if w.isalpha() and len(w) >= 3}
    native_alpha = detect_native_alphabet(alpha_raw)

    # Pass 2: keep only words composed entirely of native characters
    alpha = {
        w: f for w, f in alpha_raw.items()
        if frozenset(w.lower()) <= native_alpha
    }

    total_freq = sum(alpha.values())
    if total_freq == 0:
        return {"curve": [], "native_alpha": native_alpha, "native_words": 0}

    # Per-word letter sets (lowercase, within native alphabet)
    word_letters: dict[str, frozenset] = {w: frozenset(w.lower()) for w in alpha}

    # Weighted frequency per native character
    char_weight: dict[str, float] = {c: 0.0 for c in native_alpha}
    for w, freq in alpha.items():
        for c in word_letters[w]:
            char_weight[c] += freq

    sorted_chars = sorted(native_alpha, key=lambda c: char_weight[c], reverse=True)

    # Reverse index: character → words containing it
    char_to_words: dict[str, list[str]] = {c: [] for c in native_alpha}
    for w in alpha:
        for c in word_letters[w]:
            char_to_words[c].append(w)

    word_need = {w: len(word_letters[w]) for w in alpha}
    word_have = {w: 0 for w in alpha}

    typeable_freq = 0.0
    curve: list[tuple[str, float]] = []
    for ch in sorted_chars:
        for w in char_to_words[ch]:
            word_have[w] += 1
            if word_have[w] == word_need[w]:
                typeable_freq += alpha[w]
        curve.append((ch, typeable_freq / total_freq))

    return {
        "curve": curve,
        "native_alpha": native_alpha,
        "native_words": len(alpha),
    }


def analyze(lang: str) -> dict:
    t0 = time.perf_counter()
    freq_dict = get_frequency_dict(lang)
    load_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    result = build_coverage_curve(freq_dict)
    compute_ms = (time.perf_counter() - t0) * 1000

    curve = result["curve"]
    native_alpha = result["native_alpha"]

    threshold_keys: dict[float, int | None] = {t: None for t in THRESHOLDS}
    for i, (_, cov) in enumerate(curve):
        for t in THRESHOLDS:
            if threshold_keys[t] is None and cov >= t:
                threshold_keys[t] = i + 1

    alpha_size = len(native_alpha)
    return {
        "lang": lang,
        "load_ms": load_ms,
        "compute_ms": compute_ms,
        "alpha_size": alpha_size,
        "native_words": result["native_words"],
        "native_alpha": native_alpha,
        "threshold_keys": threshold_keys,
        "curve": curve,
        "silver_gate": round(alpha_size / 3),
        "gold_gate": round(alpha_size * 2 / 3),
    }


def print_table(results: list[dict]) -> None:
    section("Results table  (Silver gate = ⌊alpha/3⌋, Gold gate = ⌊alpha×2/3⌋)")
    header = (
        f"{'Lang':>4}  {'Alpha':>5}  {'S-gate':>6}  {'G-gate':>6}  {'Load':>7}  "
        f"{'10%':>5}  {'25%cov':>6}  {'50%cov':>6}  {'75%cov':>6}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        tk = r["threshold_keys"]
        def fmt(t):
            v = tk[t]
            return f"{v:>5}" if v is not None else "  n/a"
        print(
            f"{r['lang']:>4}  {r['alpha_size']:>5}  "
            f"{r['silver_gate']:>6}  {r['gold_gate']:>6}  "
            f"{r['load_ms']:>6.0f}ms  "
            f"{fmt(0.10)}  {fmt(0.25):>6}  {fmt(0.50):>6}  {fmt(0.75):>6}"
        )


def print_curve(lang: str, r: dict) -> None:
    curve = r["curve"]
    alpha_size = r["alpha_size"]
    silver_gate = r["silver_gate"]
    gold_gate = r["gold_gate"]

    print(f"\n  {lang} — {alpha_size} native keys  "
          f"(Silver gate: {silver_gate}, Gold gate: {gold_gate})")
    width = 40
    for i, (ch, cov) in enumerate(curve):
        filled = int(cov * width)
        bar = "█" * filled + ("▌" if cov * width - filled >= 0.5 else "")
        markers = []
        if i + 1 == silver_gate:
            markers.append("← Silver gate")
        if i + 1 == gold_gate:
            markers.append("← Gold gate")
        if cov >= 0.75 and (i == 0 or curve[i-1][1] < 0.75):
            markers.append("75% cov")
        elif cov >= 0.50 and (i == 0 or curve[i-1][1] < 0.50):
            markers.append("50% cov")
        elif cov >= 0.25 and (i == 0 or curve[i-1][1] < 0.25):
            markers.append("25% cov")
        elif cov >= 0.10 and (i == 0 or curve[i-1][1] < 0.10):
            markers.append("10% cov")
        suffix = "  " + "  ".join(markers) if markers else ""
        print(f"    {i+1:2}. {ch}  [{bar:<{width}}] {cov:5.1%}{suffix}")


def print_native_alphabets(results: list[dict]) -> None:
    section("Detected native alphabets (sorted by char_weight)")
    for r in results:
        # Show chars in the order they appear in the curve
        ordered = [ch for ch, _ in r["curve"]]
        print(f"  {r['lang']:>4} ({r['alpha_size']:2} keys): {''.join(ordered)}")


def main() -> None:
    print("wordfreq Coverage Spike")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Languages: {', '.join(LANGUAGES)}")
    print(f"Native alphabet threshold: {MIN_NATIVE_COVERAGE} "
          f"(char must appear in ≥{MIN_NATIVE_COVERAGE*100:.1f}% of 3+char text)")

    section("Per-language analysis")
    results = []
    for lang in LANGUAGES:
        print(f"  Analysing {lang}...", end="", flush=True)
        r = analyze(lang)
        results.append(r)
        print(f" alpha={r['alpha_size']}  Silver@{r['silver_gate']}keys  "
              f"Gold@{r['gold_gate']}keys  (25%cov@{r['threshold_keys'][0.25]}  "
              f"50%cov@{r['threshold_keys'][0.50]})")

    print_table(results)
    print_native_alphabets(results)

    section("Coverage curves (selected languages)")
    for lang in ["en", "de", "is", "fi", "tr"]:
        r = next(x for x in results if x["lang"] == lang)
        print_curve(lang, r)

    section("Milestone gate summary")
    silvers = [r["silver_gate"] for r in results]
    golds = [r["gold_gate"] for r in results]
    print(f"  Silver gate (⌊alpha/3⌋): min={min(silvers)}, max={max(silvers)}, "
          f"avg={sum(silvers)/len(silvers):.1f}")
    print(f"  Gold gate   (⌊alpha×2/3⌋): min={min(golds)}, max={max(golds)}, "
          f"avg={sum(golds)/len(golds):.1f}")
    print()
    print("  Coverage at those gates (informational display, not the gate itself):")
    for r in results:
        curve = r["curve"]
        sg, gg = r["silver_gate"], r["gold_gate"]
        s_cov = curve[sg - 1][1] if sg <= len(curve) else None
        g_cov = curve[gg - 1][1] if gg <= len(curve) else None
        s_str = f"{s_cov:.0%}" if s_cov is not None else "n/a"
        g_str = f"{g_cov:.0%}" if g_cov is not None else "n/a"
        print(f"    {r['lang']:>4}: Silver({sg} keys)={s_str}  Gold({gg} keys)={g_str}")

    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)
    print("\nPaste the full output of this script back into the Claude Code session.")


if __name__ == "__main__":
    main()
