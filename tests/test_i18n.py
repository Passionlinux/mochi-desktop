"""Guards for Mochi's French-first presentation layer."""

from __future__ import annotations

from string import Formatter

import pytest

from mochi import i18n
from mochi.focus import FocusPlan, FocusSession
from mochi.locale_fr import MESSAGES
from mochi.pocket import make_text_item
from mochi.pocket_window import row_model
from mochi.presence import phrases


def _dialogue_strings() -> list[str]:
    strings: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        if text not in seen:
            seen.add(text)
            strings.append(text)

    for line in phrases.INTRO_LINES:
        add(line)
    for phase_lines in phrases.BOND_DIALOGUE.values():
        for line in phase_lines:
            add(line.text)
    for values in phrases.PHRASES.values():
        for value in values:
            add(value)
    for values in phrases.CONTEXT_PHRASES.values():
        for value in values:
            add(value)
    return strings


def _placeholders(template: str) -> set[str]:
    return {
        field_name
        for _literal, field_name, _spec, _conversion in Formatter().parse(template)
        if field_name
    }


def test_french_is_the_default_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(i18n.LANGUAGE_ENVIRONMENT_VARIABLE, raising=False)

    assert i18n.current_language() == "fr"
    assert i18n.tr("Sleep") == "Dormir"


def test_english_stays_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(i18n.LANGUAGE_ENVIRONMENT_VARIABLE, "en")

    assert i18n.current_language() == "en"
    assert i18n.tr("Sleep") == "Sleep"


def test_unsupported_language_is_rejected() -> None:
    with pytest.raises(ValueError):
        i18n.set_language("de")


def test_every_dialogue_line_has_a_french_translation() -> None:
    def covered(text: str) -> bool:
        if text in MESSAGES:
            return True
        lines = text.split("\n")
        return len(lines) > 1 and all(line in MESSAGES for line in lines)

    missing = sorted(text for text in _dialogue_strings() if not covered(text))

    assert missing == []


def test_translated_markup_keeps_every_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(i18n.LANGUAGE_ENVIRONMENT_VARIABLE, raising=False)

    markup = phrases.intro_markup()

    for line in phrases.INTRO_LINES:
        assert MESSAGES[line] in markup


def test_trf_formats_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(i18n.LANGUAGE_ENVIRONMENT_VARIABLE, raising=False)

    assert i18n.trf("Bond Lv. {level}", level=3) == "Lien niv. 3"


def test_catalogue_preserves_format_placeholders() -> None:
    for source, translated in MESSAGES.items():
        assert _placeholders(source) == _placeholders(translated), source


def test_focus_phase_labels_are_french(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(i18n.LANGUAGE_ENVIRONMENT_VARIABLE, raising=False)
    session = FocusSession(FocusPlan(focus_minutes=5, break_minutes=1, rounds=2))

    assert session.phase_label == "Concentration 1 sur 2"

    session.advance(5 * 60)
    assert session.phase_label == "Pause 1 sur 2"


def test_pocket_row_labels_are_french(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(i18n.LANGUAGE_ENVIRONMENT_VARIABLE, raising=False)

    model = row_model(make_text_item("bonjour", received_at=0))

    assert model.action_label == "Voir"
    assert model.subtitle.startswith("Texte · ")


def _label_texts(widget) -> list[str]:
    from gi.repository import Gtk

    texts: list[str] = []
    if isinstance(widget, Gtk.Label):
        texts.append(widget.get_text())
    child = widget.get_first_child()
    while child is not None:
        texts.extend(_label_texts(child))
        child = child.get_next_sibling()
    return texts


def test_quick_start_window_renders_french(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gi.repository import Gtk

    from mochi.quick_start import QuickStartWindow

    monkeypatch.delenv(i18n.LANGUAGE_ENVIRONMENT_VARIABLE, raising=False)
    window = QuickStartWindow(owner=Gtk.Window())

    assert window.window.get_title() == "Faire connaissance avec Mochi 🌱"
    labels = _label_texts(window.window)
    assert "DÉMARRAGE RAPIDE" in labels
    assert "Rencontrer Mochi" in labels
    assert "Réactions d'ambiance" in labels


def test_pocket_window_renders_french(monkeypatch: pytest.MonkeyPatch) -> None:
    from mochi.pocket_window import PocketWindow

    class _EmptyController:
        items = ()
        on_changed = None

    monkeypatch.delenv(i18n.LANGUAGE_ENVIRONMENT_VARIABLE, raising=False)
    window = PocketWindow(_EmptyController())

    assert window.get_title() == "Pocket de Mochi"
    labels = _label_texts(window)
    assert "Pocket est vide. Glisse un fichier, un lien, une image ou du texte sur Mochi." in labels
    assert "Tout effacer" in labels
