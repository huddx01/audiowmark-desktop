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

AUDIOWMARK_VERSION="0.6.5"
ZITA_VERSION="1.11.2"
APP_NAME="Audiowmark Desktop"
OUT_DIR="$REPO_ROOT/dist"
BREW="$(command -v brew || echo /opt/homebrew/bin/brew)"

case "$(uname -m)" in
    arm64)  ARCH="arm64" ;;
    x86_64) ARCH="x86_64" ;;
    *)      ARCH="$(uname -m)" ;;
esac

echo "Building '$APP_NAME' $VERSION for macOS ($ARCH) ..."

# -- 1. Homebrew ---------------------------------------------------------------
if ! command -v brew &>/dev/null; then
    echo "Installing Homebrew ..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
BREW_PREFIX="$($BREW --prefix)"

# -- 2. Dependencies -----------------------------------------------------------
echo "Installing brew dependencies ..."
$BREW install \
    python@3.14 pyqt pyinstaller \
    pkg-config autoconf automake libtool \
    libsndfile fftw libgcrypt mpg123 ffmpeg \
    zstd

# -- 3. Build temp prefix ------------------------------------------------------
BUILD_TMP="$(mktemp -d)"
trap 'rm -rf "$BUILD_TMP"' EXIT
INSTALL_PREFIX="$BUILD_TMP/install"
mkdir -p "$INSTALL_PREFIX"/{lib/pkgconfig,include,bin}

# -- 4. Build zita-resampler from source ---------------------------------------
echo "Fetching zita-resampler $ZITA_VERSION ..."
curl -fsSL \
    "http://kokkinizita.linuxaudio.org/linuxaudio/downloads/zita-resampler-${ZITA_VERSION}.tar.xz" \
    | tar -xJf - -C "$BUILD_TMP"

pushd "$BUILD_TMP/zita-resampler-${ZITA_VERSION}"
# Compile sources directly - the upstream Makefile targets .so (Linux only)
g++ -O2 -fPIC -std=c++14 -c source/*.cc -I source/
ar rcs "$INSTALL_PREFIX/lib/libzita-resampler.a" ./*.o
# Build dylib for runtime linking by audiowmark
g++ -dynamiclib -install_name "@rpath/libzita-resampler.dylib" \
    -o "$INSTALL_PREFIX/lib/libzita-resampler.dylib" \
    ./*.o
mkdir -p "$INSTALL_PREFIX/include/zita-resampler"
cp source/zita-resampler/*.h "$INSTALL_PREFIX/include/zita-resampler/"
popd

# Write a minimal pkg-config file so audiowmark configure finds it
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

# -- 5. Build audiowmark from source -------------------------------------------
echo "Fetching audiowmark $AUDIOWMARK_VERSION ..."
curl -fsSL \
    "https://github.com/swesterfeld/audiowmark/releases/download/${AUDIOWMARK_VERSION}/audiowmark-${AUDIOWMARK_VERSION}.tar.zst" \
    | zstd -d | tar -xf - -C "$BUILD_TMP"

pushd "$BUILD_TMP/audiowmark-${AUDIOWMARK_VERSION}"
PKG_CONFIG_PATH="$INSTALL_PREFIX/lib/pkgconfig:$BREW_PREFIX/lib/pkgconfig" \
    ./configure \
        --prefix="$INSTALL_PREFIX" \
        --disable-dependency-tracking \
        LDFLAGS="-L$INSTALL_PREFIX/lib -Wl,-rpath,$INSTALL_PREFIX/lib" \
        CPPFLAGS="-I$INSTALL_PREFIX/include"
make -j"$(sysctl -n hw.logicalcpu)"
make install
popd

# -- 6. Build .app with PyInstaller --------------------------------------------
echo "Building .app bundle ..."
cd "$REPO_ROOT"

echo "$VERSION" > src/version.txt

QTBASE_PREFIX="$($BREW --prefix qtbase)"
QT_PLUGINS="$QTBASE_PREFIX/share/qt/plugins"
PYINSTALLER="$BREW_PREFIX/bin/pyinstaller"
FFMPEG_BIN="$($BREW --prefix ffmpeg)/bin/ffmpeg"
FFPROBE_BIN="$($BREW --prefix ffmpeg)/bin/ffprobe"

"$PYINSTALLER" \
    --windowed \
    --onedir \
    --name "$APP_NAME" \
    --icon img/AppIcon.icns \
    --add-binary "$QT_PLUGINS/platforms/libqcocoa.dylib:PyQt6/Qt6/plugins/platforms/" \
    --add-binary "$QT_PLUGINS/styles/libqmacstyle.dylib:PyQt6/Qt6/plugins/styles/" \
    --add-binary "$INSTALL_PREFIX/bin/audiowmark:." \
    --add-binary "$INSTALL_PREFIX/lib/libzita-resampler.dylib:." \
    --add-binary "$FFMPEG_BIN:." \
    --add-binary "$FFPROBE_BIN:." \
    --add-data "src/version.txt:." \
    -y \
    src/audiowmark_gui.py

# ── 7. Inject Info.plist ──────────────────────────────────────────────────────
echo "Injecting Info.plist ..."
APP_BUNDLE="$OUT_DIR/$APP_NAME.app"
PLIST="$APP_BUNDLE/Contents/Info.plist"
RESOURCES="$APP_BUNDLE/Contents/Resources"
PLISTBUDDY=/usr/libexec/PlistBuddy

# PyInstaller names the icon icon-windowed.icns; rename to AppIcon.icns
if [ -f "$RESOURCES/icon-windowed.icns" ]; then
    mv "$RESOURCES/icon-windowed.icns" "$RESOURCES/AppIcon.icns"
fi

cp "$SCRIPT_DIR/mac/Info.plist" "$PLIST"
$PLISTBUDDY -c "Set :CFBundleVersion $VERSION"            "$PLIST"
$PLISTBUDDY -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"

# Ad-hoc sign after all bundle modifications so Gatekeeper accepts it
echo "Code-signing bundle ..."
codesign --force --deep --sign - "$APP_BUNDLE"

# ── 8. Build .dmg ─────────────────────────────────────────────────────────────
echo "Building .dmg ..."
DMG_STAGING="$BUILD_TMP/dmg-root"
mkdir -p "$DMG_STAGING"
# ditto preserves APFS compression and extended attributes; cp -r does not
ditto "$APP_BUNDLE" "$DMG_STAGING/$APP_NAME.app"
ln -s /Applications "$DMG_STAGING/Applications"

DMG_FILE="$OUT_DIR/audiowmark-desktop_${VERSION}_macos_${ARCH}.dmg"
hdiutil create \
    -volname "Audiowmark Desktop $VERSION" \
    -srcfolder "$DMG_STAGING" \
    -ov \
    -format UDZO \
    "$DMG_FILE"

echo "Done: $DMG_FILE"
