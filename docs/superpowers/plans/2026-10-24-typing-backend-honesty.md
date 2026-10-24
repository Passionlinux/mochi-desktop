# Typing Backend Honesty — Implementation Plan

> **For agentic workers:** follow `AGENTS.md`. One task = one feature = one
> reviewable diff. Test-first. Stop for review after each task. Steps use
> checkbox (`- [ ]`) syntax.

**Goal:** Stop Mochi from claiming the GNOME typing helper is enabled when no
helper exists, report the backend that is actually armed, and name the missing
`at-spi2-core >= 2.60` capability instead of going silent. No behavior change on
GNOME, no new dependency, no privacy change.

**Architecture:** Keep the existing "first backend that starts wins" chain.
Separate *watching* (D-Bus name watch, must keep running) from *delivering*
(helper present), make `TypingActivityMonitor` log from the latter, and add one
INFO hint when the AT-SPI keyboard monitor is unavailable because the installed
AT-SPI is older than 2.60. Packaging documents and notices the requirement; it
does not force it.

**Tech Stack:** Python 3.11+, GLib/Gio, AT-SPI via PyGObject, pytest, Portage
ebuild.

**Spec:** `docs/superpowers/specs/2026-10-24-typing-backend-honesty-design.md`

## Global Constraints

- No new runtime dependency. `pyproject.toml` keeps `dependencies = []`.
- No network request, no telemetry.
- Never read typed content, key symbols, keycodes, modifiers, window titles, or
  clipboard. New log lines contain only backend names, a version requirement,
  and booleans.
- GNOME behavior must not regress: the helper stays first, `Pulse` handling is
  untouched, and existing GNOME tests stay green.
- Manual rule 4: the D-Bus name watch keeps its single owner and is still torn
  down in `stop()`.
- Keep the logic GTK-free and injectable: tests use fake Gio/GLib/Atspi objects,
  no display.
- **Test command:** `python3 -m pytest -q`
- **Baseline on `main` @ `874305b`:** 1 failed, 1435 passed, 5 skipped, 48
  subtests passed. The failure is
  `tests/test_x11_frame_sync.py::test_disable_frame_sync_needs_a_realized_x11_window`
  and is environmental (passes with `GDK_BACKEND=x11`). It must not become two
  failures.

## File Map

| File | Responsibility | Task |
|---|---|---|
| `src/mochi/typing_activity.py` | `helper_present`, honest selection logs, AT-SPI version hint | 1–3 |
| `tests/test_typing_activity.py` | Presence, log branches, version-hint tests | 1–3 |
| `CHANGELOG.md` | Unreleased entry | 4 |
| `README.md` | Non-GNOME typing note | 4 |
| `gentoo/README.md` | `at-spi2-core >= 2.60` requirement | 4 |
| `REGRESSION_WATCHLIST.md` | Cross-desktop typing entry | 4 |
| `gentoo/x11-misc/mochi-desktop/mochi-desktop-0.4.1-r2.ebuild` | `pkg_postinst` notice, replaces `-r1` | 4 |
| `gentoo/x11-misc/mochi-desktop/Manifest` | Refreshed for the revbump | 4 |

---

## Task 1 — Expose helper presence on the pulse backend

**Files:**
- Modify `src/mochi/typing_activity.py`
- Test `tests/test_typing_activity.py`

- [x] Add `GnomeShellTypingPulseBackend.helper_present` returning
  `self._helper is not None and self._helper.active`. Document that
  `start()` still succeeds without a helper on purpose (mid-session extension
  enable), so `active` and `helper_present` mean different things.
- [x] Tests (in `GnomeShellTypingPulseBackendTests`, next to
  `test_absent_extension_keeps_watching`):
  - [ ] no owner at start → `start()` is `True`, `helper_present` is `False`;
  - [ ] owner appears through `_appeared` → `helper_present` becomes `True`;
  - [ ] owner vanishes → `helper_present` returns to `False`, `on_lost` fires
    once.
- [x] `python3 -m pytest -q tests/test_typing_activity.py` → green.
- [x] Stop for review.

