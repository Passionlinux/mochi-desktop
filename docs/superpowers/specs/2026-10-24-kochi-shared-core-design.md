# Kochi — Shared Core, Two Shells — Design

**Date:** 2026-10-24

**Builds on:** `docs/CODEBASE_MANUAL.md`, `docs/ambisense.md`,
`src/mochi/presence/engine.py`, `gentoo/x11-misc/mochi-desktop/`

**Status:** proposed 2026-10-24. Awaiting approval. Implementation would follow
`docs/superpowers/plans/2026-10-24-kochi-shared-core.md`.

## Purpose

Mochi works on Plasma, but only through portability shims on top of a
GNOME-shaped codebase: GNOME shell signals first, AT-SPI and X11 fallbacks
after, GTK4 underneath, XWayland for the window. A Plasma user gets the pet, not
the integration.

Kochi is a second shell, not a second product. One core owns the behaviour
(state machine, priority ladder, bond/XP, care, config, speech text, animation
timeline); two shells render it: the existing GTK4 shell (`mochi`) and a new
Qt/QML Plasma shell (`kochi`). The pet, its rules, and its assets stay the same;
only the skin, the input sources and the desktop glue differ.

## Decisions to confirm before implementation

1. **Stack for Kochi:** PySide6 + QML (proposed; `dev-python/pyside` 6.12 is in
   the Gentoo tree) or PyQt6. No Kirigami for v0.1: plain QtQuick controls are
   enough, and Kirigami would add a KDE Frameworks dependency for no v0.1 gain.
2. **Repository layout:** monorepo (proposed) — `src/mochi_core/`,
   `src/mochi_sources/`, `src/mochi/`, `src/kochi/` in this repository — versus a
   separate `Passionlinux/kochi-desktop` repository pinned to a released core.
   Monorepo keeps one version, one test run, no cross-repo pinning; a separate
   repo gives Kochi its own identity and release cadence.
3. **v0.1 scope:** buddy window, sprite animation, drag and remembered position,
   speech bubble, music reaction, away/return, emote catalogue. Excluded:
   agent companion, pocket, focus sessions, self-updater, GNOME helper,
   nameplate, bond overlays.
4. **Name:** "Kochi" as the KDE-facing product name (`kochi` binary, WM class
   `io.github.kochi_desktop.Kochi`), with Mochi unchanged. Trademark and
   package-name collision check still to do.

## Current structure (measured 2026-10-24)

- 28 164 lines of Python in `src/`, 104 test files, 1 435 passing tests.
- 22 modules import GTK; 5 of them are the whole widget layer
  (`buddy.py`, `menu_window.py`, `buddy_menu.py`, `app.py`, `windowing.py`).
- ~40 modules are already **GI-free and GTK-free** (`state.py`, `behavior.py`,
  `care.py`, `config.py`, `animation.py`, `desktop_env.py`, `i18n.py`,
  `presence/phrases.py`, `presence/context.py`, `presence/clicks.py`,
  `presence/cooldowns.py`, `drag_motion.py`, `edge_roam.py`, …).
- ~20 modules are **GI-only, no GTK** and are the real portability layer
  (`typing_activity.py`, `presence_activity.py`, `media_activity.py`,
  `music_activity.py`, `file_activity.py`, `presence/signals.py`,
  `helper_connection.py`, `color_scheme.py`, `sound.py`, …).
- Two leaks block a clean split today:
  - `sprites.py` (manifest + **cairo** rendering in one file) is imported by
    `behavior.py`, so pure behaviour code depends on a renderer.
  - `presence/engine.py` (pure decision logic) imports
    `presence/signals.py` for `TypingIntensityTracker`, which is GI-tier.

## Target architecture

```
            ┌──────────────────────────────┐
            │  mochi_core  (pure Python)   │
            │  state · behaviour · priority│
            │  care · bond/XP · config     │
            │  speech text · timeline math │
            │  detector logic · scheduler  │
            │  protocol (injected)         │
            └───────┬──────────────┬───────┘
                    │              │
      ┌─────────────▼───┐    ┌─────▼──────────────┐
      │ mochi_sources   │    │ assets (shared)    │
      │ Gio/GLib, AT-SPI│    │ PNG · manifest     │
      │ X11 ctypes,     │    │ audio              │
      │ MPRIS, UPower,  │    └─────┬──────────────┘
      │ NM, screen saver│          │
      └───────┬─────────┘          │
              │                    │
      ┌───────▼────────┐   ┌───────▼──────────┐
      │ mochi (GTK4)   │   │ kochi (Qt/QML)   │
      │ bubble, menu,  │   │ Plasma-native    │
      │ cairo sprites  │   │ QML sprites      │
      └────────────────┘   └──────────────────┘
```

### Layer rules (enforced by a test, not by convention)

1. `mochi_core` imports **only** the standard library. No `gi`, no `cairo`, no
   Gtk, no PySide6, no `subprocess` audio calls.
2. `mochi_sources` may import `gi`/Gio/GLib/Atspi and `ctypes`, but **never**
   Gtk and never a shell package.
3. `mochi` and `kochi` may import anything below them; nothing below imports a
   shell.
