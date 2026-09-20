"""Where Takki's persistent files live (ADR-011, ADR-025).

Kept out of main.py -- which pulls in the full startup graph (pygame, pynput,
the TTS worker, ...) -- so a read-only tool like progress_dump.py can resolve
the same path without importing any of that.
"""

from pathlib import Path

from platformdirs import user_data_dir

DB_NAME = "takki.sqlite"
APP_NAME = "Takki"


def data_dir() -> Path:
    """The per-user application data directory. Resolve only -- creates nothing."""
    # appauthor=False because Takki has no separate vendor: the default would
    # nest the app inside an identically-named author directory
    # (AppData\Local\Takki\Takki), which is what ADR-025's original
    # `user_data_dir("Takki", "Takki")` actually produced.
    #
    # roaming is left at its default (False), so this is %LOCALAPPDATA% and
    # not the %APPDATA% ADR-025's table named. That is deliberate and the ADR
    # is amended to match: a roaming profile syncs at logon and logoff, and
    # this database runs in WAL mode (ADR-011), whose `-wal` and `-shm`
    # sidecars do not sync coherently with the main file. On a school domain
    # -- a target architecture.md names explicitly -- roaming it would risk
    # corruption on every logoff and add the database's full size to the
    # logon cost. A database belongs in local app data.
    return Path(user_data_dir(APP_NAME, appauthor=False))


def database_path() -> Path:
    """Resolve only. Creating the directory is `ensure_parent`'s job, not this one."""
    # Resolution and creation were one function until 2026-09-20 (#12a-0
    # review). Splitting them is not tidiness: progress_dump.py calls this to
    # find the default path and advertises that it cannot write, so a mkdir
    # here made that claim false -- running the dump on a machine that has
    # never launched Takki created the directory, reported no database, and
    # left the directory behind. The default test tier did the same on every
    # developer's machine and in CI.
    return data_dir() / DB_NAME


def ensure_parent(path: Path) -> Path:
    """Create the database's directory. Called by the writer only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
