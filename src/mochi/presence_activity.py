"""Privacy-preserving user presence events for Mochi.

On GNOME, the optional Shell companion extension emits zero-payload
``UserIdle``/``UserActive`` signals derived from Mutter's server-global idle
monitor. Other desktops have no such helper, so a portable backend reads the
standard screen-saver idle interface instead. Either way Mochi receives only a
semantic idle/active transition; no key, pointer, window, or application
details cross the boundary.
"""

from __future__ import annotations

from collections.abc import Callable
import logging

from mochi import desktop_env
from mochi.helper_connection import HelperConnection

# Same idle threshold as the GNOME extension (USER_IDLE_AFTER_MS = 120_000), so
# behavior matches across desktops.
IDLE_THRESHOLD_SECONDS = 120.0

# How often the screen-saver idle interface is polled when it exposes idle time.
PRESENCE_POLL_SECONDS = 5.0


def idle_seconds_from_reply(reply, *, scale: float = 1.0) -> float | None:
    """Read a non-negative idle duration from a ``(u)`` D-Bus reply, or None."""
    try:
        value = reply.unpack()
    except Exception:
        return None
    if isinstance(value, tuple):
        value = value[0] if value else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return float(value) * scale


class GnomeShellPresenceBackend:
    """Receive semantic idle/active transitions from the Mochi Shell extension."""

    name = "GNOME Shell user presence"
    BUS_NAME = "io.github.mochi_desktop.Mochi.TypingMonitor"
    OBJECT_PATH = "/io/github/mochi_desktop/Mochi/TypingMonitor"
    INTERFACE_NAME = "io.github.mochi_desktop.Mochi.TypingMonitor"
    IDLE_SIGNAL_NAME = "UserIdle"
    ACTIVE_SIGNAL_NAME = "UserActive"

    def __init__(self) -> None:
        self._helper = None
        self.last_error = None
        self._on_user_idle = None
        self._on_user_active = None

    @property
    def active(self) -> bool:
        return self._helper is not None and self._helper.active

    @staticmethod
    def _load_gio():
        import gi

        from gi.repository import Gio, GLib

        return Gio, GLib

    def start(
        self, on_user_idle: Callable[[], None], on_user_active: Callable[[], None]
    ) -> bool:
        if self._helper is not None:
            return True
        self._on_user_idle = on_user_idle
        self._on_user_active = on_user_active
        self._helper = HelperConnection(
            self._load_gio,
            {
                self.IDLE_SIGNAL_NAME: self._on_idle_signal,
                self.ACTIVE_SIGNAL_NAME: self._on_active_signal,
            },
            on_state=lambda state: (
                self._on_idle_signal() if state[0] else self._on_active_signal()
            ),
            on_lost=self._on_active_signal,
        )
        if self._helper.start():
            self.last_error = None
            return True
        self.last_error = self._helper.last_error
        self.stop()
        return False

    def stop(self) -> None:
        if self._helper is not None:
            self._helper.stop()
            self._helper = None
        self._on_user_idle = None
        self._on_user_active = None

    def _on_idle_signal(self, *_ignored) -> None:
        # PRIVACY BOUNDARY: the signal is zero-payload. Ignore all Gio callback
        # bookkeeping arguments and expose only the semantic presence event.
        callback = self._on_user_idle
        if callback is not None:
            callback()

    def _on_active_signal(self, *_ignored) -> None:
        callback = self._on_user_active
        if callback is not None:
            callback()


