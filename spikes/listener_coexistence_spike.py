"""
Spike: can the C7 trace listener and Takki's own listener run at once?

Alpha session 12b-1 (2026-09-24). windows-validation.md C7 compares a trace
taken *while Takki runs* against what Takki wrote, which is only meaningful
if neither low-level keyboard hook misses events because the other exists.

Starts two pynput_trace_spike.py processes (two independent WH_KEYBOARD_LL
hooks through the production PynputKeyStream), optionally real Takki on a
throwaway database (a third), then injects a scripted key sequence with
SendInput -- virtual key plus scan code, the shape a keyboard produces, so
pynput computes `char` from live modifier state exactly as it does for a
real key. Injected input traverses the same hook chain as hardware input;
what it cannot reproduce is the OS's own auto-repeat timing, which C1
checks by hand. Every trace log is then compared event-for-event with what
was sent, and with --with-takki the C7 script is run over trace A and
Takki's database, which rehearses C7 end to end.

    uv run python spikes/listener_coexistence_spike.py [--with-takki] [--rounds N]

**Safety:** keystrokes are only ever sent while the foreground window is
this spike's own sink window (or, with --with-takki, the window titled
"Takki"); the check runs before every single event and the spike aborts the
moment it fails, so nothing can be typed into an editor. Do not type while
it runs -- your keys would appear in the traces and fail the comparison.

**Layout: never changed, only checked.** Switching the layout of a thread
that owns the foreground window switches the whole session's layout under
Windows' default per-user input setting. A first version of this spike did
that and left the developer on US after a run started on German
(2026-09-24). So nothing here activates a layout. Key codes come from an
explicitly loaded US HKL (VkKeyScanExW), and the expected characters are
US English. Takki's startup check is satisfied inside the `_takki` harness
by handing verify_layout a US reading, so Takki never refuses to start
because of the developer's layout. Before every event, the target window's
*actual* layout must type every letter of the script on the same keys as US
(f j d k do on German QWERTZ) and must not have changed since sending began;
otherwise the spike aborts, which also catches a Win+Space or Alt+Shift
pressed mid-run.

Throwaway database: `_takki DB` runs takki.main.main() with database_path
patched. A spike harness only -- ADR-025 rejects a runtime override, and
windows-validation.md's D and G tiers run against the real path.
"""

import argparse
import ctypes
import ctypes.wintypes as wintypes
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

SPIKES = Path(__file__).parent
TRACE = SPIKES / "pynput_trace_spike.py"
C7 = SPIKES / "c7_trace_vs_dump.py"
SINK_TITLE = "takki coexistence sink"

US_KLID = "00000409"
US_LANGID = 0x0409
VK_SHIFT = 0xA0  # VK_LSHIFT
VK_ESCAPE = 0x1B
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1
WM_CLOSE = 0x0010


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT is the largest member; padding to its size keeps
    # sizeof(INPUT) what SendInput checks against.
    _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]  # noqa: RUF012 -- ctypes reads it


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.VkKeyScanExW.restype = ctypes.c_short
    user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, wintypes.HKL]
    user32.GetKeyboardLayout.restype = wintypes.HKL
    user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.GetKeyboardLayoutList.restype = ctypes.c_int
    user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(wintypes.HKL)]
    return user32


def _us_hkl(user32: ctypes.WinDLL) -> int:
    """Plain US English from the user's installed layouts, never loaded.

    LoadKeyboardLayout on a KLID the user lacks adds it to their session list
    -- the kind of side effect this spike exists not to have -- so a machine
    without US is refused instead.
    """
    count = user32.GetKeyboardLayoutList(0, None)
    installed = (wintypes.HKL * count)()
    user32.GetKeyboardLayoutList(count, installed)
    for hkl in installed:
        # Both words 0x0409: the plain layout, not Dvorak or US-International.
        if hkl and hkl & 0xFFFFFFFF == (US_LANGID << 16) | US_LANGID:
            return hkl
    raise SystemExit(
        f"US English ({US_KLID}) is not installed; add it in Settings > Time & language, "
        "or run this spike on a machine that has it"
    )


