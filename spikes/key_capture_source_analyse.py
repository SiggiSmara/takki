"""
Read a log from key_capture_source_spike.py and report, per step, what each candidate source
delivers (alpha-plan #13).

    uv run python spikes/key_capture_source_analyse.py <log.jsonl> [more.jsonl ...]

Writes <log>.txt beside each log and prints it.

Per step:
  events     every hook / raw SDL / pygame key event on one timeline (repeats collapsed)
  text       what each candidate would hand the lesson engine:
               (1) pynput + compose from is_dead with pynput's own KeyCode.join()
               (2) the window: pygame TEXTINPUT
               today: production translate() chars, as PynputKeyStream delivers them
  holds      per key: presses, repeats, time to first repeat, per source
  balance    KEYDOWN/KEYUP pairing per source (missing or orphan releases)
  pairing    each hook event matched to its SDL raw event by key and direction: lag, misses,
             and how often the two streams interleave
"""

import json
import statistics
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

if sys.platform == "win32":
    from pynput.keyboard import KeyCode
else:
    KeyCode = None


def load(path: Path) -> tuple[dict, list[tuple[dict, list[dict]]]]:
    recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = next(r for r in recs if r["k"] == "meta")
    timeline = sorted((r for r in recs if "t" in r), key=lambda r: (r["t"], r["k"] != "step"))
    steps: list[tuple[dict, list[dict]]] = []
    for r in timeline:
        if r["k"] == "step":
            steps.append((r, []))
        elif steps and r["k"] in ("hook", "raw", "pg", "flush", "note"):
            steps[-1][1].append(r)
    return meta, steps


def describe(r: dict) -> str:
    if r["k"] == "hook":
        what = f"char={r['char']!r}" + (" DEAD" if r.get("dead") else "") if "char" in r else f"name={r['name']}"
        return (f"HOOK {r['dir']:4s} {what:18s} vk=0x{r['vk']:02x} scan=0x{r['scan']:02x}"
                f"{'e' if r['ext'] else ' '} sdl_sc={r['sdl_sc']} tr={r['tr_char'] or r['tr_name']!r}"
                f"{' INJ' if r['inj'] else ''} thread_hkl={r['hkl_thread']}")
    if r["k"] == "raw":
        if r["type"] in ("KEYDOWN", "KEYUP"):
            return f"RAW  {r['type']:8s} sc={r['sc']:<3} sym={r['sym']:<9} mod=0x{r['mod']:04x} repeat={r['rep']}"
        if r["type"] == "WINDOW":
            return f"RAW  WINDOW {r['wev']}"
        return f"RAW  {r['type']} {r.get('text')!r}"
    if r["k"] == "pg":
        if r["type"] in ("KeyDown", "KeyUp"):
            extra = f" dead={r.get('dead')}" if r["type"] == "KeyDown" else ""
            return f"PG   {r['type']:8s} sc={r['sc']:<3} key={r['key']:<9} unicode={r['uni']!r}{extra}"
        if "text" in r:
            return f"PG   {r['type']} {r['text']!r}"
        return f"PG   {r['type']}"
    if r["k"] == "flush":
        return f"FLUSH ToUnicodeEx(VK_SPACE) on window thread -> {r['result']}"
    return f"NOTE {r.get('text')}"


def collapse(events: list[dict]) -> list[str]:
    lines: list[str] = []
    prev_desc, run_start, count, prev_t = None, 0.0, 0, 0.0
    for r in events:
        d = describe(r)
        if d == prev_desc:
            count += 1
            prev_t = r["t"]
            continue
        if count > 1:
            lines.append(f"{'':>10}   ... x{count} in all, last at {prev_t:.1f}")
        lines.append(f"{r['t']:10.1f}  {d}")
        prev_desc, run_start, count, prev_t = d, r["t"], 1, r["t"]
    if count > 1:
        lines.append(f"{'':>10}   ... x{count} in all, last at {prev_t:.1f}")
    return lines


def candidate1_text(hooks: list[dict]) -> str:
    # Candidate (1): keep pynput, compose a pending dead key with the next key using pynput's
    # own KeyCode.join(). Repeats of a held key are presses too, as the hook delivers them.
    if KeyCode is None:
        return "(needs Windows for pynput)"
    out, pending = [], None
    for h in hooks:
        if h["dir"] != "down":
            continue
        if "char" in h and h["char"] is not None:
            key = KeyCode.from_dead(h["char"]) if h.get("dead") else KeyCode.from_char(h["char"])
            if pending is None:
                if key.is_dead:
                    pending = key
                else:
                    out.append(h["char"])
                continue
            try:
                joined = pending.join(key).char
                out.append(joined if len(joined) == 1 else f"[{joined!r}: {len(joined)} code points]")
            except ValueError:
                out.append(f"[join failed: {pending.char!r}+{h['char']!r}]")
            pending = None
        elif h.get("name") == "space" and pending is not None:
            out.append(pending.join(KeyCode.from_char(" ")).char)
            pending = None
    if pending is not None:
        out.append(f"[pending {pending.char!r}]")
    return "".join(out)


