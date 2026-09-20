from pathlib import Path

import pytest

from takki.data_dir import database_path, ensure_parent


def test_returns_takki_sqlite_under_documents() -> None:
    path = database_path()
    assert path.name == "takki.sqlite"
    assert path.parent.name == "Takki"


def test_resolving_creates_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The invariant progress_dump.py's "cannot write" claim rests on.
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    database_path()
    assert list(tmp_path.iterdir()) == []


def test_ensure_parent_creates_the_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    path = ensure_parent(database_path())
    assert path.parent.is_dir()
    assert not path.exists()
