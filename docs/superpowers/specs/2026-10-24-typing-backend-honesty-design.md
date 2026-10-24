# Typing Backend Honesty — Design

**Date:** 2026-10-24

**Builds on:** `docs/superpowers/specs/2026-10-24-cross-desktop-ambisense-design.md`,
`src/mochi/typing_activity.py`, `src/mochi/helper_connection.py`,
`gentoo/x11-misc/mochi-desktop/`

**Status:** proposed 2026-10-24. Awaiting approval; implementation would follow
`docs/superpowers/plans/2026-10-24-typing-backend-honesty.md`.

## Purpose

On KDE Plasma Wayland, Mochi logs

```
Typing mirror enabled via GNOME Shell typing pulse extension
```

while **no** GNOME Shell is installed and **no** typing reaction ever fires,
anywhere. The log line is wrong, and the real reason typing is silent is hidden
behind three chained causes. This design makes the selection honest and names
the actual blocker, without changing the privacy model, adding a dependency, or
touching the GNOME path.

## Evidence collected (2026-10-24, live Plasma session)

- Session: Plasma Wayland (`XDG_CURRENT_DESKTOP=KDE`,
  `DESKTOP_SESSION=/usr/share/wayland-sessions/plasma.desktop`); no
  `gnome-shell` binary and no `~/.local/share/gnome-shell/extensions/`.
- `busctl --user status io.github.mochi_desktop.Mochi.TypingMonitor` reports no
  owner: nothing can ever emit `Pulse`.
- `HelperConnection.start()` returns `True` as soon as the D-Bus **name watch**
  is installed, owner or not (docstring: "Return whether watching started, even
  if the helper is absent"; locked in by
  `tests/test_typing_activity.py::test_absent_extension_keeps_watching`).
  `GnomeShellTypingPulseBackend.start()` therefore "wins" the first slot on any
  desktop.
- Installed `app-accessibility/at-spi2-core-2.58.8`; `Atspi.DeviceCapability`
  has **no** `KEYBOARD_MONITOR` member (`getattr(...) is None`). The code
  documents that capability as available since AT-SPI **2.60**, so
  `AtspiDeviceActivityBackend._enable_keyboard_monitor()` returns `False` and
  the backend refuses to start — by design ("fail cleanly").
- `gsettings get org.gnome.desktop.interface toolkit-accessibility` → `false`,
  so the last fallback (`AtspiTextActivityBackend(allow_text_changed=False)`,
  caret events only) receives nothing.
- Net effect: zero typing events. MPRIS music reactions still work, which is
  why the buddy feels half alive.

The Gentoo tree already carries `at-spi2-core-2.60.7`, but only `~amd64`.

## Goals

- Never say a backend is "enabled" when it cannot deliver events.
- Always report the backend that is *actually armed* for this session.
- Explain once, in plain language, when the AT-SPI keyboard monitor is missing
  because `at-spi2-core < 2.60`, and name the fix.
- Keep GNOME byte-for-byte behavior: same backend order, same signals, same
  tests.
- Keep the privacy boundary: new log lines contain only backend names, an
  AT-SPI version requirement, and booleans.
- Package the requirement honestly: document it, and have the ebuild say it out
  loud when the installed `at-spi2-core` is too old — without forcing a
  keyword change on stable users.

## Non-goals

- Lowering the burst threshold (`5` events in `1.25 s`, span `>= 0.30 s`). That
  is a separate behavior decision with its own QA.
- Konsole/Qt typing coverage. Already documented as an AT-SPI limitation.
- A hard `>=app-accessibility/at-spi2-core-2.60` dependency. 2.60 is
  `~amd64`; forcing it would break stable keyword users, and the ebuild does
  not get to force keyword changes.
- Upstream AT-SPI work, or shipping our own keyboard monitor.
- New user-facing settings or toggles.
- Changing when typing XP is awarded.

## Current behavior

`TypingActivityMonitor.start()` walks a fixed chain and stops at the first
backend whose `start()` returns `True`:

| Order | Backend | `start()` returns `True` when |
|---|---|---|
| 1 | `GnomeShellTypingPulseBackend` | the **name watch** is installed (helper present or not) |
| 2 | `AtspiDeviceActivityBackend` | `DeviceA11yManager.try_new()` works **and** `KEYBOARD_MONITOR` is granted |
| 3 | `AtspiTextActivityBackend(allow_text_changed=False)` | the caret listener registers |

When backend 1 wins, the monitor arms backends 2–3 as *fallbacks* and feeds
their events through `_record_fallback_activity()`, which ignores them only
while `self._backend.active` (i.e. while a helper actually owns the name). So
the fallback path is functionally correct — the diagnosis is simply invisible,
and on this system the fallback is the caret-only backend, which sees nothing
because accessibility exposure is off.

## Design decisions

### D1 — Separate "watching" from "delivering"

`GnomeShellTypingPulseBackend` keeps returning `True` from `start()` when the
helper is absent. That is deliberate: Mochi must pick the helper up if the user
enables the extension later in the session, and GNOME startup ordering is not
guaranteed.

