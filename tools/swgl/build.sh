#!/bin/bash
# Программный OpenGL для проверки шейдеров без видеокарты: всё собирается из исходников с GitHub (около 45 минут).
#   инструменты:  pip install cmake==3.31.10 ninja meson mako pyyaml pkgconf bison-bin flex-bin  (в venv /home/user/.venvs/dd)
#   deps.sh — zlib, expat, libdrm;  m4.sh — GNU m4 (нужен bison и flex);  llvm.sh — LLVM 10;  mesa.sh — Mesa 21.3.9
R=/home/user/.cache/glsw
$R/deps.sh && $R/m4.sh && $R/llvm.sh && $R/mesa.sh
