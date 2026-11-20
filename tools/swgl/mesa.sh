#!/bin/bash
# Mesa 21.3.9: llvmpipe + EGL без окна -> /home/user/.cache/glsw/mesa (libEGL.so.1, libGL.so.1, lib/dri/swrast_dri.so)
R=/home/user/.cache/glsw
D=$R/deps
V=/home/user/.venvs/dd/bin
export PATH=$V:$D/bin:$PATH M4=$D/bin/m4 PKG_CONFIG_PATH=$D/lib/pkgconfig
cd $R/src || exit 1
[ -d mesa ] || git clone -q --depth 1 --branch mesa-21.3.9 https://github.com/FireBurn/mesa 2>/dev/null
printf "[binaries]\nllvm-config = '%s/llvm-wrap/llvm-config'\n" $R > native.ini
if [ ! -f mesa-build/build.ninja ]; then
  rm -rf mesa-build
  meson setup mesa-build mesa --prefix=$R/mesa --libdir=lib --buildtype=release --native-file native.ini \
    -Dplatforms= -Dglx=disabled -Degl=enabled -Dgbm=disabled -Dgles1=disabled -Dgles2=disabled -Dopengl=true -Dshared-glapi=enabled \
    -Ddri-drivers= -Dgallium-drivers=swrast -Dvulkan-drivers= -Dllvm=enabled -Dshared-llvm=disabled -Ddri3=disabled \
    -Dgallium-vdpau=disabled -Dgallium-xvmc=disabled -Dgallium-omx=disabled -Dgallium-va=disabled -Dgallium-xa=disabled \
    -Dgallium-nine=false -Dgallium-opencl=disabled -Dvalgrind=disabled -Dlibunwind=disabled -Dlmsensors=disabled \
    -Dzstd=disabled -Dselinux=false -Dosmesa=false -Dbuild-tests=false -Dmicrosoft-clc=disabled -Dglvnd=false \
    -Dc_args=-w -Dcpp_args=-w > mesa-conf.log 2>&1 || { tail -30 mesa-conf.log; echo MESA_CONF_FAIL; exit 1; }
fi
echo "MESA_CONF_OK $(date +%T)"
nice -n 10 ninja -C mesa-build -k 0 > mesa-make.log 2>&1
rc=$?
echo "MESA_NINJA rc=$rc $(date +%T)"
if [ $rc != 0 ]; then grep -a "error:\|FAILED\|undefined reference" mesa-make.log | sort | uniq -c | head -30; exit 1; fi
ninja -C mesa-build src/mapi/glapi/libglapi_static.a >> mesa-make.log 2>&1 || { echo BRIDGE_FAIL; tail -5 mesa-make.log; exit 1; }
ninja -C mesa-build install > mesa-install.log 2>&1 || { echo INSTALL_FAIL; tail -5 mesa-install.log; exit 1; }
gcc -shared -o $R/mesa/lib/libGL.so.1 -Wl,-soname,libGL.so.1 -Wl,--whole-archive mesa-build/src/mapi/glapi/libglapi_static.a \
  -Wl,--no-whole-archive -L$R/mesa/lib -lglapi -lpthread || { echo LIBGL_FAIL; exit 1; }
cp -a $D/lib/libdrm.so* $R/mesa/lib/
ls $R/mesa/lib $R/mesa/lib/dri
echo BUILD_DONE
