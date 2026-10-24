"""Tiny message catalogue for Mochi's user-facing copy.

Mochi's source strings stay in English and double as translation keys. The
catalogue is French-first: ``fr`` is the default language, and setting
``MOCHI_LANG=en`` restores the original English alpha copy.

Only presentation strings go through this module. Log messages, D-Bus
identifiers, configuration keys, and anything that is not shown to the user
must keep their English source text so behaviour and tests stay stable.
"""

from __future__ import annotations

import os

from mochi.locale_fr import MESSAGES

DEFAULT_LANGUAGE = "fr"
SUPPORTED_LANGUAGES = ("fr", "en")
LANGUAGE_ENVIRONMENT_VARIABLE = "MOCHI_LANG"


def current_language() -> str:
    """Return the active language code, falling back to French."""
    raw = os.environ.get(LANGUAGE_ENVIRONMENT_VARIABLE, "").strip().lower()
    return raw if raw in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_language(language: str) -> None:
    """Select the presentation language for this process."""
    code = language.strip().lower()
    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported Mochi language: {language!r}")
    os.environ[LANGUAGE_ENVIRONMENT_VARIABLE] = code


def tr(text: str) -> str:
    """Translate one user-facing string, returning it unchanged if unknown.

    Multi-line strings (such as Mochi's introduction) are translated line by
    line so callers can compose copy without maintaining a second catalogue
    entry for every concatenation.
    """
    if current_language() != "fr":
        return text

    translated = MESSAGES.get(text)
    if translated is not None:
        return translated

    if "\n" in text:
        lines = text.split("\n")
        translated_lines = [MESSAGES.get(line, line) for line in lines]
        if translated_lines != lines:
            return "\n".join(translated_lines)

    return text


def trf(template: str, /, **values: object) -> str:
    """Translate a template that contains ``str.format`` placeholders."""
    return tr(template).format(**values)
