#!/bin/bash
# Cross-compile a self-contained (static) ffmpeg.exe + ffprobe.exe for Windows x64 with
# x264, LAME, NVENC (nv-codec-headers), AMD AMF and Intel QSV (libvpl). Runs on Linux or macOS
# with mingw-w64, nasm, cmake and pkg-config installed.
# The result is GPL-2.0-or-later (libx264); it ships as separate executables next to AURA-REC.exe.
# See THIRD_PARTY_NOTICES.md for the license text and source offer.
#
# Usage: tools/build_ffmpeg_windows.sh [output_dir]   (default: build/ffmpeg-win-bin)
set -euo pipefail

FFMPEG_VERSION="7.1.1"
FFMPEG_SHA256="733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1"
ZLIB_VERSION="1.3.1"
ZLIB_SHA256="9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23"
LAME_VERSION="3.100"
LAME_SHA256="ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e"
X264_COMMIT="${X264_COMMIT:-b35605ace3ddf7c1a5d67a2eb553f034aef41d55}"   # videolan/x264 stable
NVCODEC_TAG="n12.2.72.0"
AMF_TAG="v1.4.35"
LIBVPL_TAG="v2.15.0"

HOST="x86_64-w64-mingw32"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SELF="$ROOT/tools/$(basename "$0")"
OUT="${1:-$ROOT/build/ffmpeg-win-bin}"
WORK="$ROOT/build/ffmpeg-win-src"
PREFIX="$ROOT/build/ffmpeg-win-prefix"
JOBS="$( (sysctl -n hw.ncpu 2>/dev/null || nproc) )"

for tool in ${HOST}-gcc nasm cmake pkg-config git make curl; do
    command -v "$tool" >/dev/null || { echo "缺少 $tool（需要 mingw-w64、nasm、cmake、pkg-config）"; exit 1; }
done

mkdir -p "$WORK" "$PREFIX/lib/pkgconfig" "$OUT"
cd "$WORK"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$PREFIX/lib/pkgconfig"

fetch() { # url sha256 file
    [ -f "$3" ] || curl -fsSL --retry 3 -o "$3" "$1"
    echo "$2  $3" | shasum -a 256 -c -
}
git_checkout() { # dir url ref
    if [ ! -d "$1/.git" ]; then
        rm -rf "$1" && git init -q "$1"
        git -C "$1" remote add origin "$2"
    fi
    git -C "$1" fetch -q --depth 1 origin "$3" && git -C "$1" checkout -q -f FETCH_HEAD
}

echo "== zlib $ZLIB_VERSION"
if [ ! -f "$PREFIX/lib/libz.a" ]; then
    fetch "https://github.com/madler/zlib/releases/download/v$ZLIB_VERSION/zlib-$ZLIB_VERSION.tar.gz" "$ZLIB_SHA256" "zlib.tar.gz"
    rm -rf "zlib-$ZLIB_VERSION" && tar xf zlib.tar.gz
    ( cd "zlib-$ZLIB_VERSION" && CROSS_PREFIX=${HOST}- uname=MINGW ./configure --static --prefix="$PREFIX" >/dev/null && make -j"$JOBS" libz.a >/dev/null && make install >/dev/null )
fi

echo "== LAME $LAME_VERSION"
if [ ! -f "$PREFIX/lib/libmp3lame.a" ]; then
    fetch "https://downloads.sourceforge.net/project/lame/lame/$LAME_VERSION/lame-$LAME_VERSION.tar.gz" "$LAME_SHA256" "lame.tar.gz"
    rm -rf "lame-$LAME_VERSION" && tar xf lame.tar.gz
    ( cd "lame-$LAME_VERSION" && ./configure --host=$HOST --prefix="$PREFIX" --disable-shared --enable-static --disable-frontend >/dev/null && make -j"$JOBS" >/dev/null && make install >/dev/null )
fi

echo "== x264 $X264_COMMIT"
if [ ! -f "$PREFIX/lib/libx264.a" ]; then
    git_checkout x264 https://code.videolan.org/videolan/x264.git "$X264_COMMIT"
    ( cd x264 && ./configure --host=$HOST --cross-prefix=${HOST}- --prefix="$PREFIX" --enable-static --disable-cli --enable-pic >/dev/null && make -j"$JOBS" >/dev/null && make install >/dev/null )
fi

echo "== nv-codec-headers $NVCODEC_TAG (NVENC)"
git_checkout nv-codec-headers https://github.com/FFmpeg/nv-codec-headers.git "refs/tags/$NVCODEC_TAG"
make -C nv-codec-headers PREFIX="$PREFIX" install >/dev/null