## Task 2 — Log the backend that is actually armed

**Files:**
- Modify `src/mochi/typing_activity.py` (`TypingActivityMonitor.start`,
  `_log_accessibility_coverage_hint` call site)
- Test `tests/test_typing_activity.py`

- [x] In the `GnomeShellTypingPulseBackend` branch of `start()`, keep the
  existing "enabled via …" INFO line **only when `helper_present`**. Otherwise
  log, once:
  - [ ] fallback armed is `AtspiDeviceActivityBackend`:
    `Typing mirror: GNOME helper absent; using AT-SPI DeviceA11yManager keyboard activity`
  - [ ] fallback armed is `AtspiTextActivityBackend`:
    `Typing mirror: GNOME helper absent; using AT-SPI caret activity only (limited coverage)`
  - [ ] no fallback armed: keep `_log_unavailable_once()` as the only line.
- [x] Keep the existing `(anonymous activity timing only; key content is
  discarded)` suffix on the helper-present line so current user-facing output
  does not change on GNOME.
- [x] Tests with `assertLogs("mochi.typing_activity", level="INFO")` and the
  existing `_FakeBackend` helper:
  - [ ] helper present → line contains `enabled via GNOME Shell typing pulse extension`;
  - [ ] helper absent + device fallback → line contains `GNOME helper absent` and
    the device backend name, and does **not** contain `enabled via`;
  - [ ] helper absent + caret fallback → line contains `caret activity only (limited coverage)`;
  - [ ] nothing armed → `Typing mirror unavailable` still logged exactly once.
- [x] Ensure the fallback name is stored on the monitor (e.g. `_fallback`) and
  cleared in `stop()`, with a test that a second `start()` does not duplicate
  the line.
- [x] `python3 -m pytest -q tests/test_typing_activity.py` → green.
- [x] Stop for review.

## Task 3 — Name the AT-SPI version blocker once

**Files:**
- Modify `src/mochi/typing_activity.py`
  (`AtspiDeviceActivityBackend._enable_keyboard_monitor`,
  `TypingActivityMonitor.start`)
- Test `tests/test_typing_activity.py` (`DeviceCapabilityTests`)

- [x] Change the missing-capability error to
  `AT-SPI keyboard monitor needs at-spi2-core >= 2.60` and update
  `test_missing_capability_api_fails_cleanly` accordingly. Keep
  `keyboard-monitor capability was not enabled` and
  `keyboard-monitor capability API is unavailable` distinct where they are
  still accurate.
- [x] When the caret backend ends up armed *and* the device backend failed with
  that version error, log once per process:
  `Typing mirror: AT-SPI keyboard monitor needs at-spi2-core >= 2.60; caret activity only until it is available`
- [x] Do not log that hint when the device backend armed, or when the failure was
  a refused capability (different cause).
- [x] Tests:
  - [ ] `Atspi` module without `KEYBOARD_MONITOR` → `last_error` names 2.60;
  - [ ] caret fallback + version error → hint logged exactly once across two
    `start()` calls;
  - [ ] device fallback armed → no hint.
- [x] `python3 -m pytest -q tests/test_typing_activity.py` → green.
- [x] Stop for review.

## Task 4 — Docs, changelog, packaging, overlay

**Files:**
- Modify `CHANGELOG.md`, `README.md`, `gentoo/README.md`,
  `REGRESSION_WATCHLIST.md`
- Add `gentoo/x11-misc/mochi-desktop/mochi-desktop-0.4.1-r2.ebuild`, remove
  `mochi-desktop-0.4.1-r1.ebuild`, refresh `Manifest`

- [x] `CHANGELOG.md` (Unreleased → Fixed): the typing log now names the backend
  that is actually active, and off-GNOME typing needs
  `app-accessibility/at-spi2-core >= 2.60`.
- [x] `README.md`: one line in the non-GNOME compatibility notes, same
  requirement, plus the `toolkit-accessibility` note for the caret fallback.
