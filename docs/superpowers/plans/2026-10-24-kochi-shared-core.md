# Kochi — Shared Core, Two Shells — Implementation Plan

> **For agentic workers:** follow `AGENTS.md`. One task = one feature = one
> reviewable diff. Test-first. Stop for review after each task. Steps use
> checkbox (`- [ ]`) syntax.

**Goal:** Extract a toolkit-free `mochi_core`, keep the existing GTK4 shell on
top of it unchanged, and add a Qt/QML Plasma shell named Kochi that renders the
same pet with the same rules. No behaviour change for Mochi users.

**Architecture:** Three layers. `mochi_core` (pure Python, no `gi`, no `cairo`,
no shell imports), `mochi_sources` (Gio/GLib/AT-SPI/X11/MPRIS/UPower/NM
adapters, PyGObject only), and two shells (`mochi` GTK4, `kochi` Qt/QML). The
core owns the state machine, priority ladder, care/bond, config, speech text,
animation timeline and a `Scheduler` protocol. Assets stay shared; each shell
decodes and draws.

**Tech Stack:** Python 3.11+, PyGObject (Mochi + sources), PySide6/QML (Kochi),
pytest, Portage.

**Spec:** `docs/superpowers/specs/2026-10-24-kochi-shared-core-design.md`

## Global Constraints

- **No behaviour change during extraction.** P0–P4 move code and imports; they
  do not change states, priorities, delays or copy.
- No new runtime dependency for Mochi: `pyproject.toml` keeps
  `dependencies = []`. PySide6 lives in an optional extra.
- `mochi_core` imports only the standard library. No `gi`, no `cairo`, no Gtk,
  no PySide6, no `mochi`/`kochi` imports. Enforced by a test.
- `mochi_sources` never imports Gtk or a shell.
- Assets in `assets/` are not modified.
- Manual rule 4: every timer, D-Bus subscription and name watch keeps one owner
  and is torn down on shutdown.
- No network, no telemetry, no new persisted data.
- **Test command:** `python3 -m pytest -q`
- **Baseline on `main` @ `874305b`:** 1 failed, 1 435 passed, 5 skipped, 48
  subtests passed. The failure is
  `tests/test_x11_frame_sync.py::test_disable_frame_sync_needs_a_realized_x11_window`
  and is environmental. It must not become two failures.

## File Map

| File / directory | Responsibility | Phase |
|---|---|---|
| `tests/test_layer_boundaries.py` (new) | AST guard: core has no GI/cairo/shell imports | P0 |
| `src/mochi_core/scheduler.py` (new) | `Scheduler` protocol + a fake for tests | P0 |
| `src/mochi_core/state.py`, `behavior.py`, `animation.py`, `care.py`, `config.py`, `i18n.py`, `desktop_env.py`, `phrases.py`, `context.py`, `clicks.py`, `cooldowns.py` | Moved from `src/mochi/` | P1 |
| `src/mochi_core/sprites.py` + `src/mochi/sprite_renderer.py` | Split cairo rendering out of the manifest model | P2 |
| `src/mochi_core/intensity.py` + `src/mochi_sources/signals.py` | Split `TypingIntensityTracker` from the GNOME signal adapter | P3 |
| `src/mochi_sources/` (new package) | Move `typing_activity.py`, `presence_activity.py`, `media_activity.py`, `music_activity.py`, `file_activity.py`, `helper_connection.py`, `color_scheme.py`, `x11_idle.py` | P4 |
| `src/kochi/` (new package) | Qt application, QML, sprite renderer, window, GLib pump | P5 |
| `src/kochi/qml/` | `Main.qml`, `Buddy.qml`, `Bubble.qml`, `EmoteCatalogue.qml` | P5–P6 |
| `tests/test_kochi_*.py` | Offscreen QML tests, skipped without PySide6 | P5–P6 |
| `pyproject.toml`, `gentoo/x11-misc/mochi-desktop/*` | Optional extra, `IUSE=qt`, ebuild | P7 |

---

## Phase 0 — Guardrails

### Task 0.1 — Boundary test

**Files:** `tests/test_layer_boundaries.py` (new), `src/mochi_core/__init__.py`
(new, empty).

- [ ] Create the empty `mochi_core` package.
- [ ] Test walks `src/mochi_core/**/*.py` with `ast` and fails on any import of
  `gi`, `cairo`, `Gtk`, `gi.repository`, `PySide6`, `PyQt6`, `mochi`,
  `mochi_sources`, `kochi`.
- [ ] Test walks `src/mochi_sources/**/*.py` and fails on `Gtk`, `mochi`,
  `kochi`.
- [ ] Test runs a subprocess with `sys.modules["gi"] = None` and
  `sys.modules["cairo"] = None`, then imports every `mochi_core` module.
- [ ] Test fails with a readable message naming the offending file and import.
- [ ] `python3 -m pytest -q tests/test_layer_boundaries.py` → green.
- [ ] Stop for review.

### Task 0.2 — Scheduler protocol

**Files:** `src/mochi_core/scheduler.py` (new),
`tests/test_scheduler_protocol.py` (new).

