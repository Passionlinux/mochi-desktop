"""Normalized desktop-environment detection.

A single place to answer "what desktop and session is this?" so backends and
``main.py`` do not each re-implement string matching on ``XDG_CURRENT_DESKTOP``.

This module reads the environment only. It never touches GTK, D-Bus or the
display, so it is testable without a session and safe to import anywhere.
"""

from __future__ import annotations

from collections.abc import Mapping
import os

# Desktop identifiers Mochi recognizes. Several spelling variants map to the
# same normalized id (for example ``KDE`` and ``Plasma``).
_ALIASES: dict[str, str] = {
    "gnome": "gnome",
    "kde": "kde",
    "plasma": "kde",
    "xfce": "xfce",
    "mate": "mate",
    "cinnamon": "cinnamon",
    "lxqt": "lxqt",
    "lxde": "lxde",
    "budgie": "budgie",
    "unity": "unity",
    "pantheon": "pantheon",
    "deepin": "deepin",
    "sway": "sway",
    "hyprland": "hyprland",
    "niri": "niri",
    "river": "river",
    "wayfire": "wayfire",
    "labwc": "labwc",
}

# Compositors that implement the wlr-layer-shell protocol, where Mochi prefers
# its native Wayland overlay path over the XWayland fallback.
_WLROOTS_COMPOSITORS = frozenset(
    {"sway", "hyprland", "niri", "river", "wayfire", "labwc"}
)

_DESKTOP_VARIABLES = ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")
_SEPARATORS = ":;, \t"


def _environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _tokens(value: str) -> list[str]:
    tokens = [value]
    for separator in _SEPARATORS:
        tokens = [part for token in tokens for part in token.split(separator)]
    return [token.strip().casefold() for token in tokens if token.strip()]


def current_desktop(environ: Mapping[str, str] | None = None) -> str:
    """Return a normalized desktop id, or ``"unknown"``.

    Reads ``XDG_CURRENT_DESKTOP``, then ``XDG_SESSION_DESKTOP``, then
    ``DESKTOP_SESSION``. Each value may list several identifiers separated by
    ``:`` (for example ``ubuntu:GNOME``); the first recognized one wins.
    """
    environment = _environment(environ)
    for variable in _DESKTOP_VARIABLES:
        raw = environment.get(variable)
        if not raw:
            continue
        for token in _tokens(raw):
            if token in _ALIASES:
                return _ALIASES[token]
            for alias, normalized in _ALIASES.items():
                if alias in token:
                    return normalized
    return "unknown"


def session_type(environ: Mapping[str, str] | None = None) -> str:
    """Return ``"wayland"``, ``"x11"``, ``"tty"`` or ``"unknown"``."""
    environment = _environment(environ)
    declared = environment.get("XDG_SESSION_TYPE", "").casefold()
    if declared in {"wayland", "x11", "tty"}:
        return declared
    if environment.get("WAYLAND_DISPLAY"):
        return "wayland"
    if environment.get("DISPLAY"):
        return "x11"
    return "unknown"


def has_display(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether an X display is available (the XWayland path needs it)."""
    return bool(_environment(environ).get("DISPLAY"))


def uses_wlroots(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the session runs on a wlr-layer-shell compositor."""
    return current_desktop(environ) in _WLROOTS_COMPOSITORS