class ScreenSaverPresenceBackend:
    """Semantic presence from the standard screen-saver idle interface.

    Tries the freedesktop and desktop-specific screen-saver names on the
    session bus. When a provider exposes idle time
    (``GetSessionIdleTime`` in seconds, or ``GetTimeSinceUserActivity`` in
    milliseconds) it is polled on a GLib timer; otherwise the payload-free
    ``ActiveChanged`` signal drives the transitions. Privacy: only an idle flag
    or idle duration is read.
    """

    name = "screen-saver idle interface"

    # (bus name, object path, interface)
    PROVIDERS = (
        ("org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver"),
        (
            "org.freedesktop.ScreenSaver",
            "/org/freedesktop/ScreenSaver",
            "org.freedesktop.ScreenSaver",
        ),
        ("org.kde.screensaver", "/ScreenSaver", "org.kde.screensaver"),
        ("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver"),
        ("org.xfce.ScreenSaver", "/org/xfce/ScreenSaver", "org.xfce.ScreenSaver"),
        ("org.mate.ScreenSaver", "/org/mate/ScreenSaver", "org.mate.ScreenSaver"),
    )
    ACTIVE_CHANGED = "ActiveChanged"
    _DBUS = "org.freedesktop.DBus"

    def __init__(self, *, gio_loader: Callable[[], tuple[object, object]] | None = None) -> None:
        self._gio_loader = gio_loader or self._load_gio
        self._connection = None
        self._subscription_id: int | None = None
        self._timer_id: int | None = None
        self._on_user_idle: Callable[[], None] | None = None
        self._on_user_active: Callable[[], None] | None = None
        self._idle_method: tuple[str, str, str, str, float] | None = None
        self._is_idle = False
        self.last_error: str | None = None

    @property
    def active(self) -> bool:
        return self._connection is not None and (
            self._subscription_id is not None or self._timer_id is not None
        )

    @staticmethod
    def _load_gio():
        import gi

        from gi.repository import Gio, GLib

        return Gio, GLib

    def start(
        self, on_user_idle: Callable[[], None], on_user_active: Callable[[], None]
    ) -> bool:
        if self.active:
            return True
        self.last_error = None
        self._on_user_idle = on_user_idle
        self._on_user_active = on_user_active
        self._is_idle = False
        try:
            self._gio, self._glib = self._gio_loader()
            self._connection = self._gio.bus_get_sync(self._gio.BusType.SESSION, None)
            if self._connection is None:
                raise RuntimeError("session D-Bus connection is unavailable")
            if self._find_idle_method():
                self._timer_id = self._glib.timeout_add_seconds(
                    max(1, int(PRESENCE_POLL_SECONDS)), self._poll
                )
                if not self._timer_id:
                    raise RuntimeError("idle poll timer could not be started")
                return True
            if self._subscribe_active_changed():
                return True
            self.last_error = "no screen-saver idle provider is available"
            self.stop()
            return False
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.stop()
            return False

    def _name_owned(self, bus_name: str) -> bool:
        try:
            reply = self._connection.call_sync(
                self._DBUS,
                "/org/freedesktop/DBus",
                self._DBUS,
                "NameHasOwner",
                self._glib.Variant.new_tuple(self._glib.Variant.new_string(bus_name)),
                self._glib.VariantType.new("(b)"),
                self._gio.DBusCallFlags.NONE,
                1_000,
                None,
            )
        except Exception:
            return False
        try:
            return bool(reply.unpack()[0])
        except Exception:
            return False

    def _find_idle_method(self) -> bool:
        methods = (("GetSessionIdleTime", 1.0), ("GetTimeSinceUserActivity", 0.001))
        for bus_name, object_path, interface in self.PROVIDERS:
            if not self._name_owned(bus_name):
                continue
            for method, scale in methods:
                try:
                    reply = self._connection.call_sync(
                        bus_name,
                        object_path,
                        interface,
                        method,
                        None,
                        self._glib.VariantType.new("(u)"),
                        self._gio.DBusCallFlags.NONE,
                        1_000,
                        None,
                    )
                except Exception:
                    continue
                if idle_seconds_from_reply(reply, scale=scale) is not None:
                    self._idle_method = (bus_name, object_path, interface, method, scale)
                    return True
        return False

    def _subscribe_active_changed(self) -> bool:
        for bus_name, object_path, interface in self.PROVIDERS:
            if not self._name_owned(bus_name):
                continue
            subscription_id = self._connection.signal_subscribe(
                bus_name,
                interface,
                self.ACTIVE_CHANGED,
                object_path,
                None,
                self._gio.DBusSignalFlags.NONE,
                self._on_active_changed,
            )
            if subscription_id:
                self._subscription_id = int(subscription_id)
                return True
        return False

    def _poll(self) -> bool:
        method = self._idle_method
        if method is None or self._connection is None:
            return False
        bus_name, object_path, interface, name, scale = method
        try:
            reply = self._connection.call_sync(
                bus_name,
                object_path,
                interface,
                name,
                None,
                self._glib.VariantType.new("(u)"),
                self._gio.DBusCallFlags.NONE,
                1_000,
                None,
            )
        except Exception:
            return True
        idle_seconds = idle_seconds_from_reply(reply, scale=scale)
        if idle_seconds is None:
            return True
        self._emit(idle_seconds >= IDLE_THRESHOLD_SECONDS)
        return True

    def _on_active_changed(
        self,
        _connection,
        _sender_name,
        _object_path,
        _interface_name,
        _signal_name,
        parameters,
    ) -> None:
        # PRIVACY BOUNDARY: the signal is a single boolean. Nothing else is read.
        try:
            active = bool(parameters.unpack()[0])
        except Exception:
            return
        self._emit(active)

    def _emit(self, idle: bool) -> None:
        if idle == self._is_idle:
            return
        self._is_idle = idle
        callback = self._on_user_idle if idle else self._on_user_active
        if callback is not None:
            callback()

    def stop(self) -> None:
        if self._timer_id is not None and self._connection is not None:
            try:
                self._glib.source_remove(self._timer_id)
            except Exception:
                pass
        self._timer_id = None
        if self._subscription_id is not None and self._connection is not None:
            try:
                self._connection.signal_unsubscribe(self._subscription_id)
            except Exception:
                pass
        self._subscription_id = None
        self._connection = None
        self._idle_method = None
        self._is_idle = False
        self._on_user_idle = None
        self._on_user_active = None