def _foreground_hkl(user32: ctypes.WinDLL) -> int:
    """The layout of the thread that owns the foreground window -- what pynput translates with."""
    thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    return user32.GetKeyboardLayout(thread) or 0


def _types_like_us(user32: ctypes.WinDLL, hkl: int, us: int, letters: set[str]) -> bool:
    """Whether `hkl` puts every one of `letters` on the key US does, unshifted."""
    return all(user32.VkKeyScanExW(ch, hkl) == user32.VkKeyScanExW(ch, us) for ch in letters)


def _foreground_title(user32: ctypes.WinDLL) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buffer, 256)
    return buffer.value


def _vk(user32: ctypes.WinDLL, hkl: int, name: str) -> int:
    if name == "shift":
        return VK_SHIFT
    if name == "esc":
        return VK_ESCAPE
    return user32.VkKeyScanExW(name, hkl) & 0xFF


def _send(user32: ctypes.WinDLL, vk: int, down: bool) -> None:
    scan = user32.MapVirtualKeyW(vk, 0)  # MAPVK_VK_TO_VSC
    flags = 0 if down else KEYEVENTF_KEYUP
    event = INPUT(type=INPUT_KEYBOARD)
    event.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise OSError(ctypes.get_last_error(), "SendInput failed")


# (key, down, delay after in ms). Letters only from the Stage 0 opening pair
# plus two wrong ones, so the same script is a meaningful lesson for Takki.
def _round() -> list[tuple[str, bool, int]]:
    script: list[tuple[str, bool, int]] = []

    def tap(key: str, hold: int = 60, gap: int = 450) -> None:
        script.extend([(key, True, hold), (key, False, gap)])

    tap("f")
    tap("j")
    tap("d")  # wrong
    tap("f")
    tap("j")
    # Shift+f with Shift let go first: C2's shape, "F" down and "f" up.
    script.extend([("shift", True, 40), ("f", True, 40), ("shift", False, 40), ("f", False, 450)])
    # Held j: a press, five repeats at ~33 ms (Windows' fastest typematic
    # rate), one release -- one actuation under ADR-027.
    script.append(("j", True, 250))
    script.extend([("j", True, 33)] * 5)
    script.append(("j", False, 450))
    tap("k")  # wrong
    tap("f")
    # Doubled letter, released between: two actuations.
    tap("j", gap=120)
    tap("j")
    # A burst far faster than any child types: 5 ms between events.
    for key in "fjfjfj":
        script.extend([(key, True, 5), (key, False, 5)])
    script[-1] = (script[-1][0], False, 600)
    return script


def _expected(
    user32: ctypes.WinDLL, script: list[tuple[str, bool, int]]
) -> list[tuple[bool, str | None, str | None]]:
    shift = False
    out: list[tuple[bool, str | None, str | None]] = []
    for key, down, _ in script:
        if key == "shift":
            shift = down
            out.append((down, None, "shift"))
        elif key == "esc":
            out.append((down, None, "esc"))
        else:
            out.append((down, key.upper() if shift else key, None))
    return out


def _read_trace(
    path: Path, sending_from: datetime
) -> tuple[list[tuple[bool, str | None, str | None]], list[str]]:
    """(events from the first key sent onward, anything logged before it).

    Only the sending window is compared exactly. Before it, input is not this
    spike's: 2026-09-24 saw a lone `ctrl_l` release, logged identically by
    both traces, as Takki's window came up in two of four runs -- a test must
    not fail on the machine's own events. Anything stray *during* sending
    still fails, as it should.
    """
    sys.path.insert(0, str(SPIKES))
    from c7_trace_vs_dump import read_sections

    sections = read_sections(path)
    events = sections[-1][1] if sections else []
    # 50 ms of slack for the header's wall clock against perf_counter offsets.
    cutoff = sending_from - timedelta(milliseconds=50)
    before = [
        f"{e.at:%H:%M:%S.%f}"[:-3] + f" {'PRESS' if e.pressed else 'RELEASE'} {e.char or e.name}"
        for e in events
        if e.at < cutoff
    ]
    return [(e.pressed, e.char, e.name) for e in events if e.at >= cutoff], before


