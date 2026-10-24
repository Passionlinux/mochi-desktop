import unittest

from mochi.main import configure_display_backend


class DisplayBackendTests(unittest.TestCase):
    def test_gnome_wayland_selects_xwayland(self) -> None:
        environment = {
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "GNOME",
            "DISPLAY": ":0",
        }

        self.assertTrue(configure_display_backend(environment))
        self.assertEqual(environment["GDK_BACKEND"], "x11")

    def test_session_default_wayland_backend_is_overridden(self) -> None:
        environment = {
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "GNOME",
            "DISPLAY": ":0",
            "GDK_BACKEND": "wayland",
        }

        self.assertTrue(configure_display_backend(environment))
        self.assertEqual(environment["GDK_BACKEND"], "x11")

    def test_mochi_native_wayland_opt_out_is_preserved(self) -> None:
        environment = {
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "GNOME",
            "DISPLAY": ":0",
            "GDK_BACKEND": "wayland",
            "MOCHI_NATIVE_WAYLAND": "1",
        }

        self.assertFalse(configure_display_backend(environment))
        self.assertEqual(environment["GDK_BACKEND"], "wayland")

    def test_kde_wayland_selects_xwayland(self) -> None:
        environment = {
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "KDE",
            "DISPLAY": ":0",
        }

        self.assertTrue(configure_display_backend(environment))
        self.assertEqual(environment["GDK_BACKEND"], "x11")

    def test_wlroots_wayland_keeps_native_layer_shell(self) -> None:
        environment = {
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "sway",
            "DISPLAY": ":0",
        }

        self.assertFalse(configure_display_backend(environment))
        self.assertNotIn("GDK_BACKEND", environment)

    def test_x11_session_is_untouched(self) -> None:
        environment = {
            "XDG_SESSION_TYPE": "x11",
            "XDG_CURRENT_DESKTOP": "XFCE",
            "DISPLAY": ":0",
        }

        self.assertFalse(configure_display_backend(environment))
        self.assertNotIn("GDK_BACKEND", environment)

    def test_wayland_without_display_is_untouched(self) -> None:
        environment = {
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "KDE",
        }

        self.assertFalse(configure_display_backend(environment))
        self.assertNotIn("GDK_BACKEND", environment)


if __name__ == "__main__":
    unittest.main()
