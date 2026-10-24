"""Positioning decisions for the X11 speech bubble surface.

The bubble is a transparent X11 toplevel repositioned on a timer. Moving it on
every tick forced the compositor to recompose a translucent window ~45 times a
second even when nothing had changed, which is wasteful and can leave
unrepainted regions on Plasma. These decisions live here, free of GTK and X11
imports, so they are testable without a display.
"""

from __future__ import annotations

import time

#: How often a move is re-applied even when we believe the position is
#: current. Bounds the damage if a window manager or compositor moves the
#: surface behind our back.
RESYNC_INTERVAL_MS = 500


def should_move(
    applied: tuple[int, int] | None,
    target: tuple[int, int],
    *,
    force: bool = False,
) -> bool:
    """Return whether a surface at ``applied`` must be moved to ``target``.

    ``applied`` is ``None`` before the first move and after a hide, so a
    remapped window is always positioned again. ``force`` re-applies a position
    we believe is already correct; it exists for the periodic resync.
    """
    if force or applied is None:
        return True
    return applied != target


class ResyncGate:
    """Report when a forced position resync is due.

    The clock is injectable so the interval can be tested without sleeping.
    """

    def __init__(
        self,
        *,
        interval_seconds: float = RESYNC_INTERVAL_MS / 1000,
        clock=time.monotonic,
    ) -> None:
        self._interval_seconds = float(interval_seconds)
        self._clock = clock
        self._last_force: float | None = None

    def should_force(self) -> bool:
        """Return True when the interval has elapsed since the last force."""
        now = self._clock()
        if self._last_force is None or now - self._last_force >= self._interval_seconds:
            self._last_force = now
            return True
        return False
