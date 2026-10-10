#!/bin/bash
# Build a self-contained (statically linked) ffmpeg + ffprobe for macOS arm64 with x264 and LAME.
# The result is GPL-2.0-or-later (because of libx264). It is shipped as a *separate executable*
# next to AURA REC; see THIRD_PARTY_NOTICES.md for the license text and source offer.
#
# Usage: tools/build_ffmpeg_macos.sh [output_dir]   (default: build/ffmpeg-bin)
set -euo pipefail

FFMPEG_VERSION="7.1.1"
FFMPEG_SHA256="733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1"
LAME_VERSION="3.100"
LAME_SHA256="ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e"
X264_COMMIT="${X264_COMMIT:-b35605ace3ddf7c1a5d67a2eb553f034aef41d55}"   # videolan/x264 stable

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/build/ffmpeg-bin}"
WORK="$ROOT/build/ffmpeg-src"
PREFIX="$ROOT/build/ffmpeg-prefix"
export MACOSX_DEPLOYMENT_TARGET=11.0
# 只用系統與 Homebrew 的工具鏈，避免 conda 等環境的 ld/strip/ar 混入
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
command -v pkg-config >/dev/null || { echo "需要 pkg-config：brew install pkgconf"; exit 1; }
JOBS="$(sysctl -n hw.ncpu)"

mkdir -p "$WORK" "$PREFIX" "$OUT"
cd "$WORK"

fetch() { # url sha256 file
    [ -f "$3" ] || curl -fsSL --retry 3 -o "$3" "$1"
    echo "$2  $3" | shasum -a 256 -c -
}

echo "== LAME $LAME_VERSION"
if [ ! -f "$PREFIX/lib/libmp3lame.a" ]; then
fetch "https://downloads.sourceforge.net/project/lame/lame/$LAME_VERSION/lame-$LAME_VERSION.tar.gz" "$LAME_SHA256" "lame.tar.gz"
rm -rf "lame-$LAME_VERSION" && tar xf lame.tar.gz
( cd "lame-$LAME_VERSION" && ./configure --prefix="$PREFIX" --disable-shared --enable-static --disable-frontend >/dev/null && make -j"$JOBS" >/dev/null && make install >/dev/null )
fi

echo "== x264 $X264_COMMIT"
if [ ! -f "$PREFIX/lib/libx264.a" ]; then
rm -rf x264 && git init -q x264 && cd x264
git remote add origin https://code.videolan.org/videolan/x264.git
git fetch -q --depth 1 origin "$X264_COMMIT" && git checkout -q FETCH_HEAD
./configure --prefix="$PREFIX" --enable-static --disable-cli --enable-pic >/dev/null && make -j"$JOBS" >/dev/null && make install >/dev/null
cd "$WORK"
fi

echo "== FFmpeg $FFMPEG_VERSION"
fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" "$FFMPEG_SHA256" "ffmpeg.tar.xz"
rm -rf "ffmpeg-$FFMPEG_VERSION" && tar xf ffmpeg.tar.xz
cd "ffmpeg-$FFMPEG_VERSION"
PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" ./configure \
    --prefix="$PREFIX" --arch=arm64 \
    --enable-gpl --enable-version3 \
    --enable-libx264 --enable-libmp3lame \
    --disable-autodetect --enable-avfoundation --enable-videotoolbox --enable-audiotoolbox \
    --enable-zlib --enable-bzlib \
    --pkg-config-flags="--static" \
    --extra-cflags="-I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib" \
    --disable-shared --enable-static --disable-doc --disable-ffplay --disable-debug \
    >/dev/null
make -j"$JOBS" >/dev/null
cp ffmpeg ffprobe "$OUT/"
strip "$OUT/ffmpeg" "$OUT/ffprobe"
cp COPYING.GPLv2 "$OUT/FFMPEG-COPYING.GPLv2" 2>/dev/null || true
echo "$FFMPEG_VERSION" > "$OUT/FFMPEG-VERSION"

# GPL 對應原始碼：FFmpeg、LAME、x264 與本建置腳本，隨 Release 一併提供
SRC_STAGE="$WORK/corresponding-source"
rm -rf "$SRC_STAGE" && mkdir -p "$SRC_STAGE"
cp "$WORK/ffmpeg.tar.xz" "$SRC_STAGE/ffmpeg-$FFMPEG_VERSION.tar.xz"
cp "$WORK/lame.tar.gz" "$SRC_STAGE/lame-$LAME_VERSION.tar.gz"
if [ -d "$WORK/x264/.git" ]; then
    git -C "$WORK/x264" archive --format=tar.gz --prefix="x264-${X264_COMMIT:0:10}/" -o "$SRC_STAGE/x264-${X264_COMMIT:0:10}.tar.gz" HEAD
fi
cp "$ROOT/tools/build_ffmpeg_macos.sh" "$SRC_STAGE/build_ffmpeg_macos.sh"
tar -C "$SRC_STAGE" -czf "$OUT/../AURA-REC-ffmpeg-source.tar.gz" .

echo "== Dependencies (must only be system libraries/frameworks):"
otool -L "$OUT/ffmpeg" | tail -n +2
if otool -L "$OUT/ffmpeg" | grep -E "/opt/homebrew|/usr/local"; then echo "ERROR: non-system dylib linked"; exit 1; fi
"$OUT/ffmpeg" -hide_banner -version | head -1
