# Plasma Polish Implementation Plan

> **For agentic workers:** follow `AGENTS.md`. One task = one feature = one
> reviewable diff. Test-first. Stop for review after each task. Steps use
> checkbox (`- [ ]`) syntax.

**Goal:** Stop the transparent speech bubble from occasionally rendering as
black-and-white stripes on KDE Plasma, and remove the redundant 45 Hz X11
window movement behind it, without changing toolkit, dependencies, or GNOME
behavior.

**Architecture:** No new backend and no new component. The position decision
moves into a GTK-free helper so it can be tested; `SpeechBubble` caches the
position it applied and skips redundant `XMoveWindow` calls, with a periodic
forced resync. A small invalidation helper repaints the whole transparent
surface after each content change, which is the application-side counterpart of
the GTK fix for unrepainted shadow regions.

**Tech Stack:** Python 3.11+, GTK4/PyGObject, GLib, X11 via the existing
`ctypes`/libX11 helpers, pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-plasma-polish-design.md`

## Global Constraints

- No new runtime dependency. `pyproject.toml` keeps `dependencies = []`.
- No network request, no telemetry.
- Never read typed content, window titles, document names or clipboard.
- GNOME behavior must not regress. The X11 path is shared with GNOME, so the
  change is visible there too: identical result, less work.
- Keep logic GTK-free and injectable so it is testable without a display.
- Every GLib source keeps one owner and is torn down on hide/shutdown.
- **Test command:** `python3 -m pytest -q`
- **Baseline on `main` @ `6cbb770`:** `1 failed, 1427 passed, 5 skipped`. The
  failure is `tests/test_x11_frame_sync.py::test_disable_frame_sync_needs_a_realized_x11_window`,
  which needs a realized X11 window and cannot pass headless.

---

## Task 1: GTK-free position decision

**Files:**
- Create: `src/mochi/presence/bubble_position.py`
- Create: `tests/test_bubble_position.py`

**Interfaces:**
- Produces: `should_move(applied: tuple[int, int] | None, target: tuple[int, int], *, force: bool) -> bool`

- [ ] Write `tests/test_bubble_position.py` first, covering: first move with no
      applied position returns `True`; identical target returns `False`; changed
      target returns `True`; `force=True` always returns `True`; a reset applied
      value (`None`) returns `True` again.
- [ ] Run `python3 -m pytest -q tests/test_bubble_position.py` and confirm it
      fails for the right reason.
- [ ] Create `src/mochi/presence/bubble_position.py` with the docstring, a
      `RESYNC_INTERVAL_MS = 500` constant, the `should_move` function, and a
      `FollowTicker` helper or a documented counter contract for the forced
      resync (whichever keeps `SpeechBubble` simplest).
- [ ] Re-run the test file and confirm green.

**Verification:** the new tests pass and the module imports without GTK.

---

## Task 2: Wire the dedupe into the speech bubble

**Files:**
- Modify: `src/mochi/presence/bubble.py`

**Interfaces:**
- Consumes: `should_move()` from Task 1.
- Produces: no new public API; `_position_x11()` keeps its signature.

- [ ] Add `self._applied_position: tuple[int, int] | None = None` and a resync
      counter to `__init__`.
- [ ] In `_finish_hide()` and `_on_window_map()`, reset
      `_applied_position = None` so a remapped window is positioned again.
- [ ] In `_position_x11()`, replace the unconditional `move_window()` call with
      `should_move(...)`, setting `_applied_position` only when the move
      reports success.
- [ ] On the follow tick, force a resync every `RESYNC_INTERVAL_MS` so a window
      moved by the compositor is corrected within half a second.
- [ ] Run `python3 -m pytest -q` and compare with the baseline.

**Verification:** full suite at baseline; `mochi --debug` shows no new warnings
when a bubble is displayed.

---

## Task 3: Repaint the whole surface after a content change

**Files:**
- Modify: `src/mochi/presence/bubble.py`

- [ ] Add `_invalidate_surface()` calling `queue_resize()` and `queue_draw()`
      on the bubble window, with a comment naming the GTK expose-after-resize
      behavior it works around.
- [ ] Call it from `_set_text()` when visible, from
      `_reposition_after_text_change()` on both the idle and 24 ms passes, and
      from `_on_window_map()`.
- [ ] Run `python3 -m pytest -q` and compare with the baseline.

**Verification:** full suite at baseline; manual QA below.

---

## Task 4: Documentation

**Files:**
- Modify: `CHANGELOG.md` (Unreleased → Fixed)
- Modify: `REGRESSION_WATCHLIST.md` (Nameplate / Speech Surface)

- [ ] Add a `Fixed` entry describing the striping fix in user terms: the bubble
      no longer leaves unrepainted regions on transparent XWayland windows.
- [ ] Add QA checks to the speech surface section: repeated typing-preview
      bubbles stay legible; the bubble is not repositioned when Mochi rests.
- [ ] Note in the spec-side documentation that KGlobalAccel integration was
      probed and declined.

**Verification:** documentation renders and the claims match the code.

---

## Task 5: Hand off for manual QA

- [ ] Report the test command and its exact output summary.
- [ ] List the unpublished manual QA steps: ten typing-preview bubbles on
      Plasma, a fast drag, and one bubble per desktop on GNOME and XFCE.
- [ ] Do not claim desktop QA passed.

---

## Follow-ups noticed but out of scope

- `move_window()` opens and closes an X display connection on every call. With
  the dedupe it now runs at most twice a second, but a single owned connection
  would still be cleaner (Manual rule 4 applies once it becomes long-lived).
- `~/.config/environment.d/intel-gtk-fix.conf` forces `GSK_RENDERER=gl` on an
  NVIDIA machine. If visual artifacts persist after Task 3, testing
  `GSK_RENDERER=vulkan` / `cairo` is the next step, and it is an environment
  question rather than an application change.
