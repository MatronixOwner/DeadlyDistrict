#!/bin/bash
# gl.sh КОМАНДА… — запуск под программным OpenGL (Mesa llvmpipe, EGL без окна)
R=/home/user/.cache/glsw/mesa
export LD_LIBRARY_PATH=$R/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export LIBGL_DRIVERS_PATH=$R/lib/dri EGL_PLATFORM=surfaceless LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
export DD_TEST_DISPLAY=p3headlessgl LP_NUM_THREADS=${LP_NUM_THREADS:-2}
exec "$@"
