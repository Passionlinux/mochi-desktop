import logging
import unittest

from mochi.presence_activity import (
    GnomeShellPresenceBackend,
    PresenceActivityMonitor,
    ScreenSaverPresenceBackend,
    X11ScreenSaverBackend,
)
from mochi.x11_idle import idle_seconds_from_milliseconds


class _Variant:
    def __init__(self, _signature, value):
        self.value = value

    def unpack(self):
        return self.value


class _GLib:
    Variant = _Variant


class _Gio:
    class BusType:
        SESSION = object()

    class DBusCallFlags:
        NONE = object()

    class DBusSignalFlags:
        NONE = object()

    class BusNameWatcherFlags:
        NONE = 0

    @classmethod
    def bus_watch_name_on_connection(cls, connection, name, flags, appeared, vanished):
        if connection.has_owner:
            appeared(connection, name, ":1.42")
        else:
            vanished(connection, name)
        return 1

    @staticmethod
    def bus_unwatch_name(ident):
        pass

    connection = None

    @classmethod
    def bus_get_sync(cls, _bus_type, _cancellable):
        return cls.connection


class _Connection:
    def __init__(self, *, has_owner=True):
        self.has_owner = has_owner
        self.subscriptions = []
        self.callbacks = {}
        self.unsubscribed = []
        self._next_id = 11

    def call_sync(self, *args):
        return _Variant("(b)", (self.has_owner,))

    def signal_subscribe(self, *args):
        subscription_id = self._next_id
        self._next_id += 1
        signal_name = args[2]
        self.subscriptions.append(args)
        self.callbacks[signal_name] = args[-1]
        return subscription_id

    def signal_unsubscribe(self, subscription_id):
        self.unsubscribed.append(subscription_id)


class PresenceBackendTests(unittest.TestCase):
    def _backend(self, connection):
        backend = GnomeShellPresenceBackend()
        _Gio.connection = connection
        backend._load_gio = lambda: (_Gio, _GLib)
        return backend

    def test_absent_extension_keeps_watching(self) -> None:
        backend = self._backend(_Connection(has_owner=False))
        self.assertTrue(backend.start(lambda: None, lambda: None))
        self.assertFalse(backend.active)

    def test_subscribes_to_idle_and_active_zero_payload_signals(self) -> None:
        connection = _Connection()
        backend = self._backend(connection)
        idle_calls = 0
        active_calls = 0

        def idle():
            nonlocal idle_calls
            idle_calls += 1

        def active():
            nonlocal active_calls
            active_calls += 1

        self.assertTrue(backend.start(idle, active))
        self.assertTrue(backend.active)
        self.assertIn(backend.IDLE_SIGNAL_NAME, connection.callbacks)
        self.assertIn(backend.ACTIVE_SIGNAL_NAME, connection.callbacks)

        connection.callbacks[backend.IDLE_SIGNAL_NAME](object(), object(), object())
        connection.callbacks[backend.ACTIVE_SIGNAL_NAME](object(), object(), object())
        self.assertEqual(idle_calls, 1)
        self.assertEqual(active_calls, 1)

    def test_callbacks_ignore_dbus_payload_objects(self) -> None:
        class Explosive:
            def __repr__(self):
                raise AssertionError("presence callback payload must not be formatted")

            def __str__(self):
                raise AssertionError("presence callback payload must not be inspected")

        backend = GnomeShellPresenceBackend()
        calls = []
        backend._on_user_idle = lambda: calls.append("idle")
        backend._on_user_active = lambda: calls.append("active")
        secret = Explosive()

        backend._on_idle_signal(secret, secret, secret)
        backend._on_active_signal(secret, secret, secret)
        self.assertEqual(calls, ["idle", "active"])
        self.assertNotIn(secret, vars(backend).values())

    def test_stop_unsubscribes_both_once(self) -> None:
        connection = _Connection()
        backend = self._backend(connection)
        self.assertTrue(backend.start(lambda: None, lambda: None))

        backend.stop()
        backend.stop()
        self.assertEqual(connection.unsubscribed, [11, 12])
        self.assertFalse(backend.active)


class _FakeBackend:
    name = "fake presence"

    def __init__(self, available=True):
        self.available = available
        self.last_error = None if available else "unavailable"
        self.idle = None
        self.active = None
        self.stop_calls = 0

    def start(self, idle, active):
        if not self.available:
            return False
        self.idle = idle
        self.active = active
        return True

    def stop(self):
        self.stop_calls += 1


