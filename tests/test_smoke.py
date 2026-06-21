"""Smoke test: verify takki package imports."""
import takki


def test_takki_imports() -> None:
    assert takki is not None
