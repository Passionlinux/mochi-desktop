# Mochi — local Portage overlay

A small, self-contained [Portage overlay](https://wiki.gentoo.org/wiki/Overlay)
that installs Mochi system-wide from the package manager instead of the
`install.sh` script. Nothing here changes Mochi's runtime behaviour: it is the
same source tree, built as a normal Python package.

## Layout

```
gentoo/
├── metadata/layout.conf                  # masters = gentoo, thin-manifests
├── profiles/repo_name                    # mochi-desktop
├── profiles/categories                   # x11-misc
└── x11-misc/mochi-desktop/
    ├── mochi-desktop-0.4.1-r1.ebuild     # pinned commit, immutable tarball
    ├── mochi-desktop-9999.ebuild         # live, tracks the fork's main branch
    ├── Manifest
    ├── metadata.xml
    └── files/
        └── mochi-desktop-disable-self-update.patch
```

## Use it

The directory is a normal Portage repository. Pick whichever fits your setup.

### A. Register it as a repository

```sh
sudo mkdir -p /etc/portage/repos.conf
sudo tee /etc/portage/repos.conf/mochi.conf >/dev/null <<'EOF'
[mochi]
location = /home/sebastien/Projets/IA/mochi/gentoo
EOF

sudo emerge -av x11-misc/mochi-desktop
```

`sync-type` is intentionally omitted: this is a local, unsynced overlay.

### B. Drop the package into an overlay you already have

```sh
cp -r /home/sebastien/Projets/IA/mochi/gentoo/x11-misc/mochi-desktop \
      /var/db/repos/<your-overlay>/x11-misc/

sudo emerge -av x11-misc/mochi-desktop
```

Then uninstall the `install.sh` copy first if you had one (`./uninstall.sh`),
otherwise two Mochi launchers (`/usr/bin/mochi` and `~/.local/bin/mochi`)
compete for the same command name.

## Versions

| ebuild | source | rebuilds when |
| --- | --- | --- |
| `0.4.1-r1` | `github.com/Passionlinux/mochi-desktop/archive/<commit>.tar.gz` | you bump `MY_COMMIT` and refresh `Manifest` |
| `9999` | `github.com/Passionlinux/mochi-desktop.git#main`, or `MOCHI_GIT_REPO` for a local checkout | always (live) |

`0.4.1-r1` is pinned to commit `8e7459713539cbd6520a39db325b74aa1afd8b3e` (the
commit that carries the cross-desktop work) rather than the upstream `v0.4.1`
tag, so it builds exactly the code in this repository. Revision `-r1` adds
`x11-libs/libXScrnSaver`: `mochi/x11_idle.py` loads `libXss` through ctypes, and
`libX11` does not provide it, so X11 sessions without it lose idle detection
silently. Bumping it:

```sh
# edit MY_COMMIT in mochi-desktop-0.4.1-r1.ebuild, then
cd gentoo/x11-misc/mochi-desktop
ebuild mochi-desktop-0.4.1-r1.ebuild manifest   # or: pkgdev manifest x11-misc/mochi-desktop
```

## Testing local changes with emerge

The live ebuild can build your checkout directly, so local iteration needs no
push and no new pin. `9999` carries `KEYWORDS=""`; unmask it once:

```sh
echo "=x11-misc/mochi-desktop-9999 **" | sudo tee /etc/portage/package.accept_keywords/mochi
```

Then point the build at your tree, permanently, with a package env file:

```sh
sudo tee /etc/portage/env/x11-misc/mochi-desktop >/dev/null <<'EOF'
MOCHI_GIT_REPO="file:///home/sebastien/Projets/IA/mochi"
EOF
```

Rebuild whenever you want to try the current `HEAD`:

```sh
sudo emerge -av --oneshot =x11-misc/mochi-desktop-9999
```

`MOCHI_GIT_REPO` takes a URI (`file://` plus an absolute path). It builds only
**committed** work, so commit before emerging. Setting `EGIT_REPO_URI` in the
environment does *not* work: the ebuild assigns that variable itself, and the
assignment wins — which is why the ebuild reads `MOCHI_GIT_REPO` instead.

Without touching `/etc`, the same thing for a single build:

```sh
MOCHI_GIT_REPO="file:///home/sebastien/Projets/IA/mochi" \
    ebuild mochi-desktop-9999.ebuild clean install
```

Two gotchas, both hit while testing this:

* git-r3 fetches from the checkout with `--depth 1`, and git refuses to move a
  ref that is a shallow root. If the working copy is a shallow clone
  (`git rev-parse --is-shallow-repository` prints `true`), unpack dies with
  `Referencing refs/heads/main failed (wrong ref?)`. Run `git fetch --unshallow`
  once and it works.
* the checkout needs a `main` branch, because the ebuild sets `EGIT_BRANCH=main`.

Back to the pinned build:

```sh
sudo emerge -av --oneshot =x11-misc/mochi-desktop-0.4.1-r1
```

## USE flags

* `gnome` (off) — install the optional GNOME Shell helper
  (`mochi-typing@miflow13`) and its GSettings schema under `/usr/share`. The
  extension is installed, not enabled; enable it per user with
  `gnome-extensions enable mochi-typing@miflow13`. It declares
  `shell-version: ["50"]`, so it only loads on GNOME Shell 50.
  On KDE Plasma, XFCE, MATE or Cinnamon leave this flag off: Mochi gets typing
  and away reactions from AT-SPI and the screen-saver idle interface instead.
* `self-update` (off) — keep the bundled GitHub self-updater. Off by default
  because Portage owns a system-wide install: with the flag off, the patch in
  `files/` removes the automatic update check, the "Check for updates" menu
  entry and the `mochi-update` command. With `USE=self-update` plus FEATURES=test
  the upstream test suite expects the updater, which is why tests are skipped
  here (`RESTRICT="test"`).

## Runtime dependencies

Pulled in by the ebuild, all from the main tree:

| dependency | why |
| --- | --- |
| `dev-python/pygobject:3`, `dev-python/pycairo` | `gi` bindings and Cairo |
| `gui-libs/gtk:4`, `dev-libs/glib:2` | GTK4 / GLib / Gio |
| `app-accessibility/at-spi2-core:2` | AT-SPI typing monitor off GNOME |
| `x11-base/xwayland`, `x11-libs/libX11` | XWayland window and the X11 pointer/window probes |
| `x11-libs/libXScrnSaver` | `libXss`, the XScreenSaver idle counter used on X11 sessions |
| `gui-libs/gtk4-layer-shell:0` | native Wayland surface on wlroots compositors (optional at runtime) |
| `media-libs/gstreamer:1.0` + base/good plugins | sound cues and the focus ambience loop (falls back to `pw-play`/`paplay`) |
| `gnome-base/gnome-shell:0` | only with `USE=gnome` |

No network access, no telemetry, no new Python dependency: the package still
declares `dependencies = []` and everything comes from the system.

## What the ebuild installs

* `/usr/bin/mochi`, `mochi-agent-signal`, `mochi-emote-catalogue`
  (and `mochi-update` only with `USE=self-update`)
* the `mochi` Python package and `mochi_launcher` in site-packages
* assets under `/usr/share/mochi/` (sprites, audio, manifest)
* `/usr/share/applications/io.github.mochi_desktop.Mochi.desktop`
* `/usr/share/icons/hicolor/256x256/apps/io.github.mochi_desktop.Mochi.png`
* with `USE=gnome`: the extension under
  `/usr/share/gnome-shell/extensions/mochi-typing@miflow13/` and
  `org.gnome.shell.extensions.mochi-activity.gschema.xml`

## Manual QA (run these on a real desktop)

The ebuild compiles and installs cleanly (`pkgcheck scan` is clean and an
`ebuild ... install` run succeeds), but only a desktop session can confirm the
result. On the target machine:

1. `sudo emerge -av x11-misc/mochi-desktop`
2. Launch Mochi from the application grid (not from a shell) and confirm the
   buddy, its saved position, right-click menu and sounds.
3. Confirm the icon renders in the grid (not a generic placeholder).
4. Type in a text field: the typing reaction should still fire on GNOME, and on
   KDE/XFCE/MATE via AT-SPI.
5. Walk away for ~2 minutes: away reaction, then return.
6. Run `mochi-emote-catalogue` from a terminal and bind it to a desktop
   shortcut; the catalogue should open in the running Mochi.
7. Only with `USE=gnome`: `gnome-extensions enable mochi-typing@miflow13`, then
   log out and back in, and re-check step 4.
8. With the default `USE=-self-update`, confirm the right-click menu has no
   "Check for updates" row and that `command -v mochi-update` is empty.

## Notes

* Building currently emits one upstream QA notice:
  `` `project.license` as a TOML table is deprecated `` — a `pyproject.toml`
  nit in Mochi itself, not an ebuild problem.
* `PYTHON_COMPAT` is `python3_{12..15}`; choose the interpreter with the usual
  `PYTHON_SINGLE_TARGET`, e.g. in `/etc/portage/package.use/mochi-desktop`:
  `x11-misc/mochi-desktop python_single_target_python3_14`.
