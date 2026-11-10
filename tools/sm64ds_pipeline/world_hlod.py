"""Static DS BMD -> LibSaturn's canonical SourceModel -> WLH1.

This adapter owns *only* Nintendo BMD-specific material/corner conversion.
Spatial clipping, QEM, quality validation and WLH1 serialization remain in
LibSaturn's tools/model_pipeline/world_hlod.py; no simplifier is duplicated.

ROM and generated WLH1/materials are private outputs and must not be committed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import sys

from .bmd import Model
from .common import FormatError


@dataclass
class StaticSource:
    """Plain, dependency-free source IR for local audit and host unit tests."""
    vertices: list[tuple[float, float, float]]
    uvs: list[tuple[float, float]]
    triangles: list[tuple[int, int, int]]
    tri_materials: list[int]
    materials: list[dict]
    textures: list[dict]
    report: dict


def static_source(model: Model) -> StaticSource:
    """Expand per-corner DS UVs without welding across seams/materials.

    DS triangle faces repeat the last VDP1 corner; four distinct corners form
    a quad, which is split on the (0,2) diagonal with original winding.
    Zero-area source triangles are skipped *and counted* (no useful surface is
    removed). Model transforms other than the verified rigid identity root
    are rejected, never silently erased.
    """
    if (len(model.bones) != 1 or model.weighted_count or model.weighted):
        raise FormatError('world HLOD currently needs a single rigid static root')
    root = model.bones[0]
    if (root.idx, root.parent, root.trans, root.scale, root.angles) != (
            0, -1, (0, 0, 0), (4096, 4096, 4096), (0, 0, 0)):
        raise FormatError('non-identity static root requires dedicated transform baking')
    if any(v.joint != 0 for v in model.vertices):
        raise FormatError('world HLOD cannot silently discard a vertex joint')
    if len(model.face_uvs) != len(model.faces) or len(model.face_materials) != len(model.faces):
        raise FormatError('BMD face/UV/material arrays are inconsistent')
    if len(model.material_textures) != model.material_count:
        raise FormatError('BMD material texture records are incomplete')
    if model.scale_shift < 0 or model.scale_shift > 13:
        raise FormatError('unsupported BMD static scale')

    # DS raw positions are signed 4.12 before scaleShift. The stored HLOD
    # positions are game-world units, not camera-centered skybox coordinates.
    factor = (1 << model.scale_shift) / 4096.0
    result_vertices: list[tuple[float, float, float]] = []
    result_uvs: list[tuple[float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    tri_materials: list[int] = []
    corner_ids: dict[tuple[int, int, tuple[float, float]], int] = {}
    skipped: list[dict] = []
    source_quads = 0
    textures: list[dict] = []
    texture_by_identity: dict[int, int] = {}
    materials: list[dict] = []
    for mid, source_tex in enumerate(model.material_textures):
        entry: dict = {'name': f'bmd_material_{mid:04d}'}
        if source_tex is not None:
            key = id(source_tex)
            if key not in texture_by_identity:
                raw = bytes(c for pixel in source_tex.pixels for c in pixel)
                texture_by_identity[key] = len(textures)
                textures.append({
                    'width': source_tex.width,
                    'height': source_tex.height,
                    'pixels_rgba': list(source_tex.pixels),
                    'sha256': hashlib.sha256(raw).hexdigest(),
                    'repeat_s': source_tex.repeat_s,
                    'repeat_t': source_tex.repeat_t,
                    'flip_s': source_tex.flip_s,
                    'flip_t': source_tex.flip_t,
                })
            entry['texture_index'] = texture_by_identity[key]
            entry['palette_entries'] = 256
        materials.append(entry)

    def corner_index(vertex_id: int, material: int, uv: tuple[float, float]) -> int:
        if vertex_id < 0 or vertex_id >= len(model.vertices):
            raise FormatError('BMD face contains an invalid vertex index')
        if len(uv) != 2 or not all(math.isfinite(float(v)) for v in uv):
            raise FormatError('BMD face contains invalid UV coordinates')
        key = (vertex_id, material, tuple(float(v) for v in uv))
        if key not in corner_ids:
            v = model.vertices[vertex_id]
            xyz = tuple(raw * factor for raw in (v.x, v.y, v.z))
            if not all(math.isfinite(p) and abs(p) < 32768 for p in xyz):
                raise FormatError('BMD world coordinate outside Saturn signed 16.16')
            corner_ids[key] = len(result_vertices)
            result_vertices.append(xyz)
            result_uvs.append(key[2])
        return corner_ids[key]

    for face_index, (face, uvs, material) in enumerate(zip(
            model.faces, model.face_uvs, model.face_materials)):
        if len(face) != 4 or len(uvs) != 4 or not 0 <= material < model.material_count:
            raise FormatError(f'BMD face {face_index} is malformed')
        is_triangle = face[2] == face[3]
        if not is_triangle:
            source_quads += 1
        face_tris = ((0, 1, 2),) if is_triangle else ((0, 1, 2), (0, 2, 3))
        for local_tri in face_tris:
            p = [model.vertices[face[c]] for c in local_tri]
            e1 = (p[1].x-p[0].x, p[1].y-p[0].y, p[1].z-p[0].z)
            e2 = (p[2].x-p[0].x, p[2].y-p[0].y, p[2].z-p[0].z)
            cross = (e1[1]*e2[2]-e1[2]*e2[1],
                     e1[2]*e2[0]-e1[0]*e2[2],
                     e1[0]*e2[1]-e1[1]*e2[0])
            if sum(x*x for x in cross) == 0:
                skipped.append({'face': face_index, 'corners': list(local_tri),
                                'reason': 'zero-area triangle'})
                continue
            tri = tuple(corner_index(face[c], material, uvs[c]) for c in local_tri)
            triangles.append(tri)
            tri_materials.append(material)
    if not triangles:
        raise FormatError('no nondegenerate world geometry found')
    bounds = [[min(v[axis] for v in result_vertices),
               max(v[axis] for v in result_vertices)] for axis in range(3)]
    report = {
        'source_faces': len(model.faces),
        'source_quads': source_quads,
        'source_triangles_after_triangulation': len(model.faces)+source_quads,
        'output_triangles': len(triangles),
        'zero_area_removed': len(skipped),
        'zero_area_details': skipped,
        'output_vertices_with_uv_seams': len(result_vertices),
        'source_vertices': len(model.vertices),
        'material_count': len(materials),
        'unique_textures': len(textures),
        'scale_shift': model.scale_shift,
        'world_bounds_xyz': bounds,
        'notes': [
            'BMD static root is identity; per-corner UV and material indices preserved',
            'Texture bytes are referenced as private metadata; WLH1 itself does not embed texels',
            'KCL and gameplay collision are not simplified',
        ],
    }
    return StaticSource(result_vertices, result_uvs, triangles,
                        tri_materials, materials, textures, report)


def _require_libsaturn_source(path: Path):
    path = path.expanduser().resolve()
    module = path / 'tools' / 'model_pipeline' / 'world_hlod.py'
    if not module.is_file():
        raise FormatError(
            f'LibSaturn host pipeline not found at {module}; '
            'provide --libsaturn-source to its checked-out source tree')
    # Load the LibSaturn implementation from a caller-chosen local tree. This
    # intentionally avoids copying/pinning an outdated second QEM algorithm.
    sys.path.insert(0, str(path / 'tools'))
    from model_pipeline.model import SourceModel, SourceTexture
    from model_pipeline.world_hlod import build_package, LodTarget
    return SourceModel, SourceTexture, build_package, LodTarget


def build_world_hlod(model: Model, libsaturn_source: Path, *,
                     cell_size: float = 8.0,
                     lod_targets: tuple[int, ...] = (160, 64, 24),
                     quality: str = 'aggressive',
                     silhouette_views: int = 12) -> tuple[bytes, dict]:
    """Use LibSaturn's verified HLOD compressor, without duplicating QEM.

    Raises on any failed HLOD quality gate. The WLH1 payload is only the
    original source's *geometry/UV/material IDs*; collision and texels need
    their independent pipelines before runtime gameplay integration.
    """
    source = static_source(model)
    if not math.isfinite(cell_size) or cell_size <= 0:
        raise FormatError('world HLOD cell size must be positive and finite')
    if not 1 <= len(lod_targets) <= 4 or any(n < 1 for n in lod_targets) or any(
            lod_targets[i] < lod_targets[i + 1] for i in range(len(lod_targets)-1)):
        raise FormatError('world HLOD targets must be 1..4 positive, non-increasing counts')
    SourceModel, SourceTexture, build_package, LodTarget = _require_libsaturn_source(
        Path(libsaturn_source))
    canonical = SourceModel(
        vertices=source.vertices,
        uvs=source.uvs,
        triangles=source.triangles,
        tri_materials=source.tri_materials,
        materials=source.materials,
        textures=[SourceTexture(t['width'], t['height'], t['pixels_rgba'])
                  for t in source.textures],
    )
    archive, report = build_package(
        canonical,
        cell_size=cell_size,
        lod_targets=tuple(LodTarget(f'lod{i}', faces) for i, faces in enumerate(lod_targets)),
        quality=quality,
        silhouette_views=silhouette_views,
    )
    report['sm64ds_source'] = source.report
    report['required_next_steps'] = [
        'Bind WLH1 material IDs to VDP1 textures; bake UVs after splitting and simplify as needed',
        'Connect decoded HLOD mesh cells to sat_world_lod3d_plan and sat_scene_t',
        'Keep original KCL for collision; test physical world scale and alignment',
        'Verify Saturn image parity, memory residency and real scene command budget',
    ]
    return archive, report


def materials_manifest(model: Model) -> dict:
    """Private metadata only. No copied Nintendo pixels in public source."""
    s = static_source(model)
    return {
        'materials': s.materials,
        'textures': [{k: v for k, v in t.items() if k != 'pixels_rgba'}
                     for t in s.textures],
        'source': s.report,
    }
