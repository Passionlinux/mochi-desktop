"""Positioning decisions for the X11 speech bubble surface."""

from mochi.presence.bubble_position import RESYNC_INTERVAL_MS, ResyncGate, should_move


class FakeClock:
    """Monotonic clock advanced by the test, in seconds."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_first_move_is_always_applied() -> None:
    assert should_move(None, (120, 40)) is True


def test_unchanged_target_is_skipped() -> None:
    assert should_move((120, 40), (120, 40)) is False


def test_changed_target_is_applied() -> None:
    assert should_move((120, 40), (121, 40)) is True
    assert should_move((120, 40), (120, 41)) is True


def test_force_reapplies_an_unchanged_target() -> None:
    assert should_move((120, 40), (120, 40), force=True) is True


def test_reset_position_reapplies() -> None:
    applied: tuple[int, int] | None = (120, 40)
    assert should_move(applied, (120, 40)) is False

    applied = None
    assert should_move(applied, (120, 40)) is True


def test_resync_gate_forces_the_first_tick() -> None:
    gate = ResyncGate(clock=FakeClock())

    assert gate.should_force() is True


def test_resync_gate_waits_for_the_interval() -> None:
    clock = FakeClock()
    gate = ResyncGate(clock=clock)

    assert gate.should_force() is True
    clock.advance(RESYNC_INTERVAL_MS / 1000 / 2)
    assert gate.should_force() is False
    clock.advance(RESYNC_INTERVAL_MS / 1000)
    assert gate.should_force() is True


def test_resync_gate_accepts_an_explicit_interval() -> None:
    clock = FakeClock()
    gate = ResyncGate(interval_seconds=2.0, clock=clock)

    assert gate.should_force() is True
    clock.advance(1.9)
    assert gate.should_force() is False
    clock.advance(0.1)
    assert gate.should_force() is True
