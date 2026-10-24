"""The cross-desktop emote-catalogue shortcut action and its CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from mochi import shortcut_signal
from mochi.app import MochiApplication
from mochi.config import ConfigStore


def _app(tmp_path: Path, *, preview: bool = False) -> MochiApplication:
    return MochiApplication(
        config=ConfigStore(tmp_path / "config.json"),
        preview_animations=preview,
    )


class RecordingRun:
    def __init__(self, *, returncode: int = 0, error: BaseException | None = None) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.returncode = returncode
        self.error = error

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.error is not None:
            raise self.error
        return type("Result", (), {"returncode": self.returncode})()


# -- Application action ---------------------------------------------------------


def test_emote_catalogue_action_is_registered(tmp_path: Path) -> None:
    assert _app(tmp_path).lookup_action("emote-catalogue") is not None


def test_preview_app_has_no_emote_catalogue_action(tmp_path: Path) -> None:
    assert _app(tmp_path, preview=True).lookup_action("emote-catalogue") is None


def test_emote_catalogue_action_opens_the_catalogue(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app._buddy = Mock()

    app.lookup_action("emote-catalogue").activate(None)

    app._buddy.show_emote_catalogue.assert_called_once_with()


# -- CLI command ----------------------------------------------------------------


def test_gdbus_command_activates_the_action() -> None:
    command = shortcut_signal.gdbus_command("/usr/bin/gdbus")

    assert command[0] == "/usr/bin/gdbus"
    assert shortcut_signal.APPLICATION_ID in command
    assert shortcut_signal.OBJECT_PATH in command
    assert "org.gtk.Actions.Activate" in command
    assert "emote-catalogue" in command


def test_missing_gdbus_reports_failure_without_running_anything() -> None:
    run = RecordingRun()

    assert shortcut_signal.main([], run=run, which=lambda _name: None) == 1
    assert run.calls == []


def test_successful_call_returns_zero() -> None:
    run = RecordingRun(returncode=0)

    result = shortcut_signal.main([], run=run, which=lambda _name: "/usr/bin/gdbus")

    assert result == 0
    assert run.calls[0][0] == shortcut_signal.gdbus_command("/usr/bin/gdbus")


def test_failed_call_returns_one() -> None:
    run = RecordingRun(returncode=1)

    assert shortcut_signal.main([], run=run, which=lambda _name: "/usr/bin/gdbus") == 1


def test_exceptions_stay_quiet() -> None:
    run = RecordingRun(error=OSError("gdbus failed"))

    assert shortcut_signal.main([], run=run, which=lambda _name: "/usr/bin/gdbus") == 1
