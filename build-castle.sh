#!/bin/sh
set -eu
root=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$root"
rom=${1:-$root/private/sm64ds_usa.nds}
sdk=${LIBSATURN_PREFIX:-$root/../saturn-prefix}
source=${LIBSATURN_SOURCE:-$root/../lib-saturn}
compiler=${LIBSATURN_TOOLCHAIN_ROOT:-$root/../saturn-tools/bin}
python3 tools/prepare_intro.py --rom "$rom" --out private/intro
python3 tools/prepare_castle.py --rom "$rom" --out private/castle \
  --merge-quads --vertex-colors --lut4 \
  --max-edge 48 --chunk-size 128 --max-tile-size 48 \
  --texture-samples 4 --adaptive-priorities tools/castle_adaptive_priorities.json \
  --texture-budget 245760 --with-intro-props
python3 tools/prepare_castle.py --rom "$rom" --out private/castle_1f \
  --stage castle_1f --warp-target EXT.BIN \
  --merge-quads --vertex-colors --lut4 \
  --max-edge 40 --max-tile-size 48 --texture-samples 2 \
  --texture-budget 245760
python3 tools/prepare_castle.py --rom "$rom" --out private/bob \
  --stage bombhei_map --merge-quads --vertex-colors --lut4 \
  --max-edge 48 --chunk-size 128 --max-tile-size 48 --texture-samples 4 \
  --texture-budget 245760
# Castle Courtyard: first phase-7 rollout stage. Smaller and simpler than BoB.
# The courtyard has a shallow pond (water surface y=3.2) drawn as a lib-saturn
# water plane; --water-layers enables the surface, underwater tint and passes.
python3 tools/prepare_castle.py --rom "$rom" --out private/garden \
  --stage main_garden --merge-quads --vertex-colors --lut4 \
  --max-edge 48 --chunk-size 128 --max-tile-size 48 --texture-samples 4 \
  --texture-budget 245760 --water-layers
# Whomp's Fortress: phase-7 rollout stage 2.
python3 tools/prepare_castle.py --rom "$rom" --out private/wf \
  --stage battan_king_map --merge-quads --vertex-colors --lut4 \
  --max-edge 48 --chunk-size 128 --max-tile-size 48 --texture-samples 4 \
  --texture-budget 245760
# Jolly Roger Bay: phase-7 rollout stage 3.
python3 tools/prepare_castle.py --rom "$rom" --out private/jrb \
  --stage kaizoku_irie --merge-quads --vertex-colors --lut4 \
  --max-edge 112 --chunk-size 128 --max-tile-size 32 --texture-samples 2 \
  --texture-budget 196608 --water-layers
# Boss-rush variant: same course and actor kinds, Mario starts on the summit
# arena floor at its east end, facing the King Bob-omb at (96, -345) so the
# fight is a short walk toward him (not a drop-in on his head). The arena floor
# is ~268 at the boss; spawning at (150, -345) keeps a clear 54-unit gap.
python3 tools/prepare_castle.py --rom "$rom" --out private/bob_boss \
  --stage bombhei_map --merge-quads --vertex-colors --lut4 \
  --max-edge 48 --chunk-size 128 --max-tile-size 48 --texture-samples 4 \
  --texture-budget 245760 --spawn 150 -345 268 --spawn-yaw 90
cmake -S . -B build/castle -G Ninja \
  "-DCMAKE_TOOLCHAIN_FILE=$source/cmake/toolchains/sh2eb-elf.cmake" \
  "-DLIBSATURN_TOOLCHAIN_ROOT=$compiler" "-DCMAKE_PREFIX_PATH=$sdk" \
  "-DSM64DS_GENERATED_DIR=$root/private/castle" \
  "-DSM64DS_CASTLE_1F_DIR=$root/private/castle_1f" \
  "-DSM64DS_INTRO_DIR=$root/private/intro" "-DSM64DS_BOB_DIR=$root/private/bob" \
  "-DSM64DS_BOB_BOSS_DIR=$root/private/bob_boss" \
  "-DSM64DS_GARDEN_DIR=$root/private/garden" \
  "-DSM64DS_WF_DIR=$root/private/wf" \
  "-DSM64DS_JRB_DIR=$root/private/jrb" \
  -DSM64DS_BUILD_CASTLE=ON -DSM64DS_VISUAL_DIAGNOSTICS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/castle --target sm64ds_intro_disc sm64ds_castle_disc sm64ds_castle_1f_disc sm64ds_bob_stage_bin sm64ds_bob_disc sm64ds_bob_boss_stage_bin sm64ds_bob_boss_disc sm64ds_garden_stage_bin sm64ds_garden_disc sm64ds_wf_stage_bin sm64ds_wf_disc sm64ds_jrb_stage_bin sm64ds_jrb_disc --parallel 4