def _compare(
    name: str,
    got: list[tuple[bool, str | None, str | None]],
    want: list[tuple[bool, str | None, str | None]],
) -> bool:
    if got == want:
        print(f"  {name}: {len(got)} events, identical to the {len(want)} sent")
        return True
    first = next(
        (i for i, (g, w) in enumerate(zip(got, want, strict=False)) if g != w),
        min(len(got), len(want)),
    )
    print(
        f"  {name}: **MISMATCH** -- {len(got)} events logged, {len(want)} sent; first difference at event {first}"
    )
    for i in range(max(0, first - 2), min(max(len(got), len(want)), first + 3)):
        g = got[i] if i < len(got) else "(none)"
        w = want[i] if i < len(want) else "(none)"
        print(f"    {'>' if i == first else ' '} {i:>4}: logged {g!s:<32} sent {w}")
    return False


def _run_takki(db: str) -> int:
    import takki.main as takki_main

    takki_main.database_path = lambda: Path(db)  # type: ignore[assignment]

    # A test must not fail because of whatever layout the developer's session
    # happens to be on, and must not change it either: activating a layout on
    # a foreground window's thread switches the session. So verify_layout is
    # handed a US reading -- read by HKL, nothing activated -- and whether the
    # window really types the script's letters as US is the sender's check.
    import takki.platform.windows as windows_platform

    us = _us_hkl(_user32())
    # And the language the curriculum is checked against: left to the system
    # locale, a de or is machine would refuse the US reading with exit 2.
    from takki import config

    config.LANGUAGE = "en"
    windows_platform.WindowsPlatformInterface.get_layout_positions = (  # type: ignore[method-assign]
        lambda self: windows_platform.read_layout(us)
    )
    return takki_main.main()