- [ ] Define `Scheduler` with `schedule(delay_ms, callback) -> object` and
  `cancel(handle)`; document that callbacks run on the shell's main loop.
- [ ] Provide `ManualScheduler` for tests (deterministic, no wall clock).
- [ ] Tests: one-shot fire, cancel before fire, two independent handles.
- [ ] `python3 -m pytest -q tests/test_scheduler_protocol.py` → green.
- [ ] Stop for review.

## Phase 1 — Extract the pure core

Each task: `git mv` the modules, update every import in `src/` and `tests/`,
run the full suite. No logic edits. One commit per task.

### Task 1.1 — State and timeline

- [ ] Move `state.py`, `behavior.py`, `animation.py`, `interaction_tuning.py`.
- [ ] Update imports mechanically; keep `ANIMATIONS` importable from its new
  home for now (P2 splits rendering).
- [ ] `python3 -m pytest -q` → baseline unchanged.
- [ ] Stop for review.

### Task 1.2 — Care, config, environment

- [ ] Move `care.py`, `config.py`, `desktop_env.py`, `mood.py`, `mood_behavior.py`.
- [ ] Confirm `config.py` has no GI import and still writes
  `~/.config/mochi/config.json` (Kochi will read the same file; this is a
  product decision recorded in the spec).
- [ ] `python3 -m pytest -q` → baseline unchanged.
- [ ] Stop for review.

### Task 1.3 — Speech and ambient text

- [ ] Move `i18n.py`, `locale_fr.py`, `presence/phrases.py`,
  `presence/context.py`, `presence/clicks.py`, `presence/cooldowns.py`.
- [ ] `presence/engine.py` keeps working; it may stay in `presence/` for now and
  move in Task 3.1 with its intensity dependency.
- [ ] `python3 -m pytest -q` → baseline unchanged.
- [ ] Stop for review.

## Phase 2 — Break the cairo leak

### Task 2.1 — Split manifest from rendering

**Files:** `src/mochi_core/sprites.py`, `src/mochi/sprite_renderer.py`,
`src/mochi/sprite_loader.py`, `src/mochi/buddy.py`,
`tests/test_sprites*.py`.

- [ ] `mochi_core/sprites.py` keeps the manifest model, frame order, durations
  and loop rules — no `cairo`, no `GdkPixbuf`.
- [ ] `mochi/sprite_renderer.py` keeps the cairo surface drawing and imports
  the core model.
- [ ] `behavior.py` imports the core model only.
- [ ] Tests: existing sprite tests stay green; a new test asserts
  `mochi_core.sprites` imports without cairo.
- [ ] `python3 -m pytest -q` → baseline unchanged.
- [ ] Stop for review.

## Phase 3 — Break the signals leak and move the engine

### Task 3.1 — Pure intensity tracker

**Files:** `src/mochi_core/intensity.py` (new, moved logic),
`src/mochi_sources/signals.py`, `src/mochi_core/engine.py`,
`tests/test_presence_engine.py`, `tests/test_signals.py`.

- [ ] Move `TypingIntensityTracker` into `mochi_core/intensity.py`.
- [ ] Move `presence/engine.py` into `mochi_core/engine.py`; it must import only
  core modules.
- [ ] `mochi_sources/signals.py` keeps the D-Bus/GNOME adapter and feeds a core
  `TypingIntensityTracker` instance.
- [ ] `python3 -m pytest -q` → baseline unchanged.
- [ ] Stop for review.

## Phase 4 — Create the sources package

### Task 4.1 — Move GI-only modules

**Files:** new `src/mochi_sources/`; move `typing_activity.py`,
`typing_activity_atspi_text.py`, `presence_activity.py`, `media_activity.py`,
`music_activity.py`, `file_activity.py`, `helper_connection.py`,
`color_scheme.py`, `x11_idle.py`, `presence/signals.py`.

- [ ] Move modules and update imports (mechanical).
- [ ] `mochi_sources` exports the same class names; no logic edits.
- [ ] `tests/test_layer_boundaries.py` green, full suite at baseline.
- [ ] Stop for review.

### Task 4.2 — Scheduler-backed timers in sources

- [ ] Replace direct `GLib.timeout_add` in `mochi_sources/typing_activity.py` and
  `presence_activity.py` with the injected `Scheduler` (Mochi passes a
  GLib-backed implementation; tests pass `ManualScheduler`).
- [ ] Behaviour identical: same delays, same single owner, same teardown.
- [ ] Tests: existing timing tests keep passing; add a test that `stop()`
  cancels every scheduled handle.
- [ ] `python3 -m pytest -q` → baseline unchanged.
- [ ] Stop for review.

## Phase 5 — Kochi skeleton

### Task 5.1 — Application entry point

**Files:** `src/kochi/__init__.py`, `src/kochi/app.py`,
`src/kochi/qml/Main.qml`, `pyproject.toml` (script + extra),
`tests/test_kochi_app.py`.

- [ ] `kochi = "kochi.app:main"` console script; PySide6 imported lazily so a
  missing Qt never breaks Mochi.
