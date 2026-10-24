"""Command-line entry point for Mochi."""

from __future__ import annotations

import argparse
import faulthandler
import logging
import os
import signal
import sys
from collections.abc import MutableMapping
from pathlib import Path

from mochi import desktop_env
from mochi.config import ConfigStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A tiny friend for your desktop.")
    parser.add_argument("--debug", action="store_true", help="show debug logging")
    parser.add_argument(
        "--preview-animations",
        action="store_true",
        help="cycle through sprite animations with left-click",
    )
    parser.add_argument(
        "--reset-position",
        action="store_true",
        help="forget Mochi's saved position before starting",
    )
    parser.add_argument(
        "--update-ready-file",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser


def configure_display_backend(environment: MutableMapping[str, str]) -> bool:
    """Use XWayland for the buddy window where the compositor lacks layer shell.

    Mutter and KWin do not expose ``wlr-layer-shell``, so on those (and other
    non-wlroots) Wayland sessions this small standalone buddy needs the
    XWayland path to stay freely movable, sticky and positionable. wlroots
    compositors keep their native layer-shell surface, and
    ``MOCHI_NATIVE_WAYLAND=1`` opts out everywhere.
    """
    if environment.get("MOCHI_NATIVE_WAYLAND") == "1":
        return False
    if desktop_env.session_type(environment) != "wayland":
        return False
    if not desktop_env.has_display(environment):
        return False
    if desktop_env.uses_wlroots(environment):
        return False

    environment["GDK_BACKEND"] = "x11"
    return True


def enable_debug_stack_dumps() -> None:
    """`kill -USR1 <pid>` prints every Python thread's stack to stderr."""
    faulthandler.register(signal.SIGUSR1, all_threads=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected_xwayland = configure_display_backend(os.environ)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.debug:
        enable_debug_stack_dumps()
        logging.getLogger(__name__).debug(
            "Display environment: session_type=%r current_desktop=%r "
            "session_desktop=%r wayland_display=%r display=%r "
            "gdk_backend=%r forced_xwayland=%s",
            os.environ.get("XDG_SESSION_TYPE"),
            os.environ.get("XDG_CURRENT_DESKTOP"),
            os.environ.get("XDG_SESSION_DESKTOP"),
            os.environ.get("WAYLAND_DISPLAY"),
            os.environ.get("DISPLAY"),
            os.environ.get("GDK_BACKEND"),
            selected_xwayland,
        )
    if selected_xwayland:
        logging.getLogger(__name__).info(
            "Wayland without layer-shell support detected; using XWayland "
            "for the buddy window"
        )

    config = ConfigStore()
    if args.reset_position:
        config.reset_position()

    # Import GTK only when actually launching. This keeps config and state tests
    # usable on machines without a graphical session.
    try:
        from mochi.app import MochiApplication
    except (ImportError, ValueError) as error:
        logging.getLogger(__name__).error(
            "GTK4/PyGObject is required to run Mochi: %s", error
        )
        return 1

    application = MochiApplication(
        config=config,
        preview_animations=args.preview_animations,
        update_ready_file=args.update_ready_file,
    )
    return application.run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
