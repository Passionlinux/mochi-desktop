#!/bin/sh
# Keep the published overlay's copy of mochi-desktop in sync with this tree.
#
#   ./gentoo/push-to-overlay.sh [--dry-run] [overlay-checkout]
#
# The published overlay is
# https://github.com/Passionlinux/passiongnulinux-overlay. Only
# x11-misc/mochi-desktop is mirrored: profiles/, metadata/ and the README differ
# between the two repositories and must not be copied over.
#
# The default overlay checkout can be overridden with MOCHI_OVERLAY_DIR.
set -eu

dry_run=false
overlay=${MOCHI_OVERLAY_DIR:-$HOME/Projets/passionlinux/passiongnulinux-overlay}

for arg in "$@"; do
	case $arg in
	--dry-run) dry_run=true ;;
	-*) echo "unknown option: $arg" >&2; exit 2 ;;
	*) overlay=$arg ;;
	esac
done

here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")
src=$here/x11-misc/mochi-desktop
dst=$overlay/x11-misc/mochi-desktop

if [ ! -d "$overlay/.git" ]; then
	echo "not a git checkout: $overlay" >&2
	echo "clone it first:" >&2
	echo "  git clone git@github.com:Passionlinux/passiongnulinux-overlay.git $overlay" >&2
	exit 1
fi

if [ ! -d "$src" ]; then
	echo "missing source directory: $src" >&2
	exit 1
fi

rm -rf "$dst"
cp -a "$src" "$dst"
git -C "$overlay" add -A -- x11-misc/mochi-desktop

if git -C "$overlay" diff --cached --quiet; then
	echo "overlay already up to date"
	exit 0
fi

git -C "$overlay" diff --cached --stat

commit=$(git -C "$repo" rev-parse --short HEAD)
subject=$(git -C "$repo" log -1 --format=%s)

if $dry_run; then
	echo "would commit and push: x11-misc/mochi-desktop: sync $commit"
	exit 0
fi

git -C "$overlay" commit -q -F - <<EOF
x11-misc/mochi-desktop: sync with mochi $commit

$subject

Mirrored from https://github.com/Passionlinux/mochi-desktop by
gentoo/push-to-overlay.sh.
EOF

git -C "$overlay" push origin HEAD
git -C "$overlay" log --oneline -1
