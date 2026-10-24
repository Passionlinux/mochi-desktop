"""``mochi-emote-catalogue``: open the emote catalogue in a running Mochi.

Desktops without the GNOME Shell keybinding bridge (KDE Plasma, XFCE, MATE,
Cinnamon) can bind a keyboard shortcut to this command. It activates the same
``emote-catalogue`` application action the GNOME helper triggers, through the
standard ``org.gtk.Actions`` interface the running Mochi already exports, so no
new bus name or socket is needed.

The command stays quiet: it writes no output and only reports failure through
its exit code.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import shutil
import subprocess
import sys

APPLICATION_ID = "io.github.mochi_desktop.Mochi"
OBJECT_PATH = "/io/github/mochi_desktop/Mochi"
ACTION_NAME = "emote-catalogue"
GDBUS_TIMEOUT_SECONDS = 1
PROCESS_TIMEOUT_SECONDS = 1.5


def gdbus_command(gdbus: str) -> list[str]:
    """Build the ``gdbus`` call that activates the emote-catalogue action."""
    return [
        gdbus,
        "call",
        "--session",
        "--timeout",
        str(GDBUS_TIMEOUT_SECONDS),
        "--dest",
        APPLICATION_ID,
        "--object-path",
        OBJECT_PATH,
        "--method",
        "org.gtk.Actions.Activate",
        ACTION_NAME,
        "[]",
        "{}",
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    run: Callable[..., object] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> int:
    """Activate the action in the running Mochi; return 0 only on success."""
    del argv  # No arguments: the command is a single desktop-shortcut action.
    try:
        gdbus = which("gdbus")
        if gdbus is None:
            return 1
        result = run(
            gdbus_command(gdbus),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except BaseException:
        # A missing or unresponsive Mochi must never surface a traceback from a
        # desktop shortcut.
        return 1
    return 0 if getattr(result, "returncode", 1) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
