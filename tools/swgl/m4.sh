#!/bin/bash
# GNU m4 1.4.18 (нужен bison и flex) -> /home/user/.cache/glsw/deps/bin/m4
set -e
export PATH=/home/user/.venvs/dd/bin:$PATH
D=/home/user/.cache/glsw/deps
mkdir -p /home/user/.cache/glsw/src $D/bin
cd /home/user/.cache/glsw/src
[ -d gnu-m4 ] || git clone -q --depth 1 --branch v1.4.18 https://github.com/tar-mirror/gnu-m4 2>/dev/null
cd gnu-m4
# glibc 2.28+: gnulib из этой версии не знает новой libio; glibc 2.34+: SIGSTKSZ больше не константа
sed -i 's/IO_ftrylockfile/IO_EOF_SEEN/' lib/*.c
grep -q "_IO_IN_BACKUP 0x100" lib/stdio-impl.h || echo "#define _IO_IN_BACKUP 0x100" >> lib/stdio-impl.h
grep -q "^#undef SIGSTKSZ" lib/c-stack.c || sed -i 's/^#ifndef SIGSTKSZ$/#undef SIGSTKSZ\n#ifndef SIGSTKSZ/' lib/c-stack.c
# одинаковое время у всех файлов: иначе make решит пересобрать configure и документацию
find . -not -path './.git/*' -exec touch -d '2017-01-01 00:00:00' {} +
./configure --prefix=$D --disable-dependency-tracking > ../m4-conf.log 2>&1 || { tail -20 ../m4-conf.log; exit 1; }
make -C lib -j2 > ../m4-make.log 2>&1 || { grep -a "error" ../m4-make.log | head -20; exit 1; }
make -C src -j2 >> ../m4-make.log 2>&1 || { grep -a "error" ../m4-make.log | head -20; exit 1; }
cp src/m4 $D/bin/m4
$D/bin/m4 --version | head -1
echo M4_DONE
