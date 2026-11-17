#!/bin/sh
set -eu
root=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$root"
rom=${1:-$root/private/sm64ds_usa.nds}
sdk=${LIBSATURN_PREFIX:-$root/../saturn-prefix-gc}
source=${LIBSATURN_SOURCE:-$root/../lib-saturn}
compiler=${LIBSATURN_TOOLCHAIN_ROOT:-$root/../saturn-tools/bin}
python3 tools/prepare_castle.py --rom "$rom" --out private/castle \
  --sdk-split-grid 64 --split-radius 48 --libsaturn-source "$source" \
  --refine-manifest tools/castle_refine_faces.json --refine-grid 32 \
  --tile-size 8 --texture-samples 4 \
  --adaptive-faces 128 --adaptive-priorities tools/castle_adaptive_priorities.json \
  --texture-budget 196608
cmake -S . -B build/castle -G Ninja \
  "-DCMAKE_TOOLCHAIN_FILE=$source/cmake/toolchains/sh2eb-elf.cmake" \
  "-DLIBSATURN_TOOLCHAIN_ROOT=$compiler" "-DCMAKE_PREFIX_PATH=$sdk" \
  "-DSM64DS_GENERATED_DIR=$root/private/castle" \
  -DSM64DS_BUILD_CASTLE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/castle --target sm64ds_castle_disc --parallel 4