class PresenceMonitorTests(unittest.TestCase):
    def test_monitor_forwards_semantic_presence_events(self) -> None:
        backend = _FakeBackend()
        events = []
        monitor = PresenceActivityMonitor(
            on_user_idle=lambda: events.append("idle"),
            on_user_active=lambda: events.append("active"),
            backend=backend,
        )
        self.assertTrue(monitor.start())
        backend.idle()
        backend.active()
        self.assertEqual(events, ["idle", "active"])
        self.assertEqual(monitor.backend_name, "fake presence")

    def test_unavailable_backend_fails_gracefully(self) -> None:
        backend = _FakeBackend(available=False)
        monitor = PresenceActivityMonitor(
            on_user_idle=lambda: None,
            on_user_active=lambda: None,
            backend=backend,
            logger=logging.getLogger("presence-test"),
        )
        self.assertFalse(monitor.start())
        self.assertIsNone(monitor.backend_name)

    def test_stop_is_idempotent(self) -> None:
        backend = _FakeBackend()
        monitor = PresenceActivityMonitor(
            on_user_idle=lambda: None,
            on_user_active=lambda: None,
            backend=backend,
        )
        self.assertTrue(monitor.start())
        monitor.stop()
        monitor.stop()
        self.assertEqual(backend.stop_calls, 1)


class _ScreenSaverGLib:
    class VariantType:
        @staticmethod
        def new(signature):
            return signature

    class Variant:
        @staticmethod
        def new_string(value):
            return value

        @staticmethod
        def new_tuple(values):
            return tuple(values)

    def __init__(self):
        self.timers = {}
        self.removed = []
        self._next = 1

    def timeout_add_seconds(self, _seconds, callback):
        identifier = self._next
        self._next += 1
        self.timers[identifier] = callback
        return identifier

    def source_remove(self, identifier):
        self.removed.append(identifier)
        self.timers.pop(identifier, None)


class _ScreenSaverConnection:
    def __init__(self, *, has_owner=True, methods=None):
        self.has_owner = has_owner
        self.methods = dict(methods or {})
        self.subscriptions = []
        self.callbacks = {}
        self.unsubscribed = []
        self._next = 11

    def call_sync(self, bus, path, interface, method, params, reply_type, flags, timeout, cancellable):
        if method == "NameHasOwner":
            return _Variant("(b)", (self.has_owner,))
        outcome = self.methods.get(method)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            raise RuntimeError(f"{method} is not provided")
        if callable(outcome):
            outcome = outcome()
        return _Variant("(u)", (outcome,))

    def signal_subscribe(self, *args):
        identifier = self._next
        self._next += 1
        self.subscriptions.append(args)
        self.callbacks[args[2]] = args[-1]
        return identifier

    def signal_unsubscribe(self, identifier):
        self.unsubscribed.append(identifier)


class _ScreenSaverGio:
    class BusType:
        SESSION = object()

    class DBusCallFlags:
        NONE = object()

    class DBusSignalFlags:
        NONE = object()

    connection = None

    @classmethod
    def bus_get_sync(cls, _bus_type, _cancellable):
        return cls.connection


class ScreenSaverPresenceBackendTests(unittest.TestCase):
    def _backend(self, connection):
        _ScreenSaverGio.connection = connection
        glib = _ScreenSaverGLib()
        backend = ScreenSaverPresenceBackend(
            gio_loader=lambda: (_ScreenSaverGio, glib)
        )
        return backend, glib

    def test_idle_time_crossing_emits_once_per_edge(self) -> None:
        connection = _ScreenSaverConnection(has_owner=True)
        values = [10, 200, 250, 5]
        connection.methods = {
            "GetSessionIdleTime": lambda *_: values.pop(0)
        }
        backend, glib = self._backend(connection)
        events = []
        self.assertTrue(backend.start(lambda: events.append("idle"), lambda: events.append("active")))
        self.assertEqual(len(glib.timers), 1)
        poll = next(iter(glib.timers.values()))

        poll()  # 10s: below threshold, no event
        poll()  # 200s: idle
        poll()  # 250s: still idle, no duplicate
        poll()  # 5s: back to active
        self.assertEqual(events, ["idle", "active"])

    def test_no_provider_fails_with_reason(self) -> None:
        connection = _ScreenSaverConnection(has_owner=False)
        backend, _glib = self._backend(connection)
        self.assertFalse(backend.start(lambda: None, lambda: None))
        self.assertFalse(backend.active)
        self.assertIsNotNone(backend.last_error)

    def test_active_changed_signal_drives_transitions(self) -> None:
        connection = _ScreenSaverConnection(has_owner=True)
        condition = RuntimeError("method not provided")
        connection.methods = {
            "GetSessionIdleTime": condition,
            "GetTimeSinceUserActivity": condition,
        }
        backend, _glib = self._backend(connection)
        events = []
        self.assertTrue(
            backend.start(lambda: events.append("idle"), lambda: events.append("active"))
        )
        self.assertIn(ScreenSaverPresenceBackend.ACTIVE_CHANGED, connection.callbacks)

        payload = lambda value: _Variant("(b)", (value,))
        connection.callbacks[ScreenSaverPresenceBackend.ACTIVE_CHANGED](
            None, None, None, None, None, payload(True)
        )
        connection.callbacks[ScreenSaverPresenceBackend.ACTIVE_CHANGED](
            None, None, None, None, None, payload(True)
        )
        connection.callbacks[ScreenSaverPresenceBackend.ACTIVE_CHANGED](
            None, None, None, None, None, payload(False)
        )
        self.assertEqual(events, ["idle", "active"])

    def test_stop_cancels_timer_and_unsubscribes_once(self) -> None:
        connection = _ScreenSaverConnection(has_owner=True)
        connection.methods = {"GetSessionIdleTime": 5}
        backend, glib = self._backend(connection)
        self.assertTrue(backend.start(lambda: None, lambda: None))
        backend.stop()
        backend.stop()
        self.assertEqual(len(glib.removed), 1)
        self.assertFalse(backend.active)