What changes is the **claim**. The backend exposes its own presence:

```python
@property
def helper_present(self) -> bool:      # True only when a helper owns the name
    return self._helper is not None and self._helper.active
```

and `TypingActivityMonitor` logs based on `helper_present`, not on "the watch
started".

### D2 — Report the armed fallback

`TypingActivityMonitor` remembers which fallback actually armed and logs it.
Four cases, one INFO line each, emitted once per `start()`:

| Situation | Log line |
|---|---|
| helper present | `Typing mirror enabled via GNOME Shell typing pulse extension (anonymous activity timing only; key content is discarded)` — unchanged |
| helper absent, AT-SPI device armed | `Typing mirror: GNOME helper absent; using AT-SPI DeviceA11yManager keyboard activity` |
| helper absent, only caret armed | `Typing mirror: GNOME helper absent; using AT-SPI caret activity only (limited coverage)` |
| nothing armed | `Typing mirror unavailable: no safe AT-SPI typing activity backend` — unchanged |

If the helper appears later, the existing `_appeared` path takes over and the
fallback events are ignored again; no new switching logic is added.

### D3 — Name the AT-SPI version blocker once

`AtspiDeviceActivityBackend._enable_keyboard_monitor()` already returns a
`last_error`. When `DeviceCapability.KEYBOARD_MONITOR` is missing, that error
becomes explicit:

```
AT-SPI keyboard monitor needs at-spi2-core >= 2.60
```

and the monitor emits one INFO hint when the caret backend is the only thing
armed:

```
Typing mirror: AT-SPI keyboard monitor needs at-spi2-core >= 2.60; caret
activity only until it is available
```

The hint is emitted once per process, mirroring `_unavailable_logged`. It is
informational: Mochi never installs or upgrades packages, and never touches
`toolkit-accessibility`.

### D4 — Keep the chain order

GNOME stays first. Reordering to "desktop-aware" selection was considered and
rejected: it would need `desktop_env` knowledge in a privacy-sensitive module,
would still need the watch for a mid-session extension enable, and would change
GNOME ordering for no functional gain. The chain order was never the bug; the
reporting was.

### D5 — Packaging says the requirement, without forcing it

- `gentoo/x11-misc/mochi-desktop/mochi-desktop-0.4.1-r2.ebuild` adds a
  `pkg_postinst` check:

  ```sh
  if ! use gnome && ! has_version '>=app-accessibility/at-spi2-core-2.60'; then
      elog "Typing reactions off GNOME use the AT-SPI keyboard monitor, which"
      elog "needs app-accessibility/at-spi2-core >= 2.60 (currently ~amd64)."
  fi
  ```

  No `RDEPEND` bump: stable users keep a working install, they just get an
  honest notice.
- `gentoo/README.md` and `README.md` document the same requirement in the
  non-GNOME compatibility notes.
- The revbump is mirrored to
  `github.com/Passionlinux/passiongnulinux-overlay` with
  `gentoo/push-to-overlay.sh`, per `AGENTS.md`.

### D6 — No new module, no new dependency

All changes stay inside `typing_activity.py`, `helper_connection.py` (tests
only), the ebuild and docs. `pyproject.toml` keeps `dependencies = []`.

## Privacy model changes

None. The added strings are backend names, a version requirement, and
booleans. No key symbol, keycode, text, title, document name, clipboard, or
application identity is read, logged, or transported. The existing
`Pulse`/caret boundary and its comments stay as they are.

## Risks

- **Log volume:** one extra INFO line per `start()`, and one hint per process.
  `start()` runs once per Buddy; acceptable.
- **Tests that assert the old line:** `tests/test_typing_activity.py` may
  assert `"Typing mirror enabled via"`; those assertions move to the new
  branches rather than being deleted, so coverage does not shrink.
- **Plasma users may still get no typing** after the fix, because 2.60 remains
  `~amd64`. That is expected and now *explained*; the actual unblock is the
  maintainer's `emerge` (or enabling accessibility for the caret fallback).
- **GNOME regression risk** is limited to the log line, which is unchanged when
  a helper owns the name.

## Verification

- `python3 -m pytest -q` stays at the current baseline: 1 pre-existing
  environmental failure
  (`tests/test_x11_frame_sync.py::test_disable_frame_sync_needs_a_realized_x11_window`),
  1435 passed, 5 skipped, 48 subtests passed on `main` @ `874305b`.
- New tests inject fake Gio/GLib/Atspi objects; no display required.
- **Manual QA cannot be run by the author.** The plan lists exact steps on
  Plasma Wayland (with and without `at-spi2-core-2.60.7`), GNOME, and a GTK
  terminal.

## Follow-ups (not in this design)

- Reconsider the `5`-event / `1.25 s` burst threshold if honest logging shows
  events arriving but sessions not starting.
- Promote a fallback to primary when the GNOME helper appears mid-session
  (functionally already handled; only the log wording would change).
- Revisit a `>=at-spi2-core-2.60` dependency once 2.60 is stable on amd64.
- Konsole/Qt coverage, if Qt ever exposes the keyboard monitor capability.