- [ ] `[project.optional-dependencies] kochi = ["PySide6-Essentials"]`.
- [ ] Test with `pytest.importorskip("PySide6")` and
  `QT_QPA_PLATFORM=offscreen`: `main()` builds the QML engine and loads
  `Main.qml`.
- [ ] `python3 -m pytest -q` → baseline unchanged plus the new test (skipped
  when Qt is absent).
- [ ] Stop for review.

### Task 5.2 — Sprite rendering

**Files:** `src/kochi/sprites.py`, `src/kochi/qml/Buddy.qml`,
`tests/test_kochi_sprites.py`.

- [ ] Load frames from `mochi_core.sprites` and the shared `assets/` manifest.
- [ ] Advance frames on `QTimer`, driven by core durations; no image decoding
  in the core.
- [ ] Test: frame sequence for one animation matches the core timeline.
- [ ] Stop for review.

### Task 5.3 — Window, drag, position

**Files:** `src/kochi/window.py`, `tests/test_kochi_window.py`.

- [ ] XWayland sticky/always-on-top path consistent with
  `src/mochi/windowing.py`; position persisted through core `config.py`.
- [ ] Test: position round-trips through config; out-of-bounds positions clamp.
- [ ] Stop for review.

### Task 5.4 — GLib pump

**Files:** `src/kochi/glib_pump.py`, `tests/test_kochi_glib_pump.py`.

- [ ] `QObject` with a 10 ms `QTimer` iterating
  `GLib.MainContext.default().iteration(False)`, start/stop owned by the app.
- [ ] Test: a scheduled GLib timeout fires through the pump; `stop()` leaves no
  timer running.
- [ ] Stop for review.

## Phase 6 — Kochi behaviour

### Task 6.1 — Music and away/return

- [ ] Wire `mochi_sources.media_activity`/`music_activity` and
  `presence_activity` into the Kochi state machine.
- [ ] Tests with fake sources: playback starts the dance state; idle crosses
  the threshold and a key press returns to active.
- [ ] Stop for review.

### Task 6.2 — Typing with honest logs

- [ ] Reuse the typing-honesty spec's logging (`GNOME helper absent; using …`)
  in Kochi, with no GNOME-specific UI.
- [ ] Test: core receives activity only; no payload reaches the shell.
- [ ] Stop for review.

### Task 6.3 — Speech bubble and emote catalogue

- [ ] `qml/Bubble.qml` renders core text/priority; `EmoteCatalogue.qml` lists
  core emotes and dispatches the same action.
- [ ] Tests: priority filtering happens in core, not QML.
- [ ] Stop for review.

## Phase 7 — Packaging and docs

### Task 7.1 — Gentoo

- [ ] Add `IUSE="qt"` + `dev-python/pyside` to `RDEPEND` under `qt?`, install
  the `kochi` entry point, revbump `-r2`.
- [ ] `pkgcheck scan --net gentoo` → clean; `Manifest` refreshed.
- [ ] Mirror with `./gentoo/push-to-overlay.sh`; report the root-owned
  `/var/db/repos` refresh as a manual step.
- [ ] Stop for review.

### Task 7.2 — Docs

- [ ] `CHANGELOG.md` (Unreleased → Added): Kochi shell behind `USE=qt`.
- [ ] `README.md`: what Kochi is, how to launch it, what is not implemented.
- [ ] `REGRESSION_WATCHLIST.md`: dual-shell section (GNOME unchanged, Plasma
  Kochi, layer-boundary test).
- [ ] `python3 -m pytest -q` → report the summary.
- [ ] Stop for review.

---

## Manual QA (maintainer, cannot be run here)

**Plasma Wayland — Kochi:**

1. [ ] `kochi` starts, the buddy appears, stays above other windows and does
   not steal focus.
2. [ ] Drag him near each edge; he stays in the work area; relaunch restores the
   position.
3. [ ] Play music in Elisa or a browser → dance starts and stops with playback.
4. [ ] Leave the machine 2 minutes → away; press a key → return.
5. [ ] Type 5+ keys in a text editor → typing reaction; `kochi --debug` names
   the armed backend honestly.
6. [ ] Right-click menu opens; no GNOME-only entries.
7. [ ] Emote catalogue opens from the menu and from `kochi-emote-catalogue`.

**GNOME — Mochi regression:**

8. [ ] Buddy, typing, away/return, emote catalogue and bubble behave exactly as
   before the extraction.
9. [ ] `mochi --debug` still reports the GNOME helper as the typing backend.

## Risks / notes

- **The extraction is the risky part, not Kochi.** Every phase moves tested
  code; never combine a move with a behaviour change.
- **Qt in CI/headless:** tests use `QT_QPA_PLATFORM=offscreen` and
  `pytest.importorskip`, so `pytest -q` stays green on machines without Qt.
- **GLib inside Qt** is the one unproven integration; Task 5.4 and manual step
  1–5 decide whether v0.1 is viable.
- **Scope discipline:** agent companion, pocket, focus sessions, updater and
  GNOME helper stay out of Kochi v0.1 even though the core may already support
  them later.
- **Typing honesty lands first:** the `2026-10-24-typing-backend-honesty` spec
  is independent and should merge before Phase 6.2 so Kochi inherits it.