4. All timing in `mochi_core` goes through an injected
   `Scheduler.schedule(delay_ms, callback) -> handle` / `cancel(handle)`
   protocol. GLib backs it in Mochi, `QTimer` in Kochi.
5. All long-lived sources keep the Manual rule 4 property: one owner, torn down
   on shutdown.

A new test (`tests/test_layer_boundaries.py`) walks imports with `ast` and fails
on a violation, so the boundary survives future work.

## How the sources are shared

AT-SPI has no Qt equivalent, and re-implementing D-Bus sources per toolkit
would double the least testable code. Decision: `mochi_sources` stays
PyGObject-based (Gio, GLib, Atspi) and **both** shells depend on PyGObject.

- Mochi already runs a GLib loop.
- Kochi runs a thin `GlibPump` (a `QObject` with a 10 ms `QTimer` calling
  `GLib.MainContext.default().iteration(False)`). This is the only place where
  the two loops meet, and it is testable in isolation.

Rejected alternatives: QtDBus adapters for every source (duplicates ~4 000
lines of tested logic), or a helper process (new IPC surface, new failure
modes).

## Assets

- `assets/` stays shared and unchanged: 454 files, 19 MB, MIT, already loaded
  through `assets/mochi/manifest.json`.
- `mochi_core` owns the manifest model, frame ordering, durations and loop
  rules (the pure part of today's `sprites.py` + `animation.py`).
- Each shell decodes and draws: GdkPixbuf/cairo in Mochi, `QImage`/QML
  `SpriteSequence` in Kochi. No image decoder enters the core.
- Audio stays shell-side (`mochi/sound.py` today): core emits "play this cue",
  the shell decides GStreamer or QtMultimedia.

## Kochi v0.1 behaviour (proposed)

| Capability | v0.1 | Source |
| --- | --- | --- |
| Buddy window, always-on-top, drag | yes | XWayland sticky path (same as Mochi today) |
| Remembered position | yes | core config JSON |
| Idle / sleep / wake | yes | core state machine |
| Speech bubble | yes, simple | core text + priority, QML bubble |
| Typing reaction | yes | AT-SPI (needs `at-spi2-core >= 2.60`), same honest logging as the typing-honesty spec |
| Music reaction | yes | MPRIS |
| Away / return | yes | `org.kde.screensaver` idle |
| Emote catalogue | yes | core catalogue model + QML window |
| Agent companion, pocket, focus sessions, updater, GNOME helper, nameplate, bond overlays | no | — |

## Packaging

- Monorepo keeps one `pyproject.toml`. `dependencies` stays `[]`; Kochi's Qt
  bindings are an optional extra (`[project.optional-dependencies] kochi =
  ["PySide6-Essentials"]`) and a second console script `kochi`.
- Gentoo: the existing ebuild gains `IUSE="qt"`; `USE=qt` pulls
  `dev-python/pyside` and installs the `kochi` entry point. Mochi's install
  path and `dependencies = []` guarantee are untouched.
- If the separate-repository option wins, the split happens at
  `mochi_core`/`mochi_sources` release time and this section is rewritten
  before implementation.

## Privacy model

Unchanged. The core never sees content: sources still reduce to anonymous
events (activity, idle seconds, playback state, broad app category), and the
new shell receives exactly what the old one does. No new network access, no
telemetry, no new persisted data beyond the existing config JSON.

## Risks

- **Second-system risk.** The core extraction is a refactor of live, tested
  code. Mitigation: extract bottom-up, keep every test green, no behaviour
  changes in the extraction commits.
- **Loop coexistence.** GLib inside a Qt process is the main technical risk.
  Mitigation: one isolated `GlibPump`, validated on Plasma before v0.1 is
  called done.
- **Two shells, one maintainer.** Every behaviour change needs two renderers.
  Mitigation: v0.1 scope is deliberately small, and the core owns everything
  that can be owned once.
- **Positioning.** No native layer-shell for Kochi v0.1 (LayerShellQt is not
  packaged in the Gentoo tree); XWayland keeps parity with Mochi.
- **Name.** "Kochi" collides with a city and a fish in search results; a
  trademark/package check remains to be done.
- **Duplicated effort with the typing-honesty fix.** The typing diagnostics
  spec is independent and should land first; Kochi inherits the honest logs.

## Verification

- `python3 -m pytest -q` stays green at the recorded baseline (1 pre-existing
  environmental failure, 1 435 passed, 5 skipped).
- `tests/test_layer_boundaries.py` fails on any core→GI/shell import.
- Core tests run without `gi`, `cairo`, or a display (enforced by a subprocess
  test that blocks those modules).
- **Manual QA cannot be run by the author.** The plan lists the exact steps on
  Plasma Wayland (Kochi) and GNOME (Mochi regression).

## Follow-ups (not in this design)

- QtDBus adapters if PyGObject inside Kochi proves unreliable.
- LayerShellQt packaging for native Wayland surfaces.
- A shared theme/asset abstraction if Kochi ever ships its own art.
- Splitting `mochi_core` into its own distribution and repository if a third
  shell appears.
