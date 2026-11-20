#!/bin/bash
set -e
export PATH=/home/user/.venvs/dd/bin:$PATH
D=/home/user/.cache/glsw/deps
mkdir -p $D /home/user/.cache/glsw/src
cd /home/user/.cache/glsw/src
export PKG_CONFIG_PATH=$D/lib/pkgconfig
[ -d zlib ] || git clone -q --depth 1 --branch v1.3.1 https://github.com/madler/zlib 2>/dev/null
(cd zlib && CFLAGS="-O2 -fPIC" ./configure --prefix=$D --static > ../zlib.log 2>&1 && make -j2 install >> ../zlib.log 2>&1)
[ -d libexpat ] || git clone -q --depth 1 --branch R_2_6_4 https://github.com/libexpat/libexpat 2>/dev/null
cmake -G Ninja -S libexpat/expat -B expat-build -DCMAKE_INSTALL_PREFIX=$D -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_BUILD_TYPE=Release \
  -DEXPAT_BUILD_TOOLS=OFF -DEXPAT_BUILD_EXAMPLES=OFF -DEXPAT_BUILD_TESTS=OFF -DEXPAT_BUILD_DOCS=OFF -DEXPAT_SHARED_LIBS=OFF \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON > expat.log 2>&1
ninja -C expat-build install >> expat.log 2>&1
[ -d libdrm ] || git clone -q --depth 1 --branch libdrm-2.4.100 https://github.com/grate-driver/libdrm 2>/dev/null
rm -rf drm-build
meson setup drm-build libdrm --prefix=$D --libdir=lib --buildtype=release \
  -Dlibkms=false -Dintel=false -Dradeon=false -Damdgpu=false -Dnouveau=false -Dvmwgfx=false -Domap=false -Dexynos=false \
  -Dfreedreno=false -Dtegra=false -Dvc4=false -Detnaviv=false -Dcairo-tests=false -Dman-pages=false -Dvalgrind=false \
  -Dudev=false -Dinstall-test-programs=false > drm-conf.log 2>&1
ninja -C drm-build install > drm-make.log 2>&1
echo DEPS_DONE
