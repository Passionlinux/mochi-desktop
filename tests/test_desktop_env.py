import unittest

from mochi.desktop_env import (
    _WLROOTS_COMPOSITORS,
    current_desktop,
    has_display,
    session_type,
    uses_wlroots,
)


class CurrentDesktopTests(unittest.TestCase):
    def test_kde_is_normalized(self) -> None:
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "KDE"}), "kde")

    def test_plasma_is_normalized_to_kde(self) -> None:
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "Plasma"}), "kde")

    def test_gnome_suffix_form_is_normalized(self) -> None:
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}), "gnome")

    def test_hyphenated_cinnamon_is_normalized(self) -> None:
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "X-Cinnamon"}), "cinnamon")

    def test_xfce_mate_lxqt(self) -> None:
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "XFCE"}), "xfce")
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "MATE"}), "mate")
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "LXQt"}), "lxqt")

    def test_empty_environment_is_unknown(self) -> None:
        self.assertEqual(current_desktop({}), "unknown")

    def test_unrecognized_desktop_is_unknown(self) -> None:
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "MyCustomDE"}), "unknown")

    def test_falls_back_across_environment_variables(self) -> None:
        self.assertEqual(
            current_desktop({"XDG_SESSION_DESKTOP": "KDE"}), "kde"
        )
        self.assertEqual(current_desktop({"DESKTOP_SESSION": "xfce"}), "xfce")

    def test_prefers_first_recognized_identifier(self) -> None:
        self.assertEqual(
            current_desktop({"XDG_CURRENT_DESKTOP": "X-Generic:KDE", "DESKTOP_SESSION": "gnome"}),
            "kde",
        )

    def test_case_insensitive(self) -> None:
        self.assertEqual(current_desktop({"XDG_CURRENT_DESKTOP": "kde"}), "kde")


class SessionTypeTests(unittest.TestCase):
    def test_explicit_values(self) -> None:
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "wayland"}), "wayland")
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "x11"}), "x11")
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "tty"}), "tty")

    def test_case_insensitive(self) -> None:
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "Wayland"}), "wayland")

    def test_wayland_display_infers_wayland(self) -> None:
        self.assertEqual(session_type({"WAYLAND_DISPLAY": "wayland-0"}), "wayland")

    def test_display_infers_x11(self) -> None:
        self.assertEqual(session_type({"DISPLAY": ":0"}), "x11")

    def test_empty_is_unknown(self) -> None:
        self.assertEqual(session_type({}), "unknown")


class HasDisplayTests(unittest.TestCase):
    def test_present(self) -> None:
        self.assertTrue(has_display({"DISPLAY": ":0"}))

    def test_absent(self) -> None:
        self.assertFalse(has_display({}))


class UsesWlrootsTests(unittest.TestCase):
    def test_wlroots_compositors(self) -> None:
        self.assertIn("sway", _WLROOTS_COMPOSITORS)
        self.assertTrue(uses_wlroots({"XDG_CURRENT_DESKTOP": "sway"}))
        self.assertTrue(uses_wlroots({"XDG_CURRENT_DESKTOP": "Hyprland"}))

    def test_non_wlroots_desktops(self) -> None:
        self.assertFalse(uses_wlroots({"XDG_CURRENT_DESKTOP": "KDE"}))
        self.assertFalse(uses_wlroots({"XDG_CURRENT_DESKTOP": "GNOME"}))
        self.assertFalse(uses_wlroots({}))


if __name__ == "__main__":
    unittest.main()
