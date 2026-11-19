#!/usr/bin/env python3
"""Build and capture Saturn views matched to DS Mario/camera RAM dumps."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ("rear", "side", "front")


def run(command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(command, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/castle-match")
    parser.add_argument("--generated-dir", type=Path, default=ROOT / "private/castle-refined")
    parser.add_argument("--probe", type=Path, default=ROOT.parent / "lib-saturn/harness/build-macos/probe")
    parser.add_argument("--bios", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "private/castle-comparison-fixed/direct")
    parser.add_argument("--nm", type=Path, default=ROOT.parent / "saturn-tools/bin/sh2eb-elf-nm")
    parser.add_argument("--frames", type=int, default=400)
    parser.add_argument("--views", nargs="+", default=VIEWS,
                        help="names of ds-NAME-ram.bin and ds-NAME.png inputs")
    parser.add_argument("--match-player-y", action="store_true",
                        help="use the captured DS height instead of the Saturn floor height")
    parser.add_argument("--support-fix", action="store_true",
                        help="enable the experimental guarded sloped-support correction")
    parser.add_argument("--ground-pose", action="store_true",
                        help="enable experimental ground-pose adjustment")
    parser.add_argument("--castle-face-ids", action="store_true",
                        help="encode castle face IDs in the capture")
    parser.add_argument("--fallback-color", action="store_true",
                        help="highlight castle texture fallback faces")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    ds_dir = out.parent
    cmake = [
        "cmake", "-S", str(ROOT), "-B", str(args.build_dir),
        "-DSM64DS_BUILD_CASTLE=ON", "-DSM64DS_VISUAL_DIAGNOSTICS=ON",
        f"-DSM64DS_GENERATED_DIR={args.generated_dir.resolve()}",
        "-DSM64DS_DIAG_FIXED_CAMERA=ON", "-DSM64DS_DIAG_ABSOLUTE_CAMERA=ON",
        "-DSM64DS_DIAG_ORBIT_PLAYER=OFF",
        "-DSM64DS_DIAG_LIVE_ANIMATION=OFF",
        f"-DSM64DS_DIAG_GROUND_POSE={'ON' if args.ground_pose else 'OFF'}",
        f"-DSM64DS_DIAG_OVERRIDE_PLAYER_Y={'ON' if args.match_player_y else 'OFF'}",
        "-DSM64DS_DIAG_FAR_DEPTH_COUNT=0",
        "-DSM64DS_DIAG_GEOMETRIC_DEPTH=OFF",
        "-DSM64DS_DIAG_PAIR_DEPTH=OFF",
        f"-DSM64DS_DIAG_SUPPORT_DEPTH={'ON' if args.support_fix else 'OFF'}",
        f"-DSM64DS_DIAG_SUPPORT_AUTO={'ON' if args.support_fix else 'OFF'}",
        f"-DSM64DS_DIAG_SLOPED_SUPPORT={'ON' if args.support_fix else 'OFF'}",
        "-DSM64DS_DIAG_SUPPORT_GUARD=ON",
        "-DSM64DS_DIAG_WALL_FIXTURE=OFF",
        "-DSM64DS_DIAG_WALL_PARTIAL=OFF",
        "-DSM64DS_DIAG_DS_ASPECT=ON", "-DSM64DS_DIAG_SHOW_UI=OFF",
        "-DSM64DS_DIAG_OBJECTS=15", "-DSM64DS_DIAG_CLOSE_CAMERA=OFF",
        "-DSM64DS_DIAG_NO_CULL=OFF", "-DSM64DS_DIAG_SOLID=OFF",
        "-DSM64DS_DIAG_FACE_IDS=OFF",
        f"-DSM64DS_DIAG_CASTLE_FACE_IDS={'ON' if args.castle_face_ids else 'OFF'}",
        f"-DSM64DS_DIAG_CASTLE_FALLBACK_COLOR={'ON' if args.fallback_color else 'OFF'}",
        "-DSM64DS_DIAG_FLOOR_CEILING=512",
    ]
    probe = args.probe.resolve()
    bios = args.bios.resolve()
    sys.path.insert(0, str(ROOT / "tools"))
    from inspect_ds_castle_state import inspect

    for name in args.views:
        ds_path = ds_dir / f"ds-{name}-camera.json"
        ds = inspect((ds_dir / f"ds-{name}-ram.bin").read_bytes(), 0.064)
        ds_path.write_text(json.dumps(ds, indent=2) + "\n")
        mario = ds["mario"]["position_saturn_units"]
        eye = ds["camera"]["eye_saturn_units"]
        target = ds["camera"]["look_at_saturn_units"]
        facing = round(ds["mario"]["facing_degrees"]) % 360
        fov = round(ds["camera"]["fov_y_degrees"])
        flags = [
            f"-DSM64DS_DIAG_CAMERA_X={eye[0]}", f"-DSM64DS_DIAG_CAMERA_Y={eye[1]}",
            f"-DSM64DS_DIAG_CAMERA_Z={eye[2]}", f"-DSM64DS_DIAG_TARGET_X={target[0]}",
            f"-DSM64DS_DIAG_TARGET_Y={target[1]}", f"-DSM64DS_DIAG_TARGET_Z={target[2]}",
            f"-DSM64DS_DIAG_YAW={round(ds['camera']['yaw_degrees']) % 360}",
            f"-DSM64DS_DIAG_FACING={facing}", f"-DSM64DS_DIAG_FOV_Y={fov}",
            f"-DSM64DS_DIAG_X={mario[0]}", f"-DSM64DS_DIAG_Z={mario[2]}",
            f"-DSM64DS_DIAG_PLAYER_Y={mario[1] if args.match_player_y else 0}",
        ]
        run(cmake + flags)
        run(["cmake", "--build", str(args.build_dir), "--target", "sm64ds_castle_disc", "--parallel", "4"])
        stem = out / name
        elf = args.build_dir / "sm64ds_castle.elf"
        shutil.copy2(elf, stem.with_suffix(".elf"))
        cue = args.build_dir / "disc/sm64ds_castle.cue"
        run([
            str(probe), "--iso", str(cue), "--bin", str(args.build_dir / "sm64ds_castle.app.bin"),
            "--bios", str(bios), "--boot-mode", "injection", "--frames", str(args.frames),
            "--screenshot", f"{args.frames - 1}:{stem}.png",
            "--dump-wram-high", f"{stem}-wram.bin",
            "--misaligned-report", f"{stem}-misaligned.json",
        ], cwd=ROOT)
        from check_castle_capture import check

        report = check(stem.with_suffix(".elf"), stem.with_name(name + "-wram.bin"), args.nm, "boot")
        (stem.with_name(name + "-telemetry.json")).write_text(json.dumps(report, indent=2) + "\n")
        expected = {
            "x_units": mario[0], "y_units": mario[1], "z_units": mario[2],
            "camera_x_units": eye[0], "camera_y_units": eye[1], "camera_z_units": eye[2],
            "target_x_units": target[0], "target_y_units": target[1], "target_z_units": target[2],
        }
        errors = {key: report[key] - value for key, value in expected.items()
                  if abs(report[key] - value) > 0.002}
        if (errors or report["mario_facing_units"] != facing or report["camera_fov_y_units"] != fov
                or report["grounded"] != 1):
            raise RuntimeError(f"{name}: state mismatch: {errors}; telemetry={report}")
        (stem.with_name(name + "-mapping.json")).write_text(json.dumps({
            "view": name, "ds_capture": str(ds_dir / f"ds-{name}.png"),
            "mario_ds_units": ds["mario"]["position_ds_units"],
            "scale_ds_to_saturn": ds["mapping"]["scale"],
            "offset_saturn_units": ds["mapping"]["offset_saturn_units"],
            "mario_saturn_units": mario, "facing_degrees": facing,
            "fov_degrees": fov, "camera_eye": eye, "camera_target": target,
            "source_ds_ram": str(ds_dir / f"ds-{name}-ram.bin"),
        }, indent=2) + "\n")

    compare = [sys.executable, str(ROOT / "tools/compare_castle_captures.py")]
    for name in args.views:
        compare += ["--pair", name, str(ds_dir / f"ds-{name}.png"), str(out / f"{name}.png")]
    run(compare + ["--output", str(out / "comparisons.png")])
    print(out / "comparisons.png")


if __name__ == "__main__":
    main()