class PresenceChainTests(unittest.TestCase):
    def test_default_chain_skips_gnome_off_gnome(self) -> None:
        chain = PresenceActivityMonitor._default_backends("kde")
        self.assertEqual(len(chain), 2)
        self.assertIsInstance(chain[0], ScreenSaverPresenceBackend)
        self.assertIsInstance(chain[1], X11ScreenSaverBackend)

    def test_default_chain_keeps_gnome_first_on_gnome(self) -> None:
        chain = PresenceActivityMonitor._default_backends("gnome")
        self.assertIsInstance(chain[0], GnomeShellPresenceBackend)
        self.assertIsInstance(chain[1], ScreenSaverPresenceBackend)
        self.assertIsInstance(chain[2], X11ScreenSaverBackend)

    def test_first_starting_backend_wins(self) -> None:
        failing = _FakeBackend(available=False)
        working = _FakeBackend()
        monitor = PresenceActivityMonitor(
            on_user_idle=lambda: None,
            on_user_active=lambda: None,
            backends=(failing, working),
        )
        self.assertTrue(monitor.start())
        self.assertEqual(monitor.backend_name, "fake presence")
        self.assertEqual(failing.stop_calls, 0)


class X11IdleHelperTests(unittest.TestCase):
    def test_milliseconds_to_seconds(self) -> None:
        self.assertEqual(idle_seconds_from_milliseconds(250_000), 250.0)
        self.assertEqual(idle_seconds_from_milliseconds(0), 0.0)

    def test_invalid_values_return_none(self) -> None:
        self.assertIsNone(idle_seconds_from_milliseconds(None))
        self.assertIsNone(idle_seconds_from_milliseconds(-1))
        self.assertIsNone(idle_seconds_from_milliseconds(True))
        self.assertIsNone(idle_seconds_from_milliseconds("5"))


class _FakeProbe:
    def __init__(self, values) -> None:
        self.values = list(values)
        self.closed = 0

    def idle_milliseconds(self):
        if not self.values:
            return None
        return self.values.pop(0)

    def close(self) -> None:
        self.closed += 1


class X11ScreenSaverBackendTests(unittest.TestCase):
    def _backend(self, probe, glib):
        return X11ScreenSaverBackend(
            probe_factory=lambda: probe,
            gio_loader=lambda: (_ScreenSaverGio, glib),
        )

    def test_missing_probe_fails_with_reason(self) -> None:
        backend = self._backend(None, _ScreenSaverGLib())
        self.assertFalse(backend.start(lambda: None, lambda: None))
        self.assertIsNotNone(backend.last_error)

    def test_crossing_threshold_emits_edges(self) -> None:
        probe = _FakeProbe([10_000, 200_000, 250_000, 5_000])
        glib = _ScreenSaverGLib()
        backend = self._backend(probe, glib)
        events = []
        self.assertTrue(
            backend.start(lambda: events.append("idle"), lambda: events.append("active"))
        )
        poll = next(iter(glib.timers.values()))
        poll()
        poll()
        poll()
        poll()
        self.assertEqual(events, ["idle", "active"])
        self.assertTrue(backend.active)

    def test_stop_closes_probe_and_removes_timer_once(self) -> None:
        probe = _FakeProbe([10_000])
        glib = _ScreenSaverGLib()
        backend = self._backend(probe, glib)
        self.assertTrue(backend.start(lambda: None, lambda: None))
        backend.stop()
        backend.stop()
        self.assertEqual(probe.closed, 1)
        self.assertEqual(len(glib.removed), 1)
        self.assertFalse(backend.active)
