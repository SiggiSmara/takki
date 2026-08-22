import time

from takki.clock import Clock, SystemClock
from tests.fakes.fake_clock import FakeClock

# Static structural conformance — pyright fails if either drifts from the Protocol.
_system_conforms: Clock = SystemClock()
_fake_conforms: Clock = FakeClock()


class TestSystemClock:
    def test_reads_the_process_monotonic_clock(self) -> None:
        before = time.monotonic()
        reading = SystemClock().monotonic()
        after = time.monotonic()
        assert before <= reading <= after

    def test_never_goes_backwards(self) -> None:
        clock = SystemClock()
        first = clock.monotonic()
        assert clock.monotonic() >= first


class TestFakeClock:
    def test_starts_at_zero_by_default(self) -> None:
        assert FakeClock().monotonic() == 0.0

    def test_starts_at_the_given_time(self) -> None:
        assert FakeClock(12.5).monotonic() == 12.5

    def test_does_not_move_on_its_own(self) -> None:
        clock = FakeClock()
        assert clock.monotonic() == clock.monotonic()

    def test_set_replaces_the_time(self) -> None:
        clock = FakeClock(3.0)
        clock.set(1.0)
        assert clock.monotonic() == 1.0

    def test_advance_adds_to_the_time(self) -> None:
        clock = FakeClock(1.0)
        clock.advance(0.25)
        clock.advance(0.25)
        assert clock.monotonic() == 1.5
