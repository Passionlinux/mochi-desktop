# Cross-Desktop AmbiSense Implementation Plan

> **For agentic workers:** follow `AGENTS.md`. One task = one feature = one
> reviewable diff. Test-first. Stop for review after each task. Steps use
> checkbox (`- [ ]`) syntax.

**Goal:** Give KDE Plasma, XFCE, MATE and Cinnamon the AmbiSense behavior they
can support natively, by adding portable *sources* behind the existing
interfaces, wiring the portable typing backend that already exists, making the
buddy window draggable on non-GNOME Wayland, and exposing the shortcuts through
CLI commands any desktop can bind.

**Architecture:** A new GTK-free `desktop_env.py` answers "what desktop is
this?". Each capability keeps its callback and its presence logic and only
gains extra backends, chosen by the existing "first backend that starts wins"
loop. No new runtime dependency, no network, GNOME stays the first backend.

**Tech Stack:** Python 3.11+, GTK4/PyGObject, GLib, D-Bus (Gio), AT-SPI, X11
via the existing `ctypes`/libX11 helpers, pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-cross-desktop-ambisense-design.md`

## Global Constraints

- No new runtime dependency. `pyproject.toml` keeps `dependencies = []`. New
  system libraries are loaded optionally (e.g. `libXss` via `ctypes`) and their
  absence disables only that backend.
- No network request, no telemetry.
- Never read typed content, window titles, document names or clipboard. App
  identity (`WM_CLASS`, AT-SPI application name) is **Phase 2** and stays
  unstarted until the spec's decision 1 is approved.
- GNOME behavior must not regress: every GNOME backend stays first in its
  chain and existing tests stay green.
- Follow Manual rule 4: every new GLib timer, D-Bus subscription or name watch
  has one owner and is torn down in `stop()`/`shutdown`.
- Keep logic GTK-free and injectable (`gio_loader`, `portal_factory`-style
  seams) so it is testable without a display.
- New speech, if any, goes through `PresenceEngine`.
- **Test command:** `python3 -m pytest -q`
- **Baseline on `main` @ `ddde127`:** 1 failed, 1381 passed, 5 skipped. The one
  failure is `tests/test_x11_frame_sync.py::test_disable_frame_sync_needs_a_realized_x11_window`
  and is environmental (passes with `GDK_BACKEND=x11`). It must not become two
  failures.

## File Map

| File | Responsibility | Task |
|---|---|---|
| `src/mochi/desktop_env.py` (new) | Normalized desktop id, session type, wlroots detection | 1 |
| `tests/test_desktop_env.py` (new) | Env parsing tests | 1 |
| `src/mochi/typing_activity.py` | Add `AtspiDeviceActivityBackend` to the default chain | 2 |
| `tests/test_typing_activity.py` | Chain-selection tests | 2 |
| `src/mochi/presence_activity.py` | `ScreenSaverPresenceBackend`, backend chain | 3 |
| `tests/test_presence_activity.py` | Idle-edge tests with a fake timer/clock | 3 |
| `src/mochi/x11_idle.py` (new) | XScreenSaver probe via `ctypes` | 4 |
| `tests/test_presence_activity.py` | `X11ScreenSaverBackend` + probe-helper tests | 4 |
| `src/mochi/main.py` | Extend `configure_display_backend` to non-wlroots Wayland | 5 |
| `tests/test_main.py` | Backend selection matrix | 5 |
| `src/mochi/app.py` | `emote-catalogue` (+ `developer-menu`) actions | 6 |
| `src/mochi/shortcut_signal.py` (new) | CLI wrapper over `org.gtk.Actions` | 6 |
| `pyproject.toml` | New console script(s) | 6 |
| `tests/test_shortcut_signal.py` (new) | Action dispatch + arg parsing | 6 |
| `CHANGELOG.md`, `README.md`, `REGRESSION_WATCHLIST.md`, `docs/ambisense.md`, `install.sh` | Docs, notice text, non-GNOME guidance | 7 |

---

### Task 1: Desktop-capability layer

**Files:**
- Create `src/mochi/desktop_env.py`
- Create `tests/test_desktop_env.py`

**Interfaces:**
- Produces:
  - `current_desktop(environ: Mapping[str, str] | None = None) -> str`
  - `session_type(environ=None) -> str`
  - `has_display(environ=None) -> bool`
  - `uses_wlroots(environ=None) -> bool`
  - `_WLROOTS_COMPOSITORS: frozenset[str]`

- [ ] Write `tests/test_desktop_env.py` first: `XDG_CURRENT_DESKTOP=KDE` →
  `"kde"`; `ubuntu:GNOME` → `"gnome"`; `X-Cinnamon` → `"cinnamon"`;
  `XFCE` → `"xfce"`; `MATE` → `"mate"`; empty env → `"unknown"`; `sway` /
  `Hyprland` → `uses_wlroots()` true; `kde` → false. Case-insensitive, and
  falls back across `XDG_CURRENT_DESKTOP`, `XDG_SESSION_DESKTOP`,
  `DESKTOP_SESSION`.
- [ ] Implement `desktop_env.py` (environment only, no GTK, no side effects).
- [ ] Run `python3 -m pytest -q tests/test_desktop_env.py`.

### Task 2: Wire the portable typing backend

**Files:**
- Modify `src/mochi/typing_activity.py`
- Modify `tests/test_typing_activity.py`

**Interfaces:**
- Consumes: `AtspiDeviceActivityBackend` (already present).
- Produces: default chain
  `(GnomeShellTypingPulseBackend(), AtspiDeviceActivityBackend(), AtspiTextActivityBackend(allow_text_changed=False))`.

- [ ] Add a test asserting the default chain order and that, with the GNOME
  backend failing, `AtspiDeviceActivityBackend` is selected before the caret
  backend.
- [ ] Add `AtspiDeviceActivityBackend()` to the default `_backends` tuple.
  Keep the existing GNOME-helper-lost fallback behavior unchanged.
- [ ] Run `python3 -m pytest -q tests/test_typing_activity.py`.

### Task 3: Portable idle/presence backend

**Files:**
- Modify `src/mochi/presence_activity.py`
- Modify `tests/test_presence_activity.py`

**Interfaces:**
- Consumes: `desktop_env` (optional, for logging only).
- Produces:
  - `IDLE_THRESHOLD_SECONDS = 120.0`
  - `ScreenSaverPresenceBackend` with `start(on_user_idle, on_user_active)`,
    `stop()`, `active`, `last_error`, `name`.
  - `PresenceActivityMonitor` accepts `backends: Iterable | None` and uses
    `(GnomeShellPresenceBackend(), ScreenSaverPresenceBackend(), X11ScreenSaverBackend())`
    by default, first that starts wins.

- [ ] Test with a fake Gio/GLib loader and a fake clock: crossing the threshold
  emits exactly one idle edge, dropping below emits exactly one active edge,
  and re-crossing does not re-emit while already idle.
- [ ] Implement `ScreenSaverPresenceBackend` using
  `org.freedesktop.ScreenSaver.GetSessionIdleTime`, polling on a GLib timer
  owned by the backend, with all subscriptions cancelled in `stop()`.
- [ ] Refactor `PresenceActivityMonitor` to the backend-chain loop, preserving
  the GNOME backend as first and keeping `backend_name` reporting.
- [ ] Run `python3 -m pytest -q tests/test_presence_activity.py`.

### Task 4: X11 idle fallback

**Files:**
- Create `src/mochi/x11_idle.py` (the ctypes probe)
- Modify `src/mochi/presence_activity.py` (`X11ScreenSaverBackend`, next to the
  other backends, so `presence_activity` never imports the `mochi.presence`
  package and no import cycle appears)
- Modify `tests/test_presence_activity.py`

**Interfaces:**
- Produces: `X11ScreenSaverBackend` (same interface as Task 3), plus the pure
  helpers `x11_idle.idle_seconds_from_milliseconds(...)` and the
  `idle_milliseconds()` probe contract, testable without X11.

- [ ] Test the pure threshold/edge helpers directly (no X11 needed).
- [ ] Implement the XScreenSaver probe by loading `libXss`/`libX11` through
  `ctypes`, mirroring `x11.py`. On any failure, `start()` returns `False` and
  `last_error` is set. Only used when the D-Bus screensaver is absent.
- [ ] Run `python3 -m pytest -q tests/test_presence_activity.py`.

### Task 5: Draggable buddy on non-GNOME Wayland

**Files:**
- Modify `src/mochi/main.py`
- Modify `tests/test_main.py` (already covers `configure_display_backend` and
  `MOCHI_NATIVE_WAYLAND`)

**Interfaces:**
- Consumes: `desktop_env.session_type`, `desktop_env.uses_wlroots`, `desktop_env.has_display`.
- Produces: `configure_display_backend` returns `True` for any Wayland session
  with `DISPLAY` set unless `MOCHI_NATIVE_WAYLAND=1` or the compositor is
  wlroots.

- [ ] Add tests for the matrix: GNOME Wayland → force; KDE Wayland → force;
  sway Wayland → do not force; any X11 → do not force; `MOCHI_NATIVE_WAYLAND=1`
  → do not force; Wayland without `DISPLAY` → do not force.
- [ ] Rewrite `configure_display_backend` on top of `desktop_env`.
- [ ] Note the behavior change for `CHANGELOG.md` (done in Task 7).
- [ ] Run `python3 -m pytest -q`.

### Task 6: Shortcuts via CLI commands

**Files:**
- Modify `src/mochi/app.py`
- Create `src/mochi/shortcut_signal.py`
- Modify `pyproject.toml`
- Create `tests/test_shortcut_signal.py`

**Interfaces:**
- Consumes: `Gio.SimpleAction` over `org.gtk.Actions`, the pattern in
  `src/mochi/agent_signal.py`.
- Produces:
  - `app.py`: action `emote-catalogue` wired to `_show_emote_catalogue`.
    (Decision 2: the developer menu stays private and gets no command.)
  - `shortcut_signal.py`: `main(argv)` dispatching the `emote-catalogue`
    action to `io.github.mochi_desktop.Mochi`; exits non-zero quietly if Mochi
    is not running.
  - `pyproject.toml` script `mochi-emote-catalogue`.

- [ ] Test argument parsing and the D-Bus call construction with a fake
  connection (no live Mochi needed).
- [ ] Add the `emote-catalogue` action in `app.py` next to `agent-event`,
  guarded by `not preview_animations`.
- [ ] Add `shortcut_signal.py` and the `mochi-emote-catalogue` console script.
- [ ] Run `python3 -m pytest -q`.

### Task 7: Docs, installer and regression notes

**Files:**
- Modify `CHANGELOG.md`, `README.md`, `REGRESSION_WATCHLIST.md`,
  `docs/ambisense.md`, `install.sh`

- [ ] `CHANGELOG.md` (Unreleased): new portable sources, the XWayland default
  change, and the new shortcut commands.
- [ ] `README.md`: compatibility table (GNOME / Plasma / XFCE / MATE /
  Cinnamon) and the per-desktop shortcut-binding instructions.
- [ ] `docs/ambisense.md`: "Other desktops" subsection naming each portable
  source and restating the privacy boundary.
- [ ] `REGRESSION_WATCHLIST.md`: entries for the presence backend chain, the
  typing chain order, and the display-backend selection.
- [ ] `install.sh`: update the non-GNOME notice so it no longer says
  "reduced contextual awareness"; print the shortcut-binding hint and, on
  Fedora only, note `at-spi2-core` for typing.
- [ ] Run `python3 -m pytest -q` and report the summary.

---

## Phase 2 — Application and file context

**Declined on 2026-10-24.** Mochi will not read application identity in its own
process for now; app and file-browsing context stays GNOME-only. The sketch
kept in the spec documents the option, but no work starts here. To revisit,
first reopen spec decision 1.

## Manual QA (maintainer, cannot be run here)

On Plasma (Wayland), XFCE (X11) and MATE (X11), with `mochi --debug`:

1. Leave the machine untouched past 2 minutes → Mochi shows the idle/away
   reaction; press a key → he becomes active again.
2. Type a short burst in a text editor → the typing mirror starts and stops.
3. Drag Mochi near each screen edge → he stays inside the work area; relaunch →
   he reappears where he was left.
4. Bind a desktop shortcut to `mochi-emote-catalogue` → the catalogue opens.
5. Confirm the `--debug` log names the selected backend for typing, presence and
   windowing on each desktop.

## Risks / notes

- **XWayland default change** is the only user-visible behavior change for
  existing users; wlroots compositors are excluded to avoid regressing
  layer-shell users.
- **AT-SPI coverage** depends on accessibility being enabled; on Plasma this is
  `kaccess`. Docs must say so.
- **`org.freedesktop.ScreenSaver` polling** adds a light timer; it must be torn
  down in `stop()` and must not poll when another backend already owns presence.
- The author cannot run a real Plasma/XFCE/MATE session; only static checks,
  unit tests and the smoke scripts run here.
