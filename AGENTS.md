# AGENTS.md — Mochi

Mochi is a local-first Linux desktop companion (Python 3.11+, GTK4, PyGObject, Cairo).
Primary target: Fedora + GNOME + Wayland. On GNOME Wayland the whole process runs with
GDK_BACKEND=x11 (XWayland), set in src/mochi/main.py. Do not change that.

## Read before changing runtime code
- docs/CODEBASE_MANUAL.md, especially section 2, "The five rules".
- REGRESSION_WATCHLIST.md sections for every area you touch.
- docs/ambisense.md for the privacy model.
- docs/superpowers/specs and docs/superpowers/plans for spec/plan format.

## Product rules (non-negotiable)
- Local only. New features make no network requests and add no telemetry.
- No streaks, decay, penalties, or guilt-based copy.
- Mochi stays easy to ignore: new speech respects speech_enabled, quiet mode, and
  presentation priority.
- Never read typed content, window titles, document names, or clipboard contents unless
  the user explicitly hands them to Mochi.

## Engineering rules
- One task = one feature = one reviewable diff. No drive-by refactors, renames, or reformatting.
- No new runtime dependencies (pyproject has `dependencies = []`; PyGObject comes from the system).
- New speech goes through PresenceEngine (src/mochi/presence/engine.py). New code never
  calls the speech bubble directly. Never pass text that did not originate in Mochi's own
  source code to any `markup=` parameter.
- Every long-lived source (GLib timeout, signal handler, D-Bus subscription, settings watch)
  has one owner and is torn down on shutdown (Manual rule 4).
- Keep logic GTK-free where possible so it is testable without a display. Follow existing
  injection patterns (e.g. `portal_factory` in src/mochi/color_scheme.py, the adapters in
  src/mochi/presence/signals.py).
- Do not touch the updater, src/mochi_launcher.py, or GDK backend selection unless the task says so.

## Workflow for feature tasks
1. Read the relevant code and the docs above.
2. Write a spec (docs/superpowers/specs/YYYY-MM-DD-<slug>-design.md) and a plan
   (docs/superpowers/plans/YYYY-MM-DD-<slug>.md) matching existing files.
3. Stop and wait for approval. Raise disagreements with the task design here, not mid-implementation.
4. After approval: test-first, small commits.
5. Packaging changes under `gentoo/` are published too: after committing, run
   `gentoo/push-to-overlay.sh` so
   github.com/Passionlinux/passiongnulinux-overlay (the copy `emerge` actually
   consumes) stays in step.

## Gentoo overlay mirror (every commit)
`gentoo/x11-misc/mochi-desktop` is the source of truth, mirrored in the maintainer's
public overlay: https://github.com/Passionlinux/passiongnulinux-overlay
(`x11-misc/mochi-desktop`). Whenever a commit or push changes packaging, version,
dependencies, installed files, or the pinned commit:

1. Update `gentoo/x11-misc/mochi-desktop` in this repo (ebuild, `Manifest`,
   `metadata.xml`, `files/`) and verify with `pkgcheck scan --net x11-misc/mochi-desktop`.
2. Copy the same files to a writable clone of the overlay (e.g.
   `~/Projets/IA/passiongnulinux-overlay`, `git@github.com:Passionlinux/...`),
   commit there, and push to `main`. Never leave the overlay behind.
3. The Portage copy under `/var/db/repos/` is root-owned; it only refreshes through
   the maintainer's `sudo emaint sync -r passiongnulinux-overlay`. Report it as a
   manual step instead of claiming it is done.

Runtime-only commits need no overlay change; say so explicitly in the final report.

## Verification
- Run `python3 -m pytest -q` and report the actual output summary.
- You cannot run a GNOME session. Never claim desktop/manual QA passed. List exact manual
  QA steps for the maintainer instead.
- User-facing changes update CHANGELOG.md (Unreleased), README.md if usage or controls
  change, and REGRESSION_WATCHLIST.md.

## Final report
Summary; files changed; tests added; test command and result; what is unverified;
regressions/risks considered; follow-ups noticed but not done.
