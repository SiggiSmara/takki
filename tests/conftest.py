import pytest


@pytest.fixture(autouse=True)
def headless_sdl(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    # Dummy SDL drivers keep the default tier deviceless (as CI's job-level env
    # does). The `audio` tier is the one place that must reach a real device, so
    # it opts out -- forcing dummy on every test silently made `-m audio` a
    # no-op that passed without touching audio hardware at all.
    #
    # `windows_only` opts out too, for the same reason one level over: the
    # PygameFocusSource "real driver" tests were forced onto the dummy driver
    # here and so had never opened a real window, laptop included (alpha
    # session 12a-2). CI's windows job still sets dummy at job level; a real
    # window is verified by hand on the laptop (windows-validation.md T0.2).
    if request.node.get_closest_marker("audio") or request.node.get_closest_marker("windows_only"):
        return
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