def _wait_for_foreground(
    user32: ctypes.WinDLL,
    title: str,
    seconds: float,
    process: "subprocess.Popen[bytes] | None" = None,
) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _foreground_title(user32) == title:
            return True
        if process is not None and process.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def main() -> int:
    if sys.platform != "win32":
        print("FAIL: Windows-only.")
        return 1
    if len(sys.argv) == 3 and sys.argv[1] == "_takki":
        return _run_takki(sys.argv[2])

    parser = argparse.ArgumentParser(
        description="Two trace hooks (and optionally Takki) under injected input"
    )
    parser.add_argument(
        "--with-takki", action="store_true", help="also run real Takki on a throwaway database"
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument(
        "--settle", type=float, default=25.0, help="seconds to let Takki's introduction finish"
    )
    args = parser.parse_args()

    user32 = _user32()
    us = _us_hkl(user32)
    work = Path(tempfile.mkdtemp(prefix="takki_coexist_"))
    print(f"Work directory: {work}")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
            timeout = winreg.QueryValueEx(key, "LowLevelHooksTimeout")[0]
    except OSError:
        timeout = "unset (Windows default)"
    print(f"LowLevelHooksTimeout: {timeout}")

    logs = [work / "trace_a.log", work / "trace_b.log"]
    traces = [
        subprocess.Popen(
            [sys.executable, str(TRACE), str(log)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        for log in logs
    ]
    takki: subprocess.Popen[bytes] | None = None
    sink = None
    db = work / "takki.sqlite"
    try:
        # Each trace writes its header after its listener has started.
        deadline = time.monotonic() + 30
        while not all(log.exists() and log.stat().st_size for log in logs):
            if time.monotonic() > deadline:
                print("FAIL: trace processes did not start")
                return 1
            time.sleep(0.2)
        time.sleep(1.0)

        if args.with_takki:
            stderr = (work / "takki_stderr.log").open("wb")
            takki = subprocess.Popen(
                [sys.executable, __file__, "_takki", str(db)], stdout=stderr, stderr=stderr
            )
            target = "Takki"
            if not _wait_for_foreground(user32, target, 20, takki):
                if takki.poll() is not None:
                    stderr.close()
                    print(
                        f"FAIL: Takki exited {takki.returncode} before its window came up: "
                        f"{(work / 'takki_stderr.log').read_text(errors='replace').strip() or '(no stderr)'}"
                    )
                    return 1
                print(
                    f"FAIL: Takki's window never took the foreground (foreground: {_foreground_title(user32)!r}); nothing sent"
                )
                return 1
            print(
                f"Takki has the foreground; waiting {args.settle:.0f} s for its introduction script"
            )
            time.sleep(args.settle)
        else:
            import pygame

            pygame.display.init()
            pygame.display.set_mode((320, 120))
            pygame.display.set_caption(SINK_TITLE)
            sink = pygame
            target = SINK_TITLE
            for _ in range(50):
                pygame.event.pump()
                if _foreground_title(user32) == target:
                    break
                time.sleep(0.1)

        script = [step for _ in range(args.rounds) for step in _round()]
        print(f"Sending {len(script)} key events ({args.rounds} rounds) to {target!r}")
        started = time.perf_counter()
        sending_from = datetime.now()
        letters = {key for key, _, _ in script if len(key) == 1}
        down_now: set[str] = set()
        layout = _foreground_hkl(user32)
        for key, down, delay in script:
            if sink is not None:
                sink.event.pump()
            if _foreground_title(user32) != target:
                print(
                    f"ABORT: foreground is now {_foreground_title(user32)!r}, not {target!r}; stopped sending"
                )
                # Never leave a key logically down in someone else's window.
                for held in down_now:
                    _send(user32, _vk(user32, us, held), False)
                return 1
            now = _foreground_hkl(user32)
            if now != layout or not _types_like_us(user32, now, us, letters):
                print(
                    f"ABORT: {target!r} is on layout 0x{now & 0xFFFF:04x}"
                    + (" (changed during the run)" if now != layout else "")
                    + f", which does not type {''.join(sorted(letters))} as US English does; "
                    "stopped sending"
                )
                for held in down_now:
                    _send(user32, _vk(user32, us, held), False)
                return 1
            _send(user32, _vk(user32, us, key), down)
            if down:
                down_now.add(key)
            else:
                down_now.discard(key)
            time.sleep(delay / 1000)
        print(f"Sent in {time.perf_counter() - started:.1f} s")
        time.sleep(1.5)
    finally:
        if takki is not None:
            hwnd = user32.FindWindowW(None, "Takki")
            if hwnd:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)  # the E9 path: SDL QUIT
            try:
                takki.wait(15)
            except subprocess.TimeoutExpired:
                takki.kill()
        if sink is not None:
            sink.display.quit()
        for trace in traces:
            trace.terminate()
            trace.wait(10)

    want = _expected(user32, script)
    print("\nEvent-for-event against what was sent:")
    results = []
    for log in logs:
        got, before = _read_trace(log, sending_from)
        if before:
            print(
                f"  {log.stem}: {len(before)} event(s) before sending, not sent by this spike: {', '.join(before)}"
            )
        results.append(_compare(log.stem, got, want))
    ok = all(results)
    if takki is not None:
        print(
            f"\nTakki exited {takki.returncode}; stderr: {(work / 'takki_stderr.log').read_text(errors='replace').strip() or '(empty)'}"
        )
        print("\nC7 over trace_a and Takki's database:")
        result = subprocess.run([sys.executable, str(C7), str(logs[0]), "--db", str(db)])
        ok = ok and result.returncode == 0 and takki.returncode == 0
    print(f"\n{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
