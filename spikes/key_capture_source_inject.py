"""
Drives key_capture_source_spike.py's 'auto' run with injected input (alpha-plan #13).

Keys go in as scan codes through SendInput, so Windows maps them with the layout of the window in
front, exactly as for a real keyboard, and they pass the same hook chain (windows-validation C7,
2026-09-24). What injection cannot produce is Windows' own auto-repeat, so held keys stay in the
spike's manual 'confirm' run.

    uv run python spikes/key_capture_source_inject.py

Hands off the keyboard and mouse once it starts. It switches layout with Left Alt + Left Shift
(falling back to Win+Space), visits every installed layout, and switches back to the one it started
on. A line per action goes to the console and to <log>.inject.txt beside the spike's log.
"""

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.platform != "win32":
    raise SystemExit("Windows only")

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.c_void_p]


class KeybdInput(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class Input(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("ki", KeybdInput), ("pad", ctypes.c_byte * 8)]


SCANCODE, KEYUP, EXTENDED = 0x8, 0x2, 0x1
L_ALT, L_SHIFT, TAB, SPACE, ENTER, BACKSPACE, K = 0x38, 0x2A, 0x0F, 0x39, 0x1C, 0x0E, 0x25
L_WIN = 0x5B  # extended
FOUR_KEYS = (0x2C, 0x15, 0x27, 0x28)  # US z, y, ;, '
# Per language: (dead key scan, letter it composes with).
DEAD = {0x407: (0x29, 0x12), 0x40F: (0x28, 0x1E)}

lines: list[str] = []


def note(text: str) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {text}"
    print(line)
    lines.append(line)


def key(scan: int, up: bool = False, extended: bool = False) -> None:
    flags = SCANCODE | (KEYUP if up else 0) | (EXTENDED if extended else 0)
    i = Input(1, KeybdInput(0, scan, flags, 0, 0))
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(Input))


def tap(scan: int, gap: float = 0.25) -> None:
    key(scan)
    time.sleep(0.06)
    key(scan, up=True)
    time.sleep(gap)


def chord(*scans: int, extended: tuple[int, ...] = ()) -> None:
    for s in scans:
        key(s, extended=s in extended)
        time.sleep(0.05)
    for s in reversed(scans):
        key(s, up=True, extended=s in extended)
        time.sleep(0.05)
    time.sleep(0.6)


def lang_of(hwnd: int) -> int:
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    return (user32.GetKeyboardLayout(tid) or 0) & 0xFFFF


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log = Path(__file__).parent / "results" / "key_capture_source" / f"auto-{stamp}.jsonl"
    spike = subprocess.Popen(["uv", "run", "python", str(Path(__file__).parent / "key_capture_source_spike.py"),
                              "auto", str(log)])
    hwnd = 0
    for _ in range(40):
        time.sleep(0.25)
        hwnd = user32.FindWindowW(None, "Takki key-capture spike")
        if hwnd:
            break
    if not hwnd:
        raise SystemExit("spike window never appeared")
    time.sleep(1.5)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    note(f"spike window {hwnd:#x}, in front: {user32.GetForegroundWindow() == hwnd}")

    def click() -> None:
        time.sleep(0.6)  # the spike ignores clicks within 500 ms of focus coming back
        user32.PostMessageW(hwnd, 0x201, 1, (100 << 16) | 100)
        user32.PostMessageW(hwnd, 0x202, 0, (100 << 16) | 100)
        time.sleep(0.3)

    def alt_tab() -> None:
        chord(L_ALT, TAB)
        time.sleep(0.6)

    start_lang = lang_of(hwnd)
    note(f"start layout 0x{start_lang:04x}")

    for scan in (ENTER, BACKSPACE, TAB, L_SHIFT):
        tap(scan, 0.4)
    click()

    for i in (1, 2, 3):
        lang = lang_of(hwnd)
        note(f"layout {i}: 0x{lang:04x}")
        for scan in FOUR_KEYS:
            tap(scan, 0.35)
        click()
        dead = DEAD.get(lang)
        if dead:
            d, letter = dead
            for second in (letter, SPACE, d, K):
                tap(d, 0.3)
                tap(second, 0.6)
        else:
            note("  no dead key on this layout; dead-key steps left empty")
        click()
        if dead:
            for n in range(3):
                tap(dead[0], 0.3)
                alt_tab()
                away = user32.GetForegroundWindow() != hwnd
                alt_tab()
                back = user32.GetForegroundWindow() == hwnd
                note(f"  dead, alt+tab out ({'left' if away else 'DID NOT LEAVE'}) "
                     f"and back ({'back' if back else 'NOT BACK'}), then letter; try {n + 1}")
                if not back:
                    user32.SetForegroundWindow(hwnd)
                    time.sleep(0.5)
                tap(dead[1], 0.6)
        click()
        if dead:
            d, letter = dead
            for _ in range(3):
                tap(d, 0.3)
                tap(letter, 0.6)
            for second in (SPACE, K):
                tap(d, 0.3)
                tap(second, 0.6)
        click()
        before = lang_of(hwnd)
        chord(L_ALT, L_SHIFT)
        after = lang_of(hwnd)
        if after == before:
            note(f"  Left Alt + Left Shift did NOT switch (still 0x{after:04x}); trying Win+Space")
            chord(L_WIN, SPACE, extended=(L_WIN,))
            after = lang_of(hwnd)
        note(f"  switched 0x{before:04x} -> 0x{after:04x}")
        click()

    for _ in range(4):
        if lang_of(hwnd) == start_lang:
            break
        chord(L_ALT, L_SHIFT)
        if lang_of(hwnd) == start_lang:
            break
        chord(L_WIN, SPACE, extended=(L_WIN,))
    note(f"restored: 0x{lang_of(hwnd):04x} (started on 0x{start_lang:04x})")
    time.sleep(0.5)
    user32.PostMessageW(hwnd, 0x10, 0, 0)
    spike.wait(15)
    log.with_suffix(".inject.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    note(f"log: {log}")


if __name__ == "__main__":
    main()
