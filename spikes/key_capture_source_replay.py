"""
Candidate (1), repaired, replayed against the recorded logs (alpha-plan #13).

pynput's own KeyCode.join() re-implements dead-key composition and gets it wrong (see the spike's
logs). The in-place repair is to keep the hook but compose with Windows' own ToUnicodeEx, called on a
private thread whose keyboard state belongs to nobody else, with the layout the window is using at
that moment. This replays every hook key event of a log through exactly that and compares the text
with what the window received (TEXTINPUT), step by step, for steps where the window had focus.

    uv run python spikes/key_capture_source_replay.py <log.jsonl> [...]

Two inputs the repair would need from elsewhere are taken from the log here, and say so:
  - the layout: the step's main_hkl (what the window thread reports), as a repaired capture layer
    would have to poll for;
  - modifiers: tracked from the hook's own down/up events.
"""

import ctypes
import ctypes.wintypes as wt
import json
import sys
import threading
from pathlib import Path

if sys.platform != "win32":
    raise SystemExit("Windows only")

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.ToUnicodeEx.restype = ctypes.c_int
user32.ToUnicodeEx.argtypes = [
    wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_ubyte), wt.LPWSTR, ctypes.c_int, wt.UINT, ctypes.c_void_p,
]
user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p

SHIFTS = {0xA0: 0x10, 0xA1: 0x10, 0xA2: 0x11, 0xA3: 0x11, 0xA4: 0x12, 0xA5: 0x12}


def replay(path: Path) -> list[str]:
    recs = sorted((json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()),
                  key=lambda r: (r.get("t", 0), r["k"] != "step"))
    out: list[str] = [f"# {path.name}: candidate (1) repaired (hook + ToUnicodeEx on a private thread)"]
    state = (ctypes.c_ubyte * 256)()
    hkls: dict[str, int] = {}
    step: dict | None = None
    focused = True
    composed: list[str] = []
    window: list[str] = []
    focus_changed = False

    def flush_step() -> None:
        if step is None:
            return
        c, w = "".join(composed), "".join(window)
        verdict = "same" if c == w else "DIFFERENT"
        note = "  (focus changed during the step)" if focus_changed else ""
        out.append(f"step {step['n']:2d} {step['id'][:44]:44s} {verdict:9s} repaired={c!r:28s} window={w!r}{note}")

    for r in recs:
        if r["k"] == "step":
            flush_step()
            step, composed, window, focus_changed = r, [], [], False
            continue
        if r["k"] == "raw" and r["type"] == "WINDOW" and r.get("wev") in ("FOCUS_GAINED", "FOCUS_LOST"):
            focused = r["wev"] == "FOCUS_GAINED"
            focus_changed = True
        elif r["k"] == "pg" and r["type"] == "TextInput":
            window.append(r["text"])
        elif r["k"] == "hook" and step is not None:
            vk = r["vk"]
            down = r["dir"] == "down"
            if vk == 0x14 and down and not (state[0x14] & 0x80):
                state[0x14] ^= 0x01
            state[vk] = (state[vk] & 0x01) | (0x80 if down else 0)
            if vk in SHIFTS:
                generic = SHIFTS[vk]
                pair = [k for k, g in SHIFTS.items() if g == generic]
                state[generic] = 0x80 if any(state[k] & 0x80 for k in pair) else 0
            if not down or not focused:
                continue
            klid = step["main_hkl"]
            if klid not in hkls:
                hkls[klid] = user32.LoadKeyboardLayoutW(f"{int(klid, 16) & 0xFFFF:08X}", 0x80)
            buf = ctypes.create_unicode_buffer(8)
            n = user32.ToUnicodeEx(vk, r["scan"] & 0xFF, state, buf, 8, 0, hkls[klid])
            if n > 0:
                composed.append("".join(ch for ch in buf.value[:n] if ch >= " " and ch != "\x7f"))
    flush_step()
    return out


def main() -> None:
    results: list[list[str]] = []
    for arg in sys.argv[1:]:
        # A thread of its own: its keyboard state is private, which is the whole point of the repair.
        t = threading.Thread(target=lambda p=Path(arg): results.append(replay(p)))
        t.start()
        t.join()
    text = "\n\n".join("\n".join(r) for r in results) + "\n"
    sys.stdout.buffer.write(text.encode("utf-8"))


if __name__ == "__main__":
    main()
