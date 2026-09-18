# CMake toolchain file for LoongArch64 cross-compilation.
#
# Uses the musl.cc prebuilt toolchain. Download it and add to PATH:
#   curl -fsSL https://musl.cc/loongarch64-linux-musl-cross.tgz | sudo tar -xz -C /opt
#   export PATH="/opt/loongarch64-linux-musl-cross/bin:${PATH}"

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR loongarch64)

set(CMAKE_C_COMPILER   loongarch64-linux-musl-gcc)
set(CMAKE_CXX_COMPILER loongarch64-linux-musl-g++)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
