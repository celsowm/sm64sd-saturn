#!/usr/bin/env python3
"""Local-only SM64DS -> LibSaturn. Delegates to tools/sm64ds_pipeline/."""
from sm64ds_pipeline import (FormatError, field, region, signed10, signed16,
    checked_fx, quaternion, lz77, fnt_names, Filesystem, Narc, Vertex, gx_params,
    Bone, Model, convert_bmd, Channel, Animation, emit_model)
from sm64ds_pipeline.cli import main

if __name__ == '__main__':
    try:
        main()
    except (FormatError, OSError) as err:
        raise SystemExit(f'asset conversion failed: {err}') from err
