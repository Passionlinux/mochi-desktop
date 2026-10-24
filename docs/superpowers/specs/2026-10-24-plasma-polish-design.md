# Plasma Polish — Design

**Date:** 2026-10-24

**Builds on:** `docs/superpowers/specs/2026-10-24-cross-desktop-ambisense-design.md`,
`src/mochi/presence/bubble.py`, `src/mochi/x11.py`, `src/mochi/shortcut_signal.py`

**Status:** approved 2026-10-24. Implementation follows
`docs/superpowers/plans/2026-10-24-plasma-polish.md`.

## Purpose

Mochi runs on KDE Plasma through XWayland (`GDK_BACKEND=x11` is forced in
`src/mochi/main.py`). The maintainer, running Plasma 6 Wayland full time,
reported two Plasma-specific symptoms:

1. The speech bubble occasionally renders as black-and-white vertical stripes
   filling the capsule, with the text drawn over it.
2. Typing reactions never fire in Konsole. This is already documented as a
   Konsole/AT-SPI limitation and is **not** addressed here.

This design fixes the first symptom and removes the redundant work behind it,
without changing toolkit, dependencies, or GNOME behavior.

## Evidence collected (2026-10-24, live Plasma session)

- Session: Plasma Wayland, scale 1, GTK 4.20.4, NVIDIA GTX 1050 Ti with the
  proprietary driver 580.178.04.
- The environment sets `GSK_RENDERER=gl` from
  `~/.config/environment.d/intel-gtk-fix.conf`, a stale *Intel* workaround on
  an NVIDIA machine. Recorded here as an environment note; not an application
  bug, and Mochi does not change it.
- The bubble is a separate transparent X11 toplevel. `_follow_x11` calls
  `_position_x11()` every 22 ms while visible, and `move_window()` issues
  `XMoveWindow` + `XFlush` on **every** call, even when the coordinates are
  unchanged. It also opens and closes a fresh X display connection each time.
- Ordinary speech (`presence/engine.py`: `typing_preview = type == "speech"
  and priority < 40`) animates `Mochi is typing` → `.` → `..` → `...` → final
  text, so the toplevel **resizes while visible**, several times per bubble.

### Upstream context

- **KWin #475642** (CONFIRMED): transparent XWayland windows show stale,
  overlapping frames on Plasma; the compositor behaves as if the window were
  opaque.
- **GTK MR !5857**: after a `ConfigureNotify`, X11 expose events can arrive
  before the surface is resized and become no-ops, "which might lead to
  unrendered portions of the window shadow".

Mochi combines both conditions: a transparent XWayland toplevel that resizes
while visible and is repositioned continuously.

## Goals

- Remove the striped-bubble artifact on Plasma.
- Stop the redundant 45 Hz window movement and connection churn.
- Keep GTK4/PyGObject, with `dependencies = []` in `pyproject.toml`.
- Record what Plasma integration is *not* achievable cleanly, so it is not
  attempted twice.

## Non-goals

- A Qt/Plasma rewrite. That is a separate project (working name "Kochi") and a
  different codebase decision.
- Konsole typing detection. It requires a KWin effect plugin (compiled, ABI
  coupled) or reading input devices; both are out of scope and the latter
  violates the privacy model.
- Visual redesign of the bubble. The capsule CSS stays as it is.
- Reading typed content, keystrokes, window titles, or file names.

## Design

### 1. Position dedupe

Move the decision out of the GTK class so it is testable without a display. A
new GTK-free module `src/mochi/presence/bubble_position.py` exposes:

```python
def should_move(
    applied: tuple[int, int] | None,
    target: tuple[int, int],
    *,
    force: bool,
) -> bool: ...
```

`SpeechBubble` keeps `_applied_position`, set after a successful
`move_window()`. `_position_x11()` computes the target as it does today and
calls `move_window()` only when `should_move()` returns true.

Because a window manager may move the window behind our back, the cache cannot
be trusted indefinitely. Mochi re-applies the position unconditionally on:

- the bubble's `map` signal (already handled),
- every text or size change (already repositioned),
- one forced resync every `RESYNC_INTERVAL_MS = 500`, tracked by a counter on
  the existing follow tick.

That takes the steady state from ~45 moves/second to at most 2, with identical
visible behavior.

### 2. Full invalidation after a content change

After the text changes while the bubble is visible, ask GTK to redraw the whole
window once the allocation settles, instead of relying on partial expose
regions:

```python
def _invalidate_surface(self) -> None:
    self._window.queue_resize()
    self._window.queue_draw()
```

Called from `_set_text()` (visible case), `_reposition_after_text_change()`,
and `_on_window_map()`, at idle and again on the existing 24 ms pass. This is
the application-side equivalent of the GTK MR above: repaint the entire
transparent surface after a resize rather than the newly exposed rectangle.

### 3. Plasma integration: what is clean, and what is not

Probed on the live session, so this does not get retried later:

- **Colour scheme — already works.** `src/mochi/color_scheme.py` reads
  `org.freedesktop.appearance color-scheme` through the XDG portal, which
  Plasma implements. No change.
- **Global shortcut — no clean declarative path.** `org.kde.kglobalaccel` is
  present and exposes `doRegister`, `setShortcutKeys`, `setForeignShortcutKeys`
  and `invokeShortcut`. `setForeignShortcutKeys` is meant for components that
  own an exported object and receive `invokeShortcut`; it is not a way to bind
  an external command. Plasma's "Custom Shortcuts" live in KDE's own
  configuration files, and writing into a user's KDE configuration from an app
  is not acceptable. Decision: **no KGlobalAccel integration** in this batch.

`mochi-emote-catalogue` stays the supported route, with the documented manual
binding per desktop.

## Testing

- `should_move()` is pure and covers: first move, unchanged target skipped,
  changed target applied, forced resync, reset after hide.
- Surface invalidation has no unit test; it is verified by inspection and by
  the maintainer's manual QA. The design keeps it in one helper so the cost of
  being wrong is small.
- Baseline before this work: `1 failed, 1427 passed, 5 skipped` on `main`
  (`test_x11_frame_sync.py::test_disable_frame_sync_needs_a_realized_x11_window`
  needs a realized X11 window and fails in a headless run).

## Risks

- **GNOME is affected too.** Windows on GNOME also use the X11 mode, so the
  dedupe changes GNOME behavior as well. It must be QA'd there, not only on
  Plasma. The visible result is intended to be identical.
- **Stale cache.** If the window manager relocates the bubble, the cache would
  keep it in the wrong place; the 500 ms forced resync and the `map` reset bound
  the damage to half a second.
- **Repaint cost.** One extra full redraw per text change on a small window;
  negligible.

## Manual QA (maintainer)

1. Plasma, Mochi Lab → "Preview typing phrase", ten times: no stripes, text
   legible, no flicker.
2. Plasma, drag Mochi quickly: the bubble follows without lag or drift.
3. Plasma, leave a bubble to expire: it fades out in place.
4. GNOME: a bubble still fades in, follows, and fades out; no double redraw
   visible.
5. XFCE: unchanged.
