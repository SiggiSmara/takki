import pytest


@pytest.fixture(autouse=True)
def headless_sdl(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    # Dummy SDL drivers keep the default tier deviceless (as CI's job-level env
    # does). The `audio` tier is the one place that must reach a real device, so
    # it opts out -- forcing dummy on every test silently made `-m audio` a
    # no-op that passed without touching audio hardware at all.
    if request.node.get_closest_marker("audio"):
        return
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
