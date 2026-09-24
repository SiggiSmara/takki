"""
Spike: how fast the unfiltered SDL queue fills under a moving mouse (E10)

Alpha session 12b-1 (2026-09-24). PygameFocusSource.poll() takes three
event types off SDL's queue and leaves the rest, and SDL refuses new events
-- QUIT included -- once 65,535 are queued. Windows coalesces mouse moves
to at most one WM_MOUSEMOVE per message pump, so the fill rate is bounded
by how often the loop pumps (TICK_HZ), and E10's soak has to outlast
65,535 / that rate or it passes without ever reaching the cap.

    uv run python spikes/sdl_queue_soak.py measure [--seconds 10]
        Own window, pumped the way poll() pumps it at TICK_HZ; moves the
        cursor inside it and reports how many events were left queued per
        second, and the soak time that implies.
    uv run python spikes/sdl_queue_soak.py drive [--minutes 25]
        E10's mouse, for the hands-on run: waits for the window titled
        "Takki" to come to the front, then circles the cursor inside it,
        pausing whenever another window is in front, and prints a progress
        line per minute of motion. Then close Takki with the mouse.

Both stop the moment the cursor is not where this script last put it --
move the mouse yourself to take it back -- and neither moves it while
another window is in front.
"""

import argparse
import ctypes
import ctypes.wintypes as wintypes
import math
import os
import sys
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

SDL_MAX_QUEUED_EVENTS = 65535
STEP_HZ = 250  # cursor moves per second: well above any pump rate, so the pump is the bound


def _user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    # Physical pixels for Set/GetCursorPos alike; a DPI-unaware process gets
    # scaled coordinates back that do not round-trip, which reads as the user
    # having moved the mouse.
    user32.SetProcessDPIAware()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    return user32


class Mouse:
    """Circles the cursor inside `title`'s client area; refuses to fight the user."""

    def __init__(self, user32: ctypes.WinDLL, title: str) -> None:
        self._user32 = user32
        self._title = title
        self._last: tuple[int, int] | None = None
        self._angle = 0.0

    def _foreground(self) -> int | None:
        hwnd = self._user32.GetForegroundWindow()
        buffer = ctypes.create_unicode_buffer(256)
        self._user32.GetWindowTextW(hwnd, buffer, 256)
        return hwnd if buffer.value == self._title else None

    def in_front(self) -> bool:
        return self._foreground() is not None

    def forget(self) -> None:
        # While another window is in front the user may move the mouse freely;
        # only a move made while we are driving counts as taking it back.
        self._last = None

    def step(self) -> str | None:
        """Move once; a reason to stop, or None."""
        point = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(point))
        if (
            self._last is not None
            and max(abs(point.x - self._last[0]), abs(point.y - self._last[1])) > 2
        ):
            return (
                f"the mouse was moved by hand (put at {self._last}, found at {(point.x, point.y)})"
            )
        hwnd = self._foreground()
        if hwnd is None:
            return f"{self._title!r} is not the foreground window"
        rect = wintypes.RECT()
        self._user32.GetClientRect(hwnd, ctypes.byref(rect))
        centre = wintypes.POINT(rect.right // 2, rect.bottom // 2)
        self._user32.ClientToScreen(hwnd, ctypes.byref(centre))
        radius = max(5, min(rect.right, rect.bottom) // 4)
        self._angle += 0.15
        x = centre.x + int(radius * math.cos(self._angle))
        y = centre.y + int(radius * math.sin(self._angle))
        self._user32.SetCursorPos(x, y)
        self._last = (x, y)
        return None


def measure(seconds: float) -> int:
    import pygame

    from takki import config

    pygame.display.init()
    pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    title = "takki sdl queue soak"
    pygame.display.set_caption(title)
    user32 = _user32()
    for _ in range(50):
        pygame.event.get([pygame.WINDOWFOCUSGAINED, pygame.WINDOWFOCUSLOST, pygame.QUIT])
        if Mouse(user32, title)._foreground():
            break
        time.sleep(0.1)
    # Start from an empty queue so the count is only what the soak added.
    pygame.event.clear()
    mouse = Mouse(user32, title)
    frame = 1.0 / config.TICK_HZ
    started = time.monotonic()
    next_frame = next_step = started
    stopped = None
    while time.monotonic() - started < seconds and stopped is None:
        now = time.monotonic()
        if now >= next_step:
            stopped = mouse.step()
            next_step += 1.0 / STEP_HZ
        if now >= next_frame:
            # Exactly poll()'s filtered get: everything else stays queued.
            pygame.event.get([pygame.WINDOWFOCUSGAINED, pygame.WINDOWFOCUSLOST, pygame.QUIT])
            next_frame += frame
        time.sleep(0.001)
    elapsed = time.monotonic() - started
    left = pygame.event.get()
    pygame.display.quit()
    by_type: dict[str, int] = {}
    for event in left:
        name = pygame.event.event_name(event.type)
        by_type[name] = by_type.get(name, 0) + 1
    rate = len(left) / elapsed if elapsed else 0.0
    print(
        f"{elapsed:.1f} s at TICK_HZ={config.TICK_HZ}: {len(left)} events left queued ({rate:.1f}/s)"
    )
    print(
        "  "
        + ", ".join(
            f"{name} {count}" for name, count in sorted(by_type.items(), key=lambda kv: -kv[1])
        )
    )
    if stopped:
        print(f"  stopped early: {stopped}")
    if rate:
        print(
            f"Queue full after {SDL_MAX_QUEUED_EVENTS / rate / 60:.1f} min of continuous motion at this rate"
        )
    return 0 if stopped is None else 1


def drive(minutes: float) -> int:
    user32 = _user32()
    mouse = Mouse(user32, "Takki")
    print(
        f"Waiting for Takki's window to come to the front (Alt+Tab to it); then {minutes:.0f} min of motion."
    )
    print("Pauses while another window is in front. Move the mouse over Takki to stop early.")
    deadline = time.monotonic() + 60
    while not mouse.in_front():
        if time.monotonic() > deadline:
            print("Takki never came to the front; nothing moved.")
            return 1
        time.sleep(0.1)
    driven = 0.0
    reported = 0
    last = time.monotonic()
    while driven < minutes * 60:
        now = time.monotonic()
        if not mouse.in_front():
            mouse.forget()
            last = now
            time.sleep(0.1)
            continue
        driven += now - last
        last = now
        stopped = mouse.step()
        if stopped:
            print(f"Stopped after {driven / 60:.1f} min of motion: {stopped}")
            return 1
        if int(driven // 60) > reported:
            reported = int(driven // 60)
            print(f"  {reported} min")
        time.sleep(1.0 / STEP_HZ)
    print(
        f"Done: {minutes:.0f} min of motion over Takki. Keep practising; close Takki with the mouse at the end (E10)."
    )
    return 0


def main() -> int:
    if sys.platform != "win32":
        print("FAIL: Windows-only.")
        return 1
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("measure").add_argument("--seconds", type=float, default=10.0)
    sub.add_parser("drive").add_argument("--minutes", type=float, default=25.0)
    args = parser.parse_args()
    return measure(args.seconds) if args.mode == "measure" else drive(args.minutes)


if __name__ == "__main__":
    sys.exit(main())
