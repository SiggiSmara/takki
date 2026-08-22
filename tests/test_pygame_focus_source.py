import queue

import pytest

from takki.display.focus import FocusEvent, PygameFocusSource

# Real WINDOWFOCUSGAINED/LOST transitions and a genuine request_foreground()
# raise need a real SDL video driver -- unreachable under SDL_VIDEODRIVER=dummy
# (this dev box, and the linux CI job). These are smoke tests only: neither
# GitHub Actions windows-latest (headless, no interactive user) nor an
# automated test can reliably force a real OS focus transition without a
# human at the keyboard, so full confirmation is session 12's manual laptop
# run, not this tier. See the session report for the CI env-var gap this
# surfaces (windows-latest currently also sets SDL_VIDEODRIVER=dummy).
pytestmark = pytest.mark.windows_only


def test_construct_poll_and_close_on_a_real_driver() -> None:
    outbound: queue.Queue[FocusEvent] = queue.Queue()
    source = PygameFocusSource(outbound)
    source.poll()
    source.close()


def test_request_foreground_does_not_raise_on_a_real_driver() -> None:
    # Returns nothing -- SDL_RaiseWindow is async, so whether the raise
    # took effect is only observable as a later FocusGained event.
    outbound: queue.Queue[FocusEvent] = queue.Queue()
    source = PygameFocusSource(outbound)
    source.request_foreground()
    source.close()
