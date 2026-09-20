import sys
from pathlib import Path

import pytest

from takki.data_dir import data_dir, database_path, ensure_parent


def test_database_sits_in_the_app_data_directory() -> None:
    path = database_path()
    assert path.name == "takki.sqlite"
    assert path.parent == data_dir()


def test_directory_is_named_for_the_app_once() -> None:
    # appauthor=False: ADR-025's original `user_data_dir("Takki", "Takki")`
    # produced a nested Takki\Takki, which this pins against.
    parts = data_dir().parts
    assert parts[-1] == "Takki"
    assert parts[-2] != "Takki"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path layout")
def test_windows_uses_local_app_data_not_roaming() -> None:
    # ADR-011/ADR-025 as amended 2026-09-20: a WAL-mode database must not sit
    # in a roaming profile. Pins the decision, not just the library default.
    parts = [p.lower() for p in data_dir().parts]
    assert "local" in parts
    assert "roaming" not in parts


def _redirect_data_dir(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    def fake_user_data_dir(*args: object, **kwargs: object) -> str:
        return str(target)

    monkeypatch.setattr("takki.data_dir.user_data_dir", fake_user_data_dir)


def test_resolving_creates_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The invariant progress_dump.py's "cannot write" claim rests on.
    _redirect_data_dir(monkeypatch, tmp_path / "Takki")
    database_path()
    assert list(tmp_path.iterdir()) == []


def test_ensure_parent_creates_the_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _redirect_data_dir(monkeypatch, tmp_path / "Takki")
    path = ensure_parent(database_path())
    assert path.parent.is_dir()
    assert not path.exists()
