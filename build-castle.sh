#!/bin/sh
set -eu
root=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$root"
rom=${1:-$root/private/sm64ds_usa.nds}
sdk=${LIBSATURN_PREFIX:-$root/../saturn-prefix-gc}
source=${LIBSATURN_SOURCE:-$root/../lib-saturn}
compiler=${LIBSATURN_TOOLCHAIN_ROOT:-$root/../saturn-tools/bin}
python3 tools/prepare_castle.py --rom "$rom" --out private/castle \
  --merge-quads --vertex-colors --lut4 \
  --max-edge 48 --chunk-size 128 --max-tile-size 48 \
  --texture-samples 4 --adaptive-priorities tools/castle_adaptive_priorities.json \
  --texture-budget 245760
python3 tools/prepare_castle.py --rom "$rom" --out private/castle_1f \
  --stage castle_1f \
  --merge-quads --vertex-colors --lut4 \
  --max-edge 40 --max-tile-size 48 --texture-samples 2 \
  --texture-budget 245760
cmake -S . -B build/castle -G Ninja \
  "-DCMAKE_TOOLCHAIN_FILE=$source/cmake/toolchains/sh2eb-elf.cmake" \
  "-DLIBSATURN_TOOLCHAIN_ROOT=$compiler" "-DCMAKE_PREFIX_PATH=$sdk" \
  "-DSM64DS_GENERATED_DIR=$root/private/castle" \
  "-DSM64DS_CASTLE_1F_DIR=$root/private/castle_1f" \
  -DSM64DS_BUILD_CASTLE=ON -DSM64DS_VISUAL_DIAGNOSTICS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/castle --target sm64ds_castle_disc sm64ds_castle_1f_disc --parallel 4
