#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Version: from $1, git tag, or fallback
VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    VERSION="$(git -C "$REPO_ROOT" describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')" || true
fi
VERSION="${VERSION:-0.0.0}"

# Arch: dpkg naming
case "$(uname -m)" in
    x86_64)  ARCH="amd64" ;;
    aarch64) ARCH="arm64" ;;
    *)       ARCH="$(uname -m)" ;;
esac

AUDIOWMARK_VERSION="0.6.5"
PKG_NAME="audiowmark-desktop_${VERSION}_${ARCH}"
STAGING="$REPO_ROOT/dist/staging/$PKG_NAME"
OUT_DIR="$REPO_ROOT/dist"

echo "Building $PKG_NAME ..."

# -- 1. Staging structure ------------------------------------------------------
rm -rf "$STAGING"
install -d \
    "$STAGING/DEBIAN" \
    "$STAGING/usr/bin" \
    "$STAGING/usr/lib/audiowmark-desktop" \
    "$STAGING/usr/share/applications" \
    "$STAGING/usr/share/icons/hicolor/16x16/apps" \
    "$STAGING/usr/share/icons/hicolor/32x32/apps" \
    "$STAGING/usr/share/icons/hicolor/48x48/apps" \
    "$STAGING/usr/share/icons/hicolor/64x64/apps" \
    "$STAGING/usr/share/icons/hicolor/128x128/apps" \
    "$STAGING/usr/share/icons/hicolor/256x256/apps" \
    "$STAGING/usr/share/icons/hicolor/512x512/apps"

# -- 2. DEBIAN control ---------------------------------------------------------
sed "s/@VERSION@/$VERSION/g; s/@ARCH@/$ARCH/g" \
    "$SCRIPT_DIR/DEBIAN/control.in" > "$STAGING/DEBIAN/control"

install -m 0755 "$SCRIPT_DIR/DEBIAN/postinst" "$STAGING/DEBIAN/postinst"
install -d "$STAGING/usr/share/doc/audiowmark-desktop"
install -m 0644 "$SCRIPT_DIR/DEBIAN/copyright" "$STAGING/usr/share/doc/audiowmark-desktop/copyright"

# -- 3. App files --------------------------------------------------------------
install -m 0755 "$SCRIPT_DIR/launcher.sh"        "$STAGING/usr/bin/audiowmark-desktop"
install -m 0644 "$REPO_ROOT/src/audiowmark_gui.py" "$STAGING/usr/lib/audiowmark-desktop/audiowmark_gui.py"
echo "$VERSION" > "$STAGING/usr/lib/audiowmark-desktop/version.txt"
install -m 0644 "$SCRIPT_DIR/audiowmark-desktop.desktop" "$STAGING/usr/share/applications/audiowmark-desktop.desktop"

for SIZE in 16 32 48 64 128 256 512; do
    if [ -f "$REPO_ROOT/img/icon_${SIZE}.png" ]; then
        install -m 0644 "$REPO_ROOT/img/icon_${SIZE}.png" \
            "$STAGING/usr/share/icons/hicolor/${SIZE}x${SIZE}/apps/audiowmark-desktop.png"
    fi
done

# -- 4. Build audiowmark from source ------------------------------------------
BUILD_TMP="$(mktemp -d)"
trap 'rm -rf "$BUILD_TMP"' EXIT

echo "Fetching audiowmark $AUDIOWMARK_VERSION ..."
curl -fsSL "https://github.com/swesterfeld/audiowmark/releases/download/${AUDIOWMARK_VERSION}/audiowmark-${AUDIOWMARK_VERSION}.tar.zst" \
    | tar --use-compress-program=unzstd -xf - -C "$BUILD_TMP"

pushd "$BUILD_TMP/audiowmark-${AUDIOWMARK_VERSION}"
./configure --prefix="$BUILD_TMP/install" --disable-dependency-tracking
make -j"$(nproc)"
make install
popd

install -m 0755 "$BUILD_TMP/install/bin/audiowmark" \
    "$STAGING/usr/lib/audiowmark-desktop/audiowmark"

# -- 5. Installed-Size ---------------------------------------------------------
INSTALLED_KB=$(du -sk "$STAGING" | cut -f1)
echo "Installed-Size: $INSTALLED_KB" >> "$STAGING/DEBIAN/control"

# -- 6. Build .deb -------------------------------------------------------------
mkdir -p "$OUT_DIR"
fakeroot dpkg-deb --build "$STAGING" "$OUT_DIR/${PKG_NAME}.deb"

echo "Done: $OUT_DIR/${PKG_NAME}.deb"
