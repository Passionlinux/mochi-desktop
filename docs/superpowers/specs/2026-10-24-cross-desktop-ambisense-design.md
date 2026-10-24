# Cross-Desktop AmbiSense — Design

**Date:** 2026-10-24

**Builds on:** `docs/ambisense.md`, the GNOME helper shipped in
`gnome-extension/mochi-typing@miflow13/`, and the i18n layer in
`src/mochi/i18n.py`

**Status:** approved 2026-10-24. Decisions recorded below; implementation
follows `docs/superpowers/plans/2026-10-24-cross-desktop-ambisense.md`.

## Decisions (2026-10-24)

1. **Phase 2 (application/file context): declined.** Mochi will not read
   `WM_CLASS` or AT-SPI application names inside its own process for now. App
   and file-browsing context stays GNOME-only. The section is kept as a
   documented future option.
2. **Shortcuts: emote catalogue only.** `mochi-emote-catalogue` ships and is
   documented. The developer menu stays private, reachable only through the
   GNOME Shell keybinding.
3. **Windowing: approved.** Force `GDK_BACKEND=x11` on wayland except on
   wlroots compositors or when `MOCHI_NATIVE_WAYLAND=1`.
4. **First slice: approved.** Tasks 1–7 of the plan, excluding Phase 2.

## Purpose

Today the richest AmbiSense behavior (typing reactions, user idle/away,
application and file-browsing context, focused media, and the two global
shortcuts) only works where a GNOME Shell companion extension is installed and
active. Everywhere else Mochi still runs, but it is quieter.

This design reduces that dependency so KDE Plasma, XFCE, MATE and other major
desktops get as much of the same behavior as their desktop APIs allow, without
new runtime dependencies, without network access, and without weakening the
privacy model.

It is explicitly **not** a rewrite of AmbiSense. Each capability keeps its
existing callback and presence logic; we add portable *sources* behind the same
interfaces and let the existing "first backend that starts wins" pattern choose
one.

## Goals

- Provide a portable source for each AmbiSense capability where a standard,
  DE-agnostic API exists.
- Keep GNOME as the richest path and never regress it.
- Add no runtime dependency and no network request.
- Keep the buddy window draggable and positionable on the main Wayland
  desktops, not only GNOME.
- Make the two user-facing/private shortcuts reachable on desktops without a
  GNOME Shell keybinding bridge.
- Keep the privacy boundary: no typed content, title, URL, document name or
  clipboard ever enters Mochi.
- Degrade to the current behavior when no portable source is available.

## Non-goals

