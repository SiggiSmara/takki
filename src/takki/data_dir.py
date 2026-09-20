"""Database path resolution (ADR-011, ADR-025).

Kept out of main.py -- which pulls in the full startup graph (pygame, pynput,
the TTS worker, ...) -- so a read-only tool like progress_dump.py can resolve
the same path without importing any of that.
"""

from pathlib import Path

DB_NAME = "takki.sqlite"


def database_path() -> Path:
    """Resolve only. Creating the directory is `ensure_parent`'s job, not this one."""
    # Resolution and creation were one function until 2026-09-20 (#12a-0
    # review). Splitting them is not tidiness: progress_dump.py calls this to
    # find the default path and advertises that it cannot write, so a mkdir
    # here made that claim false -- running the dump on a machine that has
    # never launched Takki created the directory, reported no database, and
    # left the directory behind. The default test tier did the same on every
    # developer's machine and in CI. The bite grows once the data-directory
    # decision moves the path: the writer moves, and every read-only caller
    # keeps creating the abandoned location.
    return Path.home() / "Documents" / "Takki" / DB_NAME


def ensure_parent(path: Path) -> Path:
    """Create the database's directory. Called by the writer only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
