"""X11 XScreenSaver idle probe.

Used as a portable idle source on X11 sessions (XFCE, MATE, Cinnamon, KDE on
X11) when no screen-saver D-Bus provider exposes idle time. It reads only the
number of idle milliseconds the X server reports; nothing else is observed.

The ctypes/X11 layer is deliberately isolated here. Only ``idle_seconds_from_milliseconds``
and the ``idle_milliseconds`` contract of a probe are meant to be unit-tested;
opening a real display needs an X server.
"""

from __future__ import annotations

import ctypes
import ctypes.util


class XScreenSaverInfo(ctypes.Structure):
    """Mirror of the XScreenSaver ``XScreenSaverInfo`` C structure."""

    _fields_ = [
        ("window", ctypes.c_ulong),
        ("state", ctypes.c_int),
        ("kind", ctypes.c_int),
        ("til_or_since", ctypes.c_ulong),
        ("idle", ctypes.c_ulong),
        ("event_mask", ctypes.c_ulong),
    ]


def idle_seconds_from_milliseconds(milliseconds: object) -> float | None:
    """Convert a non-negative millisecond reading to seconds, or None."""
    if isinstance(milliseconds, bool) or not isinstance(milliseconds, (int, float)):
        return None
    if milliseconds < 0:
        return None
    return float(milliseconds) / 1000.0


class XScreenSaverIdleProbe:
    """A live XScreenSaver query bound to one open X display."""

    def __init__(self, xss, x11, display, root, info) -> None:
        self._xss = xss
        self._x11 = x11
        self._display = display
        self._root = root
        self._info = info

    def idle_milliseconds(self) -> float | None:
        if self._display is None or self._info is None:
            return None
        try:
            ok = self._xss.XScreenSaverQueryInfo(self._display, self._root, self._info)
        except Exception:
            return None
        if not ok:
            return None
        return float(self._info.contents.idle)

    def close(self) -> None:
        if self._info is not None:
            try:
                self._x11.XFree(self._info)
            except Exception:
                pass
            self._info = None
        if self._display is not None:
            try:
                self._x11.XCloseDisplay(self._display)
            except Exception:
                pass
            self._display = None


def open_idle_probe() -> XScreenSaverIdleProbe | None:
    """Open an XScreenSaver probe, or return None when X11 has no idle source."""
    xss_name = ctypes.util.find_library("Xss")
    x11_name = ctypes.util.find_library("X11")
    if xss_name is None or x11_name is None:
        return None
    try:
        xss = ctypes.CDLL(xss_name)
        x11 = ctypes.CDLL(x11_name)
    except OSError:
        return None

    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.restype = ctypes.c_int
    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XFree.restype = ctypes.c_int
    xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
    xss.XScreenSaverQueryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(XScreenSaverInfo),
    ]
    xss.XScreenSaverQueryInfo.restype = ctypes.c_int

    display = x11.XOpenDisplay(None)
    if not display:
        return None
    info = xss.XScreenSaverAllocInfo()
    if not info:
        x11.XCloseDisplay(display)
        return None
    root = x11.XDefaultRootWindow(display)
    return XScreenSaverIdleProbe(xss, x11, display, root, info)