class PresenceActivityMonitor:
    """Lifecycle wrapper around the first available presence backend.

    GNOME keeps its Shell helper first because the extension may attach after
    login. Everywhere else the helper can never appear, so the portable
    screen-saver backend is tried first instead.
    """

    def __init__(
        self,
        *,
        on_user_idle: Callable[[], None],
        on_user_active: Callable[[], None],
        logger: logging.Logger | None = None,
        backend: object | None = None,
        backends: tuple | list | None = None,
        desktop: str | None = None,
    ) -> None:
        self._on_user_idle = on_user_idle
        self._on_user_active = on_user_active
        self._logger = logger or logging.getLogger(__name__)
        if backends is not None:
            self._backends = tuple(backends)
        elif backend is not None:
            self._backends = (backend,)
        else:
            self._backends = self._default_backends(desktop)
        self._backend = None
        self.available = False

    @staticmethod
    def _default_backends(desktop: str | None = None) -> tuple:
        current = desktop if desktop is not None else desktop_env.current_desktop()
        chain = []
        if current == "gnome":
            chain.append(GnomeShellPresenceBackend())
        chain.append(ScreenSaverPresenceBackend())
        return tuple(chain)

    @property
    def backend_name(self) -> str | None:
        return None if self._backend is None else self._backend.name

    def start(self) -> bool:
        if self.available:
            return True
        for backend in self._backends:
            try:
                started = backend.start(self._on_user_idle, self._on_user_active)
            except Exception as exc:
                started = False
                self._logger.debug(
                    "Presence backend %s failed during startup: %s: %s",
                    backend.name,
                    type(exc).__name__,
                    exc,
                )
            if started:
                self._backend = backend
                self.available = True
                self._logger.info("Presence awareness enabled via %s", backend.name)
                return True
            reason = getattr(backend, "last_error", None)
            if reason:
                self._logger.debug(
                    "Presence backend unavailable: %s (%s)", backend.name, reason
                )
        self._logger.debug("Presence awareness unavailable: no backend")
        return False

    def stop(self) -> None:
        backend = self._backend
        self._backend = None
        self.available = False
        if backend is None:
            return
        try:
            backend.stop()
        except Exception:
            pass
