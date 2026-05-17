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

# -- 4. Build zita-resampler from source (static) -----------------------------
BUILD_TMP="$(mktemp -d)"
trap 'rm -rf "$BUILD_TMP"' EXIT

ZITA_VERSION="1.11.2"
INSTALL_PREFIX="$BUILD_TMP/prefix"
mkdir -p "$INSTALL_PREFIX"/{lib/pkgconfig,include,bin}

echo "Fetching zita-resampler $ZITA_VERSION ..."
curl -fsSL \
    "http://kokkinizita.linuxaudio.org/linuxaudio/downloads/zita-resampler-${ZITA_VERSION}.tar.xz" \
    | tar -xJf - -C "$BUILD_TMP"

pushd "$BUILD_TMP/zita-resampler-${ZITA_VERSION}"
g++ -O2 -fPIC -std=c++14 -c source/*.cc -I source/
ar rcs "$INSTALL_PREFIX/lib/libzita-resampler.a" ./*.o
mkdir -p "$INSTALL_PREFIX/include/zita-resampler"
cp source/zita-resampler/*.h "$INSTALL_PREFIX/include/zita-resampler/"
popd

cat > "$INSTALL_PREFIX/lib/pkgconfig/zita-resampler.pc" <<EOF
prefix=$INSTALL_PREFIX
exec_prefix=\${prefix}
libdir=\${prefix}/lib
includedir=\${prefix}/include

Name: zita-resampler
Description: zita-resampler library
Version: $ZITA_VERSION
Libs: -L\${libdir} -lzita-resampler
Cflags: -I\${includedir}
EOF

# -- 5. Build audiowmark from source (links zita-resampler statically) --------
echo "Fetching audiowmark $AUDIOWMARK_VERSION ..."
curl -fsSL "https://github.com/swesterfeld/audiowmark/releases/download/${AUDIOWMARK_VERSION}/audiowmark-${AUDIOWMARK_VERSION}.tar.zst" \
    | tar --use-compress-program=unzstd -xf - -C "$BUILD_TMP"

pushd "$BUILD_TMP/audiowmark-${AUDIOWMARK_VERSION}"
PKG_CONFIG_PATH="$INSTALL_PREFIX/lib/pkgconfig" \
    ./configure --prefix="$INSTALL_PREFIX" --disable-dependency-tracking \
    LDFLAGS="-L$INSTALL_PREFIX/lib" \
    CPPFLAGS="-I$INSTALL_PREFIX/include"
make -j"$(nproc)"
make install
popd

install -m 0755 "$INSTALL_PREFIX/bin/audiowmark" \
    "$STAGING/usr/lib/audiowmark-desktop/audiowmark"

# -- 5. Installed-Size ---------------------------------------------------------
INSTALLED_KB=$(du -sk "$STAGING" | cut -f1)
echo "Installed-Size: $INSTALLED_KB" >> "$STAGING/DEBIAN/control"

# -- 6. Build .deb -------------------------------------------------------------
mkdir -p "$OUT_DIR"
fakeroot dpkg-deb --build "$STAGING" "$OUT_DIR/${PKG_NAME}.deb"

echo "Done: $OUT_DIR/${PKG_NAME}.deb"
