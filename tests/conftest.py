"""Shared pytest configuration for Mochi.

Mochi ships French-first, but the source strings and the long-standing test
suite use the original English copy. Tests therefore run in English unless a
test explicitly opts into another language, which keeps behaviour assertions
stable while dedicated i18n tests exercise the French catalogue.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _english_presentation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the legacy suite against the original English presentation."""
    monkeypatch.setenv("MOCHI_LANG", "en")