- Feature parity with GNOME where no desktop API exists (see
  [Capability matrix](#capability-matrix)).
- Browser *tab* awareness outside GNOME. It needs window titles; opening that
  cross-desktop would break the privacy model. Out of scope.
- A compositor-agnostic "point Mochi at the focused window" feature. Still out
  of scope.
- Writing native extensions for KDE/XFCE/MATE.
- New user-facing toggles. Quiet mode and the existing ambient control keep
  covering opting out.
- Distribution-agnostic automatic dependency install (Fedora stays the only
  auto-install target). Other distros get printed guidance.

## Current GNOME dependency

| Capability | GNOME source | Portable today? |
|---|---|---|
| Typing activity | Shell `Pulse` signal (`typing_activity.py`) | Partly: an AT-SPI backend exists but is **not wired** into the default chain |
| User idle/away | Shell `UserIdle`/`UserActive` (`presence_activity.py`) | No (but logind suspend/lock already portable in `presence/session.py`) |
| App category / focus | Shell `AppCategoryChanged`/`AppFocusChanged` (`presence/signals.py`) | No |
| File browsing | Shell `FileBrowsingStarted/Stopped` (`file_activity.py`) | Downloads watch already portable; focused file-manager detection is not |
| Focused media (YouTube) | Shell focus signals (`media_activity.py`) | MPRIS already works everywhere (`media_activity.py` keeps MPRIS when the helper is absent) |
| Browser tab pulse | Shell `BrowserTabChanged` | No, and intentionally not |
| Battery / network | UPower / NetworkManager | Already portable |
| Suspend / lock / return | logind (`presence/session.py`) | Already portable |
| Light/dark theme | `org.freedesktop.portal.Settings` portal | Already portable (Plasma implements it) |
| Global shortcuts | Shell keybindings → D-Bus signals (`emote_shortcut.py`, `developer_shortcut.py`) | No |
| Window drag/position | X11/XWayland forced on GNOME Wayland (`main.py`) | No on non-GNOME Wayland |

## Design

### 0. A small desktop-capability layer

New GTK-free module `src/mochi/desktop_env.py`:

- `current_desktop()` → normalized id from `XDG_CURRENT_DESKTOP`,
  `XDG_SESSION_DESKTOP`, `DESKTOP_SESSION`: `gnome`, `kde`, `xfce`, `mate`,
  `cinnamon`, `lxqt`, `sway`, `hyprland`, `niri`, `river`, `wayfire`,
  or `unknown`.
- `session_type()` → `wayland`, `x11`, or `tty` from `XDG_SESSION_TYPE`.
- `has_display()` → whether `DISPLAY` is set.
- `uses_wlroots()` → `current_desktop() in _WLROOTS_COMPOSITORS`.

It reads environment only, so it is trivially testable without a display, and
it gives `main.py` and each backend a single place to ask "what desktop is
this?" instead of scattering string checks.

### 1. Typing activity — wire the portable AT-SPI backend

`typing_activity.py` already ships `AtspiDeviceActivityBackend` (AT-SPI
`DeviceA11yManager`, keyboard-monitor capability, payload discarded) and it is
covered by tests, but the default backend chain in `TypingActivityMonitor` is
only:

```text
GnomeShellTypingPulseBackend  →  AtspiTextActivityBackend(allow_text_changed=False)
```

Change the default chain to:

```text
GnomeShellTypingPulseBackend
  → AtspiDeviceActivityBackend        (new in the chain)
  → AtspiTextActivityBackend(allow_text_changed=False)
```

AT-SPI needs the accessibility bus, which Plasma (`kaccess`), XFCE, MATE and
Cinnamon all provide when accessibility is enabled. When it is off, the chain
falls through to the existing caret backend, exactly as on GNOME with an old or
missing extension. This is the single highest-value portability change, and it
is already implemented and tested.

**Privacy:** unchanged. The backend accepts the native `key-pressed` payload as
`*_ignored` and never inspects it.

### 2. User presence — a portable idle backend

Add a portable backend that emits the same `on_user_idle` / `on_user_active`
semantics, using the shared GNOME idle threshold
(`USER_IDLE_AFTER_MS = 120_000`) as the named constant `IDLE_THRESHOLD_SECONDS`.

Backend chain for `PresenceActivityMonitor`:

1. `GnomeShellPresenceBackend` (unchanged, first).
2. `ScreenSaverPresenceBackend` — the cross-desktop
   `org.freedesktop.ScreenSaver` interface. Try `GetSessionIdleTime` on
   `org.freedesktop.ScreenSaver` and fall back to the `org.kde.ScreenSaver` /
   `org.gnome.ScreenSaver` aliases. Implementations vary: some
   screensavers expose idle time, some only `ActiveChanged`. If idle time is
   not exposed, subscribe to `ActiveChanged` and drive the idle/active edges
   from that; if neither is available, `start()` returns `False` and the chain
   continues. Poll on a GLib timer only when the method exists. Privacy: reads
   only an idle flag or a number of idle seconds.
3. `X11ScreenSaverBackend` — on X11 sessions, query the XScreenSaver extension
   (`XScreenSaverQueryInfo`) through the same `ctypes`/libX11 pattern already
   used in `x11.py`, loading `libXss`. Used when the D-Bus screensaver is
   absent or does not expose idle time. Privacy: idle milliseconds only.

Because availability differs per desktop, the exact source selected on each
desktop is confirmed during the maintainer's manual QA and recorded in the
docs, rather than assumed.

This restores "Mochi notices you stepped away" on the main desktops while
logind keeps handling suspend/lock/return as it does today.

### 3. Application awareness — Phase 2, DECLINED (2026-10-24)

The maintainer declined this phase for now: Mochi should not broaden its own
privacy surface by reading application identity in-process. Everything else in
this design ships; app and file-browsing context stays GNOME-only.

The rest of this section is kept as a documented future option, not a plan.

Today the GNOME extension classifies the focused window *inside GNOME Shell* and
sends Mochi one of seven broad categories (`vscode`, `editor`, `terminal`,
`browser`, `media`, `pixel_art`, `unknown`) plus payload-free focus and tab
pulses. `ambisense.md` states the goal is that awareness is "reduced to broad
semantic categories before Mochi reacts".

Proposed portable sources, each producing the same categories through the same
`AppCategorySignalAdapter` interface:

- **X11 sessions (XFCE, MATE, Cinnamon, KDE-X11):** read `_NET_ACTIVE_WINDOW`
  and `WM_CLASS`/`_NET_WM_PID` with the existing `x11.py` helpers, and classify
  with the same marker tables the extension uses. Move those tables into a new
  `src/mochi/presence/app_categories.py` so extension markers, X11
  classification and tests share one source of truth.
- **Wayland non-GNOME (KDE Wayland):** derive a coarse category from AT-SPI
  `window:activate`/`object:state-changed:active` on application frames. App
  identity comes from the accessible application name. Coverage depends on each
  app exposing AT-SPI, so this is best-effort.
- **File browsing:** reuse the same marker table's file-manager entries
  (`dolphin`, `thunar`, `caja`, `nemo`, `nautilus`, `pcmanfm`, …) to emit
  `FileBrowsingStarted/Stopped`. Downloads watching stays as-is.

**Privacy delta to approve:** Mochi would read `WM_CLASS` / accessible app
names inside its own process. This is not one of the forbidden items (typed
content, window titles, document names, clipboard), and it matches what the
GNOME extension already reads before reducing it — but it widens the surface
from "the compositor reduces it" to "Mochi reduces it". Titles, URLs and
content stay out in both cases. This needs an explicit yes/no.

If declined, typing, idle, media, battery, network, downloads, theme, windowing
and shortcuts still land; only app/file context stays GNOME-only.

### 4. Windowing — make the buddy draggable on non-GNOME Wayland

`configure_display_backend()` in `main.py` forces `GDK_BACKEND=x11` only on
GNOME Wayland. Mutter and KWin both lack `wlr-layer-shell`, so on KDE Wayland
Mochi ends up on the compositor-managed GTK path where the X11 helpers in
`windowing.py` return `False` and drag/position/sticky/edge-roam stop working
(see `REGRESSION_WATCHLIST.md`). XFCE and MATE are usually X11 sessions and are
unaffected.

Proposed rule:

```text
force GDK_BACKEND=x11 when
  session_type == wayland
  and DISPLAY is set
  and MOCHI_NATIVE_WAYLAND != "1"
  and not uses_wlroots()
```

i.e. keep native Wayland (and layer-shell) on wlroots compositors where it
already works, and use the proven XWayland path everywhere else. `MOCHI_NATIVE_WAYLAND=1`
stays the escape hatch.

This is a behavior change for any non-wlroots Wayland user currently on the
compositor-managed path; it strictly improves positioning there. It must be
called out in `CHANGELOG.md`.

### 5. Global shortcuts — reachable without a GNOME Shell bridge

The emote catalogue and the developer menu are only reachable through the
GNOME Shell keybindings today. Expose them as application actions on the
running instance and add thin CLI wrappers, mirroring the existing
`mochi-agent-signal` → `agent-event` pattern (which already talks to a
`Gio.SimpleAction` over `org.gtk.Actions`):

- new actions `emote-catalogue` and `developer-menu` in `app.py`;
- the emote action calls `_show_emote_catalogue`, the developer action calls
  `_show_developer_menu`;
- new console scripts `mochi-emote-catalogue` and (optionally, behind
  `--debug`) `mochi-developer-menu`, or a single `mochi` subcommand, added to
  `[project.scripts]`.

Users on Plasma, XFCE, MATE, Cinnamon bind a keyboard shortcut to the command
in their own settings. Documentation lists the per-desktop path.

**Note:** the developer menu is described in code as "private". The default
recommendation is to expose only the emote catalogue as a documented shortcut
and keep the developer menu available but undocumented, or gate it behind
`--debug`. This is a decision to confirm.

### 6. Compatibility matrix (target)

| Capability | GNOME | KDE Plasma | XFCE | MATE | Cinnamon |
|---|---|---|---|---|---|
| Typing reactions | helper | AT-SPI | AT-SPI | AT-SPI | AT-SPI |
| Idle / away | helper | ScreenSaver | ScreenSaver / X11 | ScreenSaver | ScreenSaver |
| App category / file context | helper | AT-SPI (best-effort) / X11 | X11 | X11 | X11 |
| Focused media | helper + MPRIS | MPRIS | MPRIS | MPRIS | MPRIS |
| Browser tab pulse | helper | — | — | — | — |
| Battery / network / suspend | all desktops | ✓ | ✓ | ✓ | ✓ |
| Theme | portal | ✓ | best-effort | best-effort | ✓ |
| Global shortcuts | helper | CLI binding | CLI binding | CLI binding | CLI binding |
| Drag / position (Wayland) | XWayland | XWayland (new) | n/a (X11) | n/a (X11) | XWayland (new) |

## Privacy model changes

- New sources add **no** new class of data: idle seconds, app category, and
  anonymous activity were already observed. The only delta is *where* the
  reduction happens for app identity (Phase 2), which is why that phase is
  gated.
- `docs/ambisense.md` gets a short "Other desktops" subsection naming the
  portable sources and restating that no title/URL/document/clipboard data is
  read.
- The session-bus timing visibility already documented for helper signals also
  applies to any signals a portable source emits; portable sources prefer
  polling where the standard API only offers polling, to avoid emitting extra
  bus traffic.

See [Decisions (2026-10-24)](#decisions-2026-10-24) at the top.

## Verification

- `python3 -m pytest -q` must stay green (baseline: 1 pre-existing
  environmental failure in `tests/test_x11_frame_sync.py`, everything else
  passing).
- New backends are tested without a display by injecting fake Gio/GLib loaders
  and fake `ctypes` handles, following `tests/test_presence_activity.py`,
  `tests/test_typing_activity.py` and the `portal_factory` pattern in
  `color_scheme.py`.
- `desktop_env.py` is tested with monkeypatched environment variables.
- **Manual QA on real desktops cannot be run by the author.** The plan lists
  exact steps for the maintainer on Plasma, XFCE and MATE (idle crossing the
  threshold, typing burst, drag and position persistence, shortcut binding).

## Follow-ups (not in this design)

- Theme fallback from the GTK theme name for desktops without the appearance
  portal.
- A wlroots-native positioning path if `gtk4-layer-shell` becomes reliable
  there.
- Richer idle sources (logind `IdleHint`) if a desktop exposes it reliably.