def names(text: str) -> str:
    return ", ".join(f"{c!r} {unicodedata.name(c, '?')}" for c in text) if text else "(nothing)"


def holds(events: list[dict]) -> list[str]:
    lines = []
    # hook: by vk
    per: dict[tuple[str, object], list[dict]] = defaultdict(list)
    for r in events:
        if r["k"] == "hook":
            per[("hook", r["vk"])].append(r)
        elif r["k"] == "raw" and r["type"] in ("KEYDOWN", "KEYUP"):
            per[("raw", r["sc"])].append(r)
        elif r["k"] == "pg" and r["type"] in ("KeyDown", "KeyUp"):
            per[("pg", r["sc"])].append(r)
    for (src, key), rs in sorted(per.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        actuations, i = [], 0
        cur: list[dict] = []
        for r in rs:
            down = r.get("dir") == "down" or r.get("type") in ("KEYDOWN", "KeyDown")
            if down:
                cur.append(r)
            else:
                actuations.append((cur, r))
                cur = []
        if cur:
            actuations.append((cur, None))
        for downs, up in actuations:
            i += 1
            label = (downs[0].get("char") or downs[0].get("name")) if src == "hook" and downs else key
            if not downs:
                lines.append(f"  {src:4s} key={label}: RELEASE with no press before it (t={up['t']:.1f})")
                continue
            n = len(downs)
            held = (up["t"] - downs[0]["t"]) if up else None
            if src == "raw":
                fresh = sum(1 for d in downs if not d["rep"])
                rep = n - fresh
            else:
                fresh, rep = 1, n - 1
            first_rep = f"{downs[1]['t'] - downs[0]['t']:.0f} ms" if n > 1 else "-"
            ivals = [b["t"] - a["t"] for a, b in zip(downs[1:], downs[2:])]
            ival = f"{statistics.median(ivals):.0f} ms" if ivals else "-"
            lines.append(
                f"  {src:4s} key={label!s:6s} fresh={fresh} repeats={rep:<3} first repeat after {first_rep:>7}"
                f"  interval {ival:>6}  held {'%.0f ms' % held if held is not None else 'NO RELEASE'}"
            )
    texts = [r for r in events if r["k"] == "pg" and r["type"] == "TextInput"]
    if texts:
        gaps = [b["t"] - a["t"] for a, b in zip(texts, texts[1:])]
        lines.append(f"  pg   TEXTINPUT x{len(texts)}: {''.join(r['text'] for r in texts)!r}"
                     + (f"  gaps ms: {[round(g) for g in gaps[:6]]}{' ...' if len(gaps) > 6 else ''}" if gaps else ""))
    return lines


TICK_MS = 1000 / 60
PAIRS: list[tuple[dict, dict]] = []


def simulate_loop(pairs: list[tuple[dict, dict]]) -> tuple[int, int, int]:
    # Replays recorded times through the core loop of concurrency-model.md: each tick pumps SDL first,
    # then drains the inbound queue. Averaged over four tick phases, since the phase is arbitrary.
    split = between = worst = 0
    for phase in (0.0, 0.25, 0.5, 0.75):
        def tick(t: float) -> int:
            return int((t / TICK_MS) + phase) + 1
        order = sorted(
            [(tick(h["t"]), 1, h["t"], ("h", i)) for i, (h, _) in enumerate(pairs)]
            + [(tick(r["t"]), 0, r["t"], ("r", i)) for i, (_, r) in enumerate(pairs)]
        )
        pos = {who: n for n, (*_, who) in enumerate(order)}
        for i, (h, r) in enumerate(pairs):
            if tick(h["t"]) != tick(r["t"]):
                split += 1
            gap = abs(pos[("h", i)] - pos[("r", i)]) - 1
            if gap > 0:
                between += 1
                worst = max(worst, gap)
    return split, between, worst


def pairing(events: list[dict]) -> tuple[list[str], list[float], int, int]:
    hooks = [r for r in events if r["k"] == "hook"]
    for h in hooks:
        if h["sdl_sc"] is None and h["scan"] == 0x36:
            h["sdl_sc"] = 229  # logs before the spike learned the hook flags Right Shift as extended
    raws = [r for r in events if r["k"] == "raw" and r["type"] in ("KEYDOWN", "KEYUP")]
    used: set[int] = set()
    pairs: list[tuple[dict, dict]] = []
    unmatched_h = []
    for h in hooks:
        want = "KEYDOWN" if h["dir"] == "down" else "KEYUP"
        hit = None
        for j, r in enumerate(raws):
            if j in used or r["type"] != want or r["sc"] != h["sdl_sc"]:
                continue
            if h["t"] - 5 <= r["t"] <= h["t"] + 1000:
                hit = j
                break
        if hit is None:
            unmatched_h.append(h)
        else:
            used.add(hit)
            pairs.append((h, raws[hit]))
    unmatched_r = [r for j, r in enumerate(raws) if j not in used]
    lags = [r["t"] - h["t"] for h, r in pairs]
    PAIRS.extend(pairs)
    interleaved = sum(1 for (h1, r1), (h2, _) in zip(pairs, pairs[1:]) if h2["t"] < r1["t"])
    inversions = sum(1 for (_, r1), (_, r2) in zip(pairs, pairs[1:]) if r2["t"] < r1["t"])
    lines = [f"  matched {len(pairs)} hook events to SDL events; inversions of order: {inversions}; "
             f"next hook event before this SDL event (interleaved): {interleaved}"]
    if lags:
        lines.append(f"  lag hook->SDL ms: min {min(lags):.1f}  median {statistics.median(lags):.1f}  max {max(lags):.1f}")
    def runs(items: list[str]) -> list[str]:
        out: list[str] = []
        for item in items:
            if out and out[-1].split(" x")[0] == item:
                head, _, n = out[-1].rpartition(" x")
                out[-1] = f"{head} x{int(n) + 1}"
            else:
                out.append(f"{item} x1")
        return out

    for line in runs([f"{h['dir']} {h.get('char') or h.get('name')!r} scan=0x{h['scan']:02x}" for h in unmatched_h]):
        lines.append(f"  hook event with no SDL event: {line}")
    for line in runs([f"{r['type']} sc={r['sc']} repeat={r['rep']}" for r in unmatched_r]):
        lines.append(f"  SDL event with no hook event: {line}")
    return lines, lags, interleaved, inversions


def balance(events: list[dict]) -> list[str]:
    out = []
    for src, down_t, up_t in (("raw", "KEYDOWN", "KEYUP"), ("pg", "KeyDown", "KeyUp")):
        down: dict[int, float] = {}
        problems = []
        for r in events:
            if r["k"] != src or r.get("type") not in (down_t, up_t):
                continue
            if r["type"] == down_t:
                down.setdefault(r["sc"], r["t"])
            elif r["sc"] in down:
                del down[r["sc"]]
            else:
                problems.append(f"orphan KEYUP sc={r['sc']} t={r['t']:.1f}")
        problems += [f"KEYDOWN sc={sc} t={t:.1f} never released in this step" for sc, t in down.items()]
        out.append(f"  {src:4s}: " + ("every KEYDOWN has its KEYUP" if not problems else "; ".join(problems)))
    return out


def report(path: Path) -> str:
    PAIRS.clear()
    meta, steps = load(path)
    out = [f"# {path.name}", "", "meta: " + json.dumps(meta, ensure_ascii=False), ""]
    all_lags: list[float] = []
    tot_inter = tot_inv = 0
    for step, events in steps:
        out.append(f"## step {step['n']} '{step['id']}' attempt {step['attempt']} "
                   f"(main_hkl {step['main_hkl']}, text input active: {step['text_input_active']})")
        out.append(f"   {step['text']}")
        out += collapse(events)
        hooks = [r for r in events if r["k"] == "hook"]
        window_text = "".join(r["text"] for r in events if r["k"] == "pg" and r["type"] == "TextInput")
        uni = "".join(r["uni"] or "" for r in events if r["k"] == "pg" and r["type"] == "KeyDown")
        today = "".join(h["tr_char"] for h in hooks if h["dir"] == "down" and h["tr_char"])
        editing = [r for r in events if r["k"] in ("raw", "pg") and "EDITING" in r["type"].upper()]
        out.append("  text:")
        if hooks:
            out.append(f"    today, translate() presses: {today!r}  [{names(today)}]")
            c1 = candidate1_text(hooks)
            out.append(f"    (1) pynput + join():        {c1!r}")
        out.append(f"    (2) window TEXTINPUT:       {window_text!r}  [{names(window_text)}]")
        out.append(f"        pygame KEYDOWN.unicode: {uni!r}")
        if editing:
            out.append(f"    TEXTEDITING events (IME composition): {len(editing)}")
        out.append("  holds:")
        out += holds(events)
        out.append("  balance:")
        out += balance(events)
        if hooks:
            out.append("  pairing:")
            lines, lags, inter, inv = pairing(events)
            out += lines
            all_lags += lags
            tot_inter += inter
            tot_inv += inv
        out.append("")
    if all_lags:
        s = sorted(all_lags)
        p95 = s[int(0.95 * (len(s) - 1))]
        out.append(f"# all steps: {len(s)} hook->SDL pairs, lag ms min {s[0]:.1f} median {statistics.median(s):.1f} "
                   f"p95 {p95:.1f} max {s[-1]:.1f}; interleaved {tot_inter}; order inversions {tot_inv}")
        split, between, worst = simulate_loop(PAIRS)
        n = 4 * len(PAIRS)
        out.append(f"# simulated 60 Hz loop (4 phases, {n} pair-placements): hook and SDL event in different ticks "
                   f"{split} ({100 * split / n:.1f}%); another event delivered between them {between} "
                   f"({100 * between / n:.1f}%), at most {worst} events between")
    return "\n".join(out) + "\n"


def main() -> None:
    for arg in sys.argv[1:]:
        path = Path(arg)
        text = report(path)
        path.with_suffix(".txt").write_text(text, encoding="utf-8")
        sys.stdout.buffer.write(text.encode("utf-8"))


if __name__ == "__main__":
    main()