echo "== AMF headers $AMF_TAG"
git_checkout AMF https://github.com/GPUOpen-LibrariesAndSDKs/AMF.git "refs/tags/$AMF_TAG"
mkdir -p "$PREFIX/include" && rm -rf "$PREFIX/include/AMF" && cp -R AMF/amf/public/include "$PREFIX/include/AMF"

echo "== libvpl $LIBVPL_TAG (Intel QSV)"
if [ ! -f "$PREFIX/lib/libvpl.a" ]; then
    git_checkout libvpl https://github.com/intel/libvpl.git "refs/tags/$LIBVPL_TAG"
    cat > "$WORK/mingw-toolchain.cmake" <<TC
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER ${HOST}-gcc)
set(CMAKE_CXX_COMPILER ${HOST}-g++)
set(CMAKE_RC_COMPILER ${HOST}-windres)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
TC
    rm -rf libvpl/build
    cmake -S libvpl -B libvpl/build -DCMAKE_TOOLCHAIN_FILE="$WORK/mingw-toolchain.cmake" \
        -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
        -DBUILD_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_PREVIEW=OFF -DINSTALL_EXAMPLE_CODE=OFF \
        -DBUILD_DISPATCHER_ONEVPL_EXPERIMENTAL=OFF >/dev/null
    cmake --build libvpl/build -j"$JOBS" >/dev/null && cmake --install libvpl/build >/dev/null
fi

echo "== FFmpeg $FFMPEG_VERSION"
fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" "$FFMPEG_SHA256" "ffmpeg.tar.xz"
rm -rf "ffmpeg-$FFMPEG_VERSION" && tar xf ffmpeg.tar.xz
cd "ffmpeg-$FFMPEG_VERSION"
./configure \
    --prefix="$PREFIX" --arch=x86_64 --target-os=mingw32 --cross-prefix=${HOST}- \
    --pkg-config=pkg-config --pkg-config-flags="--static" \
    --disable-autodetect --enable-gpl --enable-version3 \
    --enable-libx264 --enable-libmp3lame \
    --enable-ffnvcodec --enable-nvenc --enable-amf --enable-libvpl \
    --enable-d3d11va --enable-dxva2 --enable-schannel \
    --enable-zlib \
    --extra-cflags="-I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib -static" \
    --extra-libs="-lstdc++" \
    --disable-shared --enable-static --disable-doc --disable-ffplay --disable-debug \
    >/dev/null
make -j"$JOBS" >/dev/null
${HOST}-strip -o "$OUT/ffmpeg.exe" ffmpeg.exe
${HOST}-strip -o "$OUT/ffprobe.exe" ffprobe.exe
cp COPYING.GPLv2 "$OUT/FFMPEG-COPYING.GPLv2" 2>/dev/null || true
echo "$FFMPEG_VERSION" > "$OUT/FFMPEG-VERSION"
cd "$WORK"

# GPL 對應原始碼（隨 Release 一併提供）
SRC_STAGE="$WORK/corresponding-source"
rm -rf "$SRC_STAGE" && mkdir -p "$SRC_STAGE"
cp ffmpeg.tar.xz "$SRC_STAGE/ffmpeg-$FFMPEG_VERSION.tar.xz"
cp lame.tar.gz "$SRC_STAGE/lame-$LAME_VERSION.tar.gz"
cp zlib.tar.gz "$SRC_STAGE/zlib-$ZLIB_VERSION.tar.gz"
git -C x264 archive --format=tar.gz --prefix="x264-${X264_COMMIT:0:10}/" -o "$SRC_STAGE/x264-${X264_COMMIT:0:10}.tar.gz" HEAD
git -C nv-codec-headers archive --format=tar.gz --prefix="nv-codec-headers-$NVCODEC_TAG/" -o "$SRC_STAGE/nv-codec-headers-$NVCODEC_TAG.tar.gz" HEAD
# AMF 倉庫很大（文件與範例），只需其公開標頭與授權；完整原始碼見 https://github.com/GPUOpen-LibrariesAndSDKs/AMF
git -C AMF archive --format=tar.gz --prefix="AMF-$AMF_TAG/" -o "$SRC_STAGE/AMF-$AMF_TAG-headers.tar.gz" HEAD amf/public/include LICENSE.txt
git -C libvpl archive --format=tar.gz --prefix="libvpl-$LIBVPL_TAG/" -o "$SRC_STAGE/libvpl-$LIBVPL_TAG.tar.gz" HEAD
cp "$SELF" "$SRC_STAGE/build_ffmpeg_windows.sh"
tar -C "$SRC_STAGE" -czf "$OUT/../AURA-REC-ffmpeg-win-source.tar.gz" .

echo "== Result"
file "$OUT/ffmpeg.exe" | cut -c1-120
ls -lh "$OUT"