- [x] `gentoo/README.md`: dependency table row for `at-spi2-core` states the
  2.60 requirement and the `~amd64` status.
- [x] `REGRESSION_WATCHLIST.md`, under "Cross-Desktop AmbiSense (non-GNOME)":
  - [ ] `mochi --debug` on Plasma names the armed backend and, when the helper
    is absent, says so instead of claiming the GNOME backend;
  - [ ] `at-spi2-core < 2.60` produces the one-time version hint.
- [x] Copy `-r1` → `-r2`, add:

  ```sh
  pkg_postinst() {
      ...existing body...
      if ! use gnome && ! has_version '>=app-accessibility/at-spi2-core-2.60'; then
          ewarn "Typing reactions off GNOME need app-accessibility/at-spi2-core >= 2.60."
          ewarn "It is ~amd64 in the Gentoo tree; until then only caret activity is used."
      fi
  }
  ```

- [x] Remove `-r1`, regenerate `Manifest`
  (`ebuild mochi-desktop-0.4.1-r2.ebuild manifest`, distfile already in
  `/var/cache/distfiles`), and run
  `pkgcheck scan --net gentoo` → clean.
- [x] Mirror to the published overlay, per `AGENTS.md`:
  `./gentoo/push-to-overlay.sh`, then report the root-owned
  `/var/db/repos` refresh as a manual maintainer step.
- [x] `python3 -m pytest -q` → report the summary; only the known
  environmental failure is allowed.
- [x] Stop for review.

---

## Manual QA (maintainer, cannot be run here)

Run `mochi --debug`, capture the `Typing mirror:` lines, and repeat on each
system.

**Plasma Wayland, `at-spi2-core-2.58.8` (current state):**

1. [ ] Start Mochi with no GNOME helper installed → log says
   `GNOME helper absent; using AT-SPI caret activity only (limited coverage)`
   plus the one-time 2.60 hint. No `enabled via GNOME Shell` line.
2. [ ] `gsettings set org.gnome.desktop.interface toolkit-accessibility true`,
   restart, type in a GTK text field → typing reaction fires.
3. [ ] Type in Konsole → still nothing, and the log does not promise otherwise.

**Plasma Wayland after `emerge =app-accessibility/at-spi2-core-2.60.7`:**

4. [ ] `python3 -c "from gi.repository import Atspi; print(Atspi.DeviceCapability.KEYBOARD_MONITOR)"`
   prints an integer instead of `None`.
5. [ ] Restart → log says
   `GNOME helper absent; using AT-SPI DeviceA11yManager keyboard activity`, and a
   five-key burst in a text editor starts the typing mirror.
6. [ ] Sprint typing still stops after the 2.25 s delay, once.

**GNOME (regression check):**

7. [ ] With the extension enabled, the unchanged
   `enabled via GNOME Shell typing pulse extension (anonymous activity timing
   only; key content is discarded)` line appears, and typing reactions behave as
   before.
8. [ ] Disable the extension while Mochi runs → fallback takes over without a
   restart, and re-enabling it returns to the helper.

**Packaging:**

9. [ ] `emerge -av --oneshot =x11-misc/mochi-desktop-0.4.1-r2` (or `-9999`) →
   the `ewarn` appears on this machine, and the install still succeeds.
10. [ ] On a GNOME machine with `USE=gnome`, no `ewarn` is printed.

## Risks / notes

- **The fix does not make Plasma typing work by itself** on `at-spi2-core <
  2.60`; it makes the reason visible. The unblock is the upgrade (or enabling
  accessibility for the caret fallback).
- **Log assertions are new** in `tests/test_typing_activity.py`; keep them on
  the monitor's logger name (`mochi.typing_activity`) so they do not depend on
  `basicConfig`.
- **The name watch stays armed** when the helper is absent — do not "fix" that
  by returning `False` from `start()`, or a mid-session extension enable stops
  working.
- **Threshold:** 5 events in 1.25 s with a 0.30 s span. If manual QA shows
  events arriving but no session starting, that is a separate decision, not a
  bug in this plan.
