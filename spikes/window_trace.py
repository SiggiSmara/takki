"""
Trace: what Takki's own window reports for each key, through the production reader.

#14a (alpha-plan, 2026-11-14). The window replaces pynput as the key source
(#13), so tier C's evidence (windows-validation.md) is taken from here and no
longer from pynput_trace_spike.py. The window is a real PygameFocusSource, so
it is Takki's window by construction (same set_mode, same text-input state),
and every key event goes through takki.input.window_keys.WindowKeyReader.

One line per event, stamped at the drain with the tick it was drained in:
events on one tick reached Takki together. SDL events carry no time of their
own here, so a stamp is accurate to one tick (~17 ms).

    DOWN / UP   sdl=<SDL scancode> set1=<Windows scan code, then ` ext` if
                extended> cell=<(row, col) on the grid, or ->
                key=<SDL keycode> '<name>'
    TEXT        '<text>' <code points> fresh|repeat sdl=<key it belongs to>
    KEYMAP      the keyboard layout changed (Win+Space)
    FOCUS       gained / lost; QUIT ends the trace

Run from the repo root:
    uv run python spikes/window_trace.py [output_path]

Appends to spikes/results/window_trace.log by default. Give the window focus
and type; close the window (or Ctrl+C in this console) to stop. Switch layout
or Caps Lock before typing what a check needs, as tier C says.
"""

import queue
import sys
from datetime import datetime
from pathlib import Path

import pygame

from takki import config
from takki.clock import SleepFrameLimiter
from takki.display.focus import FocusEvent, PygameFocusSource
from takki.events import Quit
from takki.input.window_keys import KeyDown, KeymapChanged, KeyUp, TextTyped, WindowKeyReader
from takki.platform.layout import scan_code_grid
from takki.platform.scan_codes import SDL_TO_SET1

DEFAULT_LOG_PATH = Path(__file__).parent / "results" / "window_trace.log"


def describe_key(scancode: int, key: int) -> str:
    set1 = SDL_TO_SET1.get(scancode)
    if set1 is None:
        where = "set1=?    cell=-"
    else:
        code, extended = set1
        cell = None if extended else scan_code_grid().get(code)
        where = f"set1=0x{code:02x}{' ext' if extended else '    '} cell={cell or '-'}"
    # pygame names no dead key (`´` is key 180, name ''); a printable key's
    # code is its character, so show that instead.
    shown = chr(key) if 0 < key < 0x40000000 else ""
    name = pygame.key.name(key) or (shown if shown.isprintable() else "")
    return f"sdl={scancode:<3} {where} key={key} {name!r}"


def describe_text(event: TextTyped) -> str:
    points = " ".join(f"U+{ord(c):04X}" for c in event.text)
    return f"{event.text!r} {points} {'fresh' if event.fresh else 'repeat'} sdl={event.scancode}"


def main(argv: list[str]) -> int:
    log_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)

    seeded: queue.Queue[FocusEvent | Quit] = queue.Queue()
    focus = PygameFocusSource(seeded)
    reader = WindowKeyReader()
    frames = SleepFrameLimiter()
    tick = 0

    with log_path.open("a", encoding="utf-8") as log:

        def emit(line: str) -> None:
            stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            out = f"{stamp} t{tick:<6} {line}"
            print(out)
            log.write(out + "\n")
            log.flush()

        log.write(
            f"\n=== window trace started {datetime.now().isoformat(timespec='seconds')}"
            f" (pygame {pygame.version.ver}, SDL {'.'.join(map(str, pygame.get_sdl_version()))},"
            f" shape {config.KEYBOARD_SHAPE}) ===\n"
        )
        print(f"Tracing to {log_path}. Type in the Takki window; close it to stop.\n")
        emit(f"SEED   {type(seeded.get_nowait()).__name__}")
        try:
            running = True
            while running:
                tick += 1
                # The tool's one drain. PygameFocusSource.poll() is not called:
                # in 14a it still drops key events. 14b joins the reader to
                # poll() and this tool moves onto it.
                for ev in pygame.event.get():
                    out = reader.read(ev)
                    if isinstance(out, KeyDown):
                        emit("DOWN   " + describe_key(out.scancode, out.key))
                    elif isinstance(out, KeyUp):
                        emit("UP     " + describe_key(out.scancode, out.key))
                    elif isinstance(out, TextTyped):
                        emit("TEXT   " + describe_text(out))
                    elif isinstance(out, KeymapChanged):
                        emit("KEYMAP")
                    elif ev.type == pygame.WINDOWFOCUSGAINED:
                        emit("FOCUS  gained")
                    elif ev.type == pygame.WINDOWFOCUSLOST:
                        emit("FOCUS  lost")
                    elif ev.type == pygame.QUIT:
                        emit("QUIT")
                        running = False
                frames.wait()
        except KeyboardInterrupt:
            pass
        finally:
            focus.close()
    print(f"\nStopped. Trace appended to {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
