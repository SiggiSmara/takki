"""
Run the real Takki on Icelandic, on a laptop with no Icelandic voice, logging every key event.

Written in alpha-plan #14b (2026-11-14) for the developer's Icelandic run, and
kept for #14c. The real main(), with four things patched in memory:

- LANGUAGE is "is", whatever the locale says.
- find_voice("is") borrows the English voice: the laptop has German and English
  SAPI voices only, and Takki stops at startup with no voice for the lesson
  language. The asks and letters are therefore spoken in English.
- The database is a fresh one under the system temp directory, never the
  developer's own, unless a path is given to continue a profile.
- Every event the focus model handles is logged with the command it produced
  (KeyDown -> Pressed, TextTyped -> TypedCharacter, ...), and every disarm
  (DISARM), to the console and to spikes/results/icelandic_run.log.

Run from the repo root, in a terminal switched to Icelandic (Win+Space) first:
Takki reads the layout of the thread that starts it, and stops if it is not
Icelandic. A process started from another program's shell may not get the
layout switched on the desktop.

    uv run python spikes/icelandic_run.py [database_path]

Close the window to stop. On a fresh database the alignment is three full
rounds: `f j a æ d k s l`, bumps first.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

import takki.focus_model as focus_model
import takki.main as takki_main
from takki.platform.windows import WindowsPlatformInterface

LOG = Path(__file__).parent / "results" / "icelandic_run.log"


def log(line: str) -> None:
    stamped = f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {line}"
    print(stamped, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as out:
        out.write(stamped + "\n")


original_handle = focus_model.FocusModel.handle


def handle(self: focus_model.FocusModel, event: object) -> object:
    command = original_handle(self, event)  # type: ignore[arg-type]
    log(f"{event!r:70} -> {command!r}")
    return command


original_disarm = WindowsPlatformInterface.disarm_dead_key


def disarm(self: WindowsPlatformInterface) -> None:
    log("DISARM")
    original_disarm(self)


original_find_voice = WindowsPlatformInterface.find_voice


def find_voice(self: WindowsPlatformInterface, language: str) -> str | None:
    return original_find_voice(self, "en" if language == "is" else language)


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        database = Path(argv[1])
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        database = Path(tempfile.gettempdir()) / f"takki_icelandic_run_{stamp}" / "takki.sqlite"
    focus_model.FocusModel.handle = handle  # type: ignore[method-assign]
    WindowsPlatformInterface.disarm_dead_key = disarm  # type: ignore[method-assign]
    WindowsPlatformInterface.find_voice = find_voice  # type: ignore[method-assign]
    takki_main.config.LANGUAGE = "is"
    takki_main.database_path = lambda: database  # type: ignore[assignment]
    log(f"=== run started, database {database}")
    code = takki_main.main()
    log(f"=== main() returned {code}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
