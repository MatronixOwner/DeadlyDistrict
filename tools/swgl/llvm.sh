#!/bin/bash
# LLVM 10.0.0 (только то, что нужно llvmpipe) -> /home/user/.cache/glsw/llvm-build
R=/home/user/.cache/glsw
V=/home/user/.venvs/dd/bin
export PATH=$V:$PATH
cd $R || exit 1
if [ ! -d llvm-src/llvm ]; then
  rm -rf llvm-src
  git clone -q --depth 1 --branch llvmorg-10.0.0 --filter=blob:none --sparse https://github.com/llvm/llvm-project.git llvm-src || exit 1
  (cd llvm-src && git sparse-checkout set llvm) || exit 1
fi
echo "LLVM_SRC_OK $(date +%T)"
if [ ! -f llvm-build/build.ninja ]; then
  cmake -G Ninja -S llvm-src/llvm -B llvm-build \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="-w" -DCMAKE_CXX_FLAGS="-w" \
    -DCMAKE_C_FLAGS_RELEASE="-O1 -DNDEBUG" -DCMAKE_CXX_FLAGS_RELEASE="-O1 -DNDEBUG" \
    -DLLVM_TARGETS_TO_BUILD=X86 -DLLVM_BUILD_TOOLS=OFF -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF \
    -DLLVM_INCLUDE_BENCHMARKS=OFF -DLLVM_INCLUDE_DOCS=OFF -DLLVM_INCLUDE_GO_TESTS=OFF \
    -DLLVM_ENABLE_TERMINFO=OFF -DLLVM_ENABLE_ZLIB=OFF -DLLVM_ENABLE_LIBXML2=OFF -DLLVM_ENABLE_LIBEDIT=OFF \
    -DLLVM_ENABLE_LIBPFM=OFF -DLLVM_ENABLE_BINDINGS=OFF -DLLVM_ENABLE_OCAMLDOC=OFF -DLLVM_ENABLE_Z3_SOLVER=OFF \
    -DLLVM_ENABLE_ASSERTIONS=OFF -DLLVM_ENABLE_PIC=ON -DLLVM_ENABLE_RTTI=ON \
    -DPYTHON_EXECUTABLE=$V/python > cmake.log 2>&1 || { tail -30 cmake.log; echo LLVM_CMAKE_FAIL; exit 1; }
fi
echo "LLVM_CMAKE_OK $(date +%T)"
T="llvm-config LLVMMCJIT LLVMInterpreter LLVMX86CodeGen LLVMX86AsmParser LLVMX86Disassembler LLVMX86Desc LLVMX86Info LLVMX86Utils LLVMBitWriter LLVMBitReader LLVMMCDisassembler LLVMCore LLVMExecutionEngine LLVMScalarOpts LLVMTransformUtils LLVMInstCombine LLVMCoroutines LLVMipo LLVMIRReader LLVMAsmParser LLVMLinker LLVMVectorize LLVMInstrumentation LLVMAggressiveInstCombine"
nice -n 10 ninja -C llvm-build -k 0 $T > ninja.log 2>&1
rc=$?
echo "LLVM_NINJA rc=$rc $(date +%T)"
grep -a "error:" ninja.log | sort | uniq -c | head -20
[ $rc = 0 ] && echo LLVM_DONE
