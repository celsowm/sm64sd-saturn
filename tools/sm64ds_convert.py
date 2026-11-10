#!/usr/bin/env python3
"""Local-only SM64DS ASME -> LibSaturn experimental rigid-skin converter.

Supports NitroFS / NARC / Nintendo LZ77, BMD GX vertex streams and BCA sampled
bone poses. Output is intentionally **flat-color** C source: BMD textures, UV
baking, weighted transforms and complete game parity remain separate gates.
No Nintendo asset bytes are included in this source repository.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import struct

MAX_OUTPUT = 16 * 1024 * 1024


class FormatError(ValueError):
    """Input cannot be safely or faithfully converted."""


def field(data: bytes, at: int, fmt: str):
    n = struct.calcsize(fmt)
    if at < 0 or at + n > len(data):
        raise FormatError(f"truncated buffer at 0x{at:x}, requires {n} bytes")
    return struct.unpack_from("<" + fmt, data, at)[0] if len(fmt) == 1 else struct.unpack_from("<" + fmt, data, at)


def region(data: bytes, offset: int, size: int) -> bytes:
    if size < 0 or offset < 0 or offset + size > len(data):
        raise FormatError(f"invalid span 0x{offset:x}+{size} in {len(data)} bytes")
    return data[offset:offset + size]


def lz77(data: bytes) -> bytes:
    """Strict SM64DS LZ77-wrapped LZ10 decoder; raw payloads pass through."""
    if data[:4] == b"LZ77":
        data = data[4:]
    else:
        return data  # Decompressed BCA data may itself begin with 0x10.
    if len(data) < 4 or data[0] != 0x10:
        raise FormatError("bad LZ10 header")
    total = int.from_bytes(data[1:4], 'little')
    if total == 0 or total > MAX_OUTPUT:
        raise FormatError(f"unsafe decompressed length: {total}")
    result = bytearray()
    pos = 4
    while len(result) < total:
        if pos >= len(data):
            raise FormatError("truncated LZ10 flag byte")
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if len(result) >= total:
                break
            if flags & (0x80 >> bit):
                if pos + 2 > len(data):
                    raise FormatError("truncated LZ10 back-reference")
                a, b = data[pos], data[pos + 1]
                pos += 2
                size = (a >> 4) + 3
                distance = (((a & 15) << 8) | b) + 1
                if distance > len(result) or len(result) + size > total:
                    raise FormatError("invalid LZ10 distance or output overrun")
                for _ in range(size):
                    result.append(result[-distance])
            else:
                if pos >= len(data):
                    raise FormatError("truncated LZ10 literal")
                result.append(data[pos])
                pos += 1
    return bytes(result)


def fnt_names(fnt: bytes) -> dict[int, str]:
    """Nintendo FNT directory walker, shared by ROM and NARC."""
    if len(fnt) < 8:
        raise FormatError("missing FNT root directory")
    directory_count = field(fnt, 6, 'H')
    if not 1 <= directory_count <= 4096 or 8 * directory_count > len(fnt):
        raise FormatError("invalid FNT directory count")
    dirs = {}
    for i in range(directory_count):
        dirs[0xF000 + i] = field(fnt, i * 8, 'IHH')
    result: dict[int, str] = {}
    active: set[int] = set()

    def walk(directory: int, prefix: str):
        if directory not in dirs or directory in active:
            raise FormatError("unknown or cyclic FNT directory")
        active.add(directory)
        pos, file_id, _parent = dirs[directory]
        if pos >= len(fnt):
            raise FormatError("FNT directory offset outside table")
        for _ in range(len(fnt)):
            if pos >= len(fnt):
                raise FormatError("unterminated FNT directory")
            n = fnt[pos]
            pos += 1
            if n == 0:
                active.remove(directory)
                return
            size = n & 0x7f
            if size == 0:
                raise FormatError("empty FNT name")
            name = region(fnt, pos, size).decode('latin1')
            pos += size
            if n & 0x80:
                child = field(fnt, pos, 'H')
                pos += 2
                walk(child, prefix + name + '/')
            else:
                if file_id in result:
                    raise FormatError("duplicate FNT file ID")
                result[file_id] = prefix + name
                file_id += 1
        raise FormatError("unterminated FNT directory")

    walk(0xF000, '')
    return result


class Filesystem:
    def __init__(self, blob: bytes):
        if len(blob) < 0x60 or blob[12:16] != b'ASME' or blob[30] != 0:
            raise FormatError("only USA ASME revision 0 has been verified")
        fnt_off, fnt_len, fat_off, fat_len = field(blob, 0x40, 'IIII')
        if fat_len % 8:
            raise FormatError("invalid FAT length")
        self.blob = blob
        self.names = fnt_names(region(blob, fnt_off, fnt_len))
        self.by_name = {p: i for i, p in self.names.items()}
        if len(self.by_name) != len(self.names):
            raise FormatError("duplicate NitroFS path")
        self.fat = [field(blob, fat_off + 8 * i, 'II') for i in range(fat_len // 8)]
        for start, end in self.fat:
            if start > end or end > len(blob):
                raise FormatError("invalid FAT file bounds")
        self.sha256 = hashlib.sha256(blob).hexdigest()

    @classmethod
    def from_file(cls, path: Path):
        return cls(path.read_bytes())

    def read_id(self, file_id: int) -> bytes:
        if file_id < 0 or file_id >= len(self.fat):
            raise FormatError(f"NitroFS ID out of range: {file_id}")
        a, b = self.fat[file_id]
        return self.blob[a:b]

    def read(self, selector: str) -> bytes:
        """'NitroFS/path' or 'ARCHIVE/arc0.narc:131' or ':nested/path'."""
        outer, colon, inner = selector.partition(':')
        if outer not in self.by_name:
            raise FormatError(f"NitroFS path not found: {outer}")
        data = self.read_id(self.by_name[outer])
        if colon:
            archive = Narc(data)
            data = archive.read(int(inner) if inner.isdecimal() else inner)
        return lz77(data)


class Narc:
    def __init__(self, blob: bytes):
        if len(blob) < 16 or blob[:4] != b'NARC' or field(blob, 8, 'I') != len(blob):
            raise FormatError("invalid NARC header")
        self.blob = blob
        blocks = {}
        pos = field(blob, 12, 'H')  # NARC header length (0x10)
        count = field(blob, 14, 'H')
        if pos < 16 or not 2 <= count <= 8:
            raise FormatError("invalid NARC block count/header")
        for _ in range(count):
            tag = region(blob, pos, 4)
            size = field(blob, pos + 4, 'I')
            if size < 8 or tag in blocks:
                raise FormatError("invalid NARC block")
            blocks[tag] = (pos, size)
            region(blob, pos, size)
            pos += size
        if pos != len(blob) or not all(k in blocks for k in (b'BTAF', b'BTNF', b'GMIF')):
            raise FormatError("missing NARC section or trailing data")
        fat_off, fat_size = blocks[b'BTAF']
        self.count = field(blob, fat_off + 8, 'I')
        if self.count > 65535 or fat_size < 12 + self.count * 8:
            raise FormatError("invalid NARC FAT")
        self.items = [field(blob, fat_off + 12 + 8 * i, 'II') for i in range(self.count)]
        fnt_off, fnt_size = blocks[b'BTNF']
        self.names = fnt_names(region(blob, fnt_off + 8, fnt_size - 8))
        self.name_ids = {p: i for i, p in self.names.items()}
        dat_off, dat_size = blocks[b'GMIF']
        self.data = region(blob, dat_off + 8, dat_size - 8)
        for a, b in self.items:
            if a > b or b > len(self.data):
                raise FormatError("invalid NARC internal FAT")

    def read(self, entry: int | str) -> bytes:
        if isinstance(entry, str):
            if entry not in self.name_ids:
                raise FormatError(f"NARC path not found: {entry}")
            entry = self.name_ids[entry]
        if not 0 <= entry < self.count:
            raise FormatError("NARC ID outside FAT")
        a, b = self.items[entry]
        return self.data[a:b]


def signed10(n: int) -> int:
    n &= 1023
    return n - 1024 if n & 512 else n


def signed16(n: int) -> int:
    n &= 65535
    return n - 65536 if n & 32768 else n


@dataclass(frozen=True)
class Bone:
    idx: int
    parent: int
    trans: tuple[int, int, int]
    scale: tuple[int, int, int]
    angles: tuple[int, int, int]


@dataclass(frozen=True)
class Vertex:
    x: int
    y: int
    z: int
    joint: int


@dataclass
class Model:
    bones: list[Bone]
    vertices: list[Vertex]
    faces: list[tuple[int, int, int, int]]
    scale_shift: int
    material_count: int
    texture_count: int
    weighted_count: int
    gx_commands: dict[str, int]


def gx_params(cmd: int) -> int:
    if cmd in (0, 0x11, 0x15, 0x41):
        return 0
    if cmd in (0x16, 0x18):
        return 16
    if cmd in (0x17, 0x19):
        return 12
    if cmd == 0x1a:
        return 9
    if cmd in (0x1b, 0x1c, 0x70):
        return 3
    if cmd in (0x23, 0x71):
        return 2
    if cmd == 0x34:
        return 32
    return 1


# For this converter a DS display list is *not* a free-standing rendering
# program. Reject matrix mutation and unfamiliar opcodes rather than silently
# losing animations or changing vertex locations.
ALLOWED_GX = {0, 0x14, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
              0x27, 0x28, 0x40, 0x41}


def convert_bmd(blob: bytes) -> Model:
    data = lz77(blob)
    if len(data) < 0x38:
        raise FormatError("truncated BMD")
    shift = data[0]
    nb = field(data, 4, 'I')
    weighted = field(data, 0x30, 'I')
    if not 1 <= nb <= 255 or shift > 12:
        raise FormatError("BMD bone count or scaleShift unsupported")
    if weighted:
        raise FormatError("weighted BMD matrices are not supported by rigid importer")
    bones_at = field(data, 8, 'I')
    bones = []
    for i in range(nb):
        at = bones_at + 0x40 * i
        region(data, at, 0x40)
        bone_id, parent_delta = field(data, at, 'h'), field(data, at + 8, 'h')
        if bone_id != i:
            raise FormatError(f"BMD record vs bone ID mismatch at {i}: {bone_id}")
        parent = i + parent_delta
        if parent == i:
            parent = -1
        if parent >= i or parent < -1:
            raise FormatError(f"non-parent-first hierarchy at bone {i}")
        bones.append(Bone(i, parent, field(data, at + 0x24, 'iii'),
                          field(data, at + 0x10, 'iii'),
                          field(data, at + 0x1c, 'HHH')))
    map_offset = field(data, 0x2c, 'I')
    if map_offset == 0:
        raise FormatError("missing BMD transformBoneMap")
    group_count, groups_at = field(data, 0x0c, 'II')
    if not 1 <= group_count <= 1024:
        raise FormatError("invalid BMD display groups")
    verts: list[Vertex] = []
    face_indices: list[tuple[int, int, int, int]] = []
    intern: dict[Vertex, int] = {}
    hist = Counter()

    def index(x: int, y: int, z: int, slot: int) -> int:
        # map[] is not the same thing as the BMD bone records themselves.
        bone = field(data, map_offset + 2 * slot, 'H')
        if bone >= nb:
            raise FormatError(f"unsupported matrix slot {slot}, maps to {bone}")
        vertex = Vertex(x, y, z, bone)
        if vertex not in intern:
            if len(verts) >= 65535:
                raise FormatError("model has >65535 unique rigid vertices")
            intern[vertex] = len(verts)
            verts.append(vertex)
        return intern[vertex]

    def emit_triangle(a: int, b: int, c: int):
        # LibSaturn generated glTF triangle convention: A,C,B,B.
        face_indices.append((a, c, b, b))

    for group in range(group_count):
        group_at = groups_at + group * 8
        count, lists_at = field(data, group_at, 'II')
        if count > 10000:
            raise FormatError("too many BMD display lists")
        for di in range(count):
            _reserved, _ptr, length, offset = field(data, lists_at + di * 0x10, 'IIII')
            if length % 4:
                raise FormatError("unaligned GX display list")
            stream = region(data, offset, length)
            pos = 0
            primitive = -1
            winding: list[int] = []
            matrix_slot = 0
            vx = vy = vz = 0
            while pos < len(stream):
                command_word = field(stream, pos, 'I')
                pos += 4
                for j in range(4):
                    cmd = (command_word >> (8 * j)) & 255
                    hist[f'{cmd:02x}'] += 1
                    n = gx_params(cmd)
                    words = ((field(stream, pos, 'I'),) if n == 1 else field(stream, pos, 'I' * n)) if n else ()
                    pos += 4 * n
                    if cmd not in ALLOWED_GX:
                        raise FormatError(f"unhandled GX opcode 0x{cmd:02x} (will not silently drop)")
                    if cmd == 0x14:
                        matrix_slot = words[0] & 31
                    elif cmd == 0x40:
                        if primitive >= 0:
                            raise FormatError("nested BEGIN_VTXS")
                        primitive = words[0] & 3
                        winding = []
                    elif cmd == 0x41:
                        if primitive < 0:
                            raise FormatError("END_VTXS without begin")
                        primitive = -1
                        winding = []
                    elif cmd in (0x23, 0x24, 0x25, 0x26, 0x27, 0x28):
                        if cmd == 0x23:
                            vx, vy, vz = signed16(words[0]), signed16(words[0] >> 16), signed16(words[1])
                        elif cmd == 0x24:
                            vx, vy, vz = (signed10(words[0] >> (10 * k)) * 64 for k in range(3))
                        elif cmd == 0x25:
                            vx, vy = signed16(words[0]), signed16(words[0] >> 16)
                        elif cmd == 0x26:
                            vx, vz = signed16(words[0]), signed16(words[0] >> 16)
                        elif cmd == 0x27:
                            vy, vz = signed16(words[0]), signed16(words[0] >> 16)
                        else:
                            vx += signed10(words[0]); vy += signed10(words[0] >> 10); vz += signed10(words[0] >> 20)
                            if not all(-32768 <= x <= 32767 for x in (vx, vy, vz)):
                                raise FormatError("VTX_DIFF coordinate overflow")
                        if primitive < 0:
                            raise FormatError("vertex outside BEGIN/END")
                        w = index(vx, vy, vz, matrix_slot)
                        winding.append(w)
                        nverts = len(winding)
                        if primitive == 0 and nverts == 3:
                            emit_triangle(*winding)
                            winding.clear()
                        elif primitive == 1 and nverts == 4:
                            a, b, c, d = winding
                            face_indices.append((a, d, c, b))
                            winding.clear()
                        elif primitive == 2 and nverts >= 3:
                            a, b, c = winding[-3:]
                            emit_triangle(b, a, c) if ((nverts - 3) & 1) else emit_triangle(a, b, c)
                        elif primitive == 3 and nverts >= 4 and nverts % 2 == 0:
                            a, b, c, d = winding[-4:]
                            face_indices.append((a, c, d, b))
            if primitive >= 0 or pos != len(stream):
                raise FormatError("unfinished GX primitive or stream")
    if not verts or not face_indices or len(face_indices) >= 65536:
        raise FormatError("empty or oversized BMD geometry")
    return Model(bones, verts, face_indices, shift, field(data, 0x24, 'I'),
                 field(data, 0x14, 'I'), weighted, dict(hist))


@dataclass(frozen=True)
class Channel:
    shift: int
    animated: int
    index: int


class Animation:
    def __init__(self, blob: bytes, joints: int):
        data = lz77(blob)
        if len(data) < 0x18:
            raise FormatError("truncated BCA")
        self.data = data
        self.frames = field(data, 2, 'H')
        self.loop = bool(data[4])
        if self.frames < 1 or self.frames > 10000:
            raise FormatError("unsupported animation frame count")
        self.joints = joints
        self.pools = field(data, 8, 'III')
        base = field(data, 0x14, 'I')
        region(data, base, joints * 0x24)
        self.tracks = []
        for joint in range(joints):
            row = [Channel(*field(data, base + joint * 0x24 + i * 4, 'BBH')) for i in range(9)]
            if any(c.shift > 2 or c.animated not in (0, 1) for c in row):
                raise FormatError("unsupported BCA track shift or animation flag")
            self.tracks.append(row)

    def sample_channel(self, joint: int, channel: int, frame: int) -> int:
        if not (0 <= joint < self.joints and 0 <= channel < 9 and 0 <= frame < self.frames):
            raise FormatError("BCA channel/frame outside range")
        ch = self.tracks[joint][channel]
        p = self.pools[0 if channel < 3 else (1 if channel < 6 else 2)]
        is_rotation = 3 <= channel < 6
        kind = 'h' if is_rotation else 'i'
        width = 2 if is_rotation else 4

        def at(n: int):
            return field(self.data, p + (ch.index + n) * width, kind)

        if not ch.animated:
            return at(0)
        if not ch.shift:
            return at(frame)
        base = ((self.frames - 1) >> ch.shift) << ch.shift
        k = frame >> ch.shift
        if frame >= base:
            return at(k + frame - base)
        lo, hi = at(k), at(k + 1)
        rem = frame - (k << ch.shift)
        if rem == 0:
            return lo
        gap = 1 << ch.shift
        if is_rotation and abs(lo - hi) >= 0x800:
            if lo > hi:
                hi += 0x1000
            else:
                lo += 0x1000
            return ((lo * (gap - rem) + hi * rem) >> ch.shift) & 0xfff
        return (lo * (gap - rem) + hi * rem) >> ch.shift

    def sample(self, frame: int):
        out = []
        for joint in range(self.joints):
            scales = tuple(self.sample_channel(joint, k, frame) for k in range(3))
            rotations = tuple(self.sample_channel(joint, k, frame) for k in range(3, 6))
            translation = tuple(self.sample_channel(joint, k, frame) for k in range(6, 9))
            if scales != (4096, 4096, 4096):
                raise FormatError(f"BCA joint {joint} frame {frame} has non-unit scale: {scales}")
            out.append((translation, rotations))
        return out


def checked_fx(raw20_12: int) -> int:
    result = raw20_12 * 16  # 20.12 -> 16.16: never a reinterpret cast.
    if not -(2**31) <= result < 2**31:
        raise FormatError("20.12 -> 16.16 overflow; needs coordinate origin/scale")
    return result


def quaternion(angles: tuple[int, int, int]) -> tuple[int, int, int, int]:
    """Match func_02045178 XYZ Euler row matrix; transpose to LibSaturn basis."""
    ax, ay, az = (2.0 * math.pi * (v & 0xfff) / 4096.0 for v in angles)
    a0, a1 = math.sin(ax), math.cos(ax)
    b0, b1 = math.sin(ay), math.cos(ay)
    c0, c1 = math.sin(az), math.cos(az)
    # Source matrix: row-vector convention, transpose for standard quaternion.
    row = [[b1*c1, b1*c0, -b0],
           [b0*a0*c1 - a1*c0, a1*c1 + b0*a0*c0, b1*a0],
           [a0*c0 + b0*a1*c1, b0*a1*c0 - a0*c1, b1*a1]]
    m = [[row[c][r] for c in range(3)] for r in range(3)]
    trace = sum(m[i][i] for i in range(3))
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = ((m[2][1]-m[1][2])/s, (m[0][2]-m[2][0])/s,
             (m[1][0]-m[0][1])/s, s/4)
    else:
        k = max(range(3), key=lambda i: m[i][i]); j=(k+1)%3; l=(k+2)%3
        s = math.sqrt(1.0 + m[k][k] - m[j][j] - m[l][l]) * 2
        qv = [0.0]*4; qv[k] = s/4
        qv[3] = (m[l][j] - m[j][l]) / s
        qv[j] = (m[k][j] + m[j][k]) / s
        qv[l] = (m[k][l] + m[l][k]) / s
        q = tuple(qv)
    norm = math.sqrt(sum(x*x for x in q))
    return tuple(max(-32767, min(32767, round(x/norm*32767))) for x in q)


def emit_model(model: Model, animations: list[tuple[str, Animation]], name: str,
               rate_num: int = 30, rate_den: int = 1):
    """Return header, C source, manifest for a flat-color rigging diagnostic."""
    if not re.fullmatch('[a-z][a-z0-9_]*', name):
        raise FormatError("output symbol prefix must be C identifier")
    if not (1 <= rate_num <= 32767 and 1 <= rate_den <= 65535):
        raise FormatError("clip sample-rate fields out of LibSaturn bounds")
    if len({key for key, _ in animations}) != len(animations):
        raise FormatError("duplicate clip names")
    if len(model.bones) > 255:
        raise FormatError("skinning joint index >8bit")
    if not animations:
        raise FormatError("at least one animation is required")
    for clip_name, clip in animations:
        if clip.joints != len(model.bones):
            raise FormatError(f"{clip_name}: mismatched bone count")
    def vec(values):
        return '{' + ', '.join(str(int(v)) for v in values) + '}'
    lines = [f'#include "{name}.h"', '',
             '/* This is an UNTEXTURED rig/geometry diagnostic. Call',
             ' * sat_skin_update_mesh() on an actor-owned mesh BEFORE rendering.',
             ' * UV baking, materials, collision and full actor parity are not generated. */', '']
    header = ['#pragma once', '#include <saturn/model3d.h>',
              '#include <saturn/skeleton3d.h>', '#include <saturn/skin3d.h>',
              f'extern const sat_model_asset_t {name}_model;',
              f'extern const sat_skeleton_asset_t {name}_skeleton;',
              f'extern const sat_skin_asset_t {name}_skin;',
              f'extern const sat_skeleton_clip_t {name}_clips[{len(animations)}];', '']
    lines.append(f'static const sat_skeleton_joint_t {name}_joints[{len(model.bones)}] = {{')
    for b in model.bones:
        parent = 'SAT_TRANSFORM3D_ROOT' if b.parent < 0 else str(b.parent)
        lines.append('    {.parent=%s, .rest_translation=%s, .rest_rotation=%s, .rest_scale=%s},' %
                     (parent, vec(checked_fx(t) for t in b.trans), vec(quaternion(b.angles)),
                      vec(checked_fx(s) for s in b.scale)))
    lines += ['};',f'const sat_skeleton_asset_t {name}_skeleton = '
              f'{{.joints={name}_joints, .joint_count={len(model.bones)}}};', '']
    lines.append(f'static const sat_vec3_t {name}_source_vertices[{len(model.vertices)}] = {{')
    for v in model.vertices:
        lines.append('    %s,' % vec((v.x * (1 << (model.scale_shift+4)),
                                     v.y * (1 << (model.scale_shift+4)),
                                     v.z * (1 << (model.scale_shift+4)))))
    lines.append('};')
    lines.append(f'static const sat_skin_rigid_t {name}_anchors[{len(model.vertices)}] = {{')
    for v in model.vertices:
        lines.append(f'    {{{{{v.x}, {v.y}, {v.z}}}, {v.joint}, 0}},')
    lines += ['};', f'const sat_skin_asset_t {name}_skin = {{',
              f'    .rigid={name}_anchors, .rigid_count={len(model.vertices)},',
              f'    .joint_count={len(model.bones)}, .pos_shift={12-model.scale_shift},',
              f'    .max_joint={max(v.joint for v in model.vertices)}', '};', '']
    lines.append(f'static const uint16_t {name}_faces[{len(model.faces)*4}] = {{')
    for face in model.faces:
        lines.append('    ' + ', '.join(map(str,face)) + ',')
    lines += ['};', f'static const uint16_t {name}_face_textures[{len(model.faces)}] = {{']
    lines += ['    ' + ', '.join('SAT_MESH_TEXTURE_NONE' for _ in range(min(len(model.faces)-i,8))) + ','
              for i in range(0,len(model.faces),8)]
    lines += ['};', f'const sat_model_asset_t {name}_model = {{',
              f'    .vertices={name}_source_vertices, .vertex_count={len(model.vertices)},',
              f'    .indices={name}_faces, .face_count={len(model.faces)},',
              f'    .face_texture_indices={name}_face_textures,', '};', '']
    info=[]
    for clip_name, clip in animations:
        if not re.fullmatch('[a-z][a-z0-9_]*',clip_name):
            raise FormatError("clip name must be C identifier")
        lines.append(f'static const sat_skeleton_pose_joint_t {name}_{clip_name}_poses[{clip.frames*clip.joints}] = {{')
        last_q = [None] * clip.joints
        for frame in range(clip.frames):
            pose = clip.sample(frame)
            for j,(trans,angles) in enumerate(pose):
                q = quaternion(angles)
                if last_q[j] and sum(a*b for a,b in zip(q,last_q[j])) < 0:
                    q = tuple(-x for x in q)
                last_q[j] = q
                lines.append('    {%s, %s},' % (vec(checked_fx(t) for t in trans), vec(q)))
        lines += ['};','']
        info.append({'name':clip_name,'frames':clip.frames,'joint_tracks':clip.joints,'loop':clip.loop})
    lines.append(f'const sat_skeleton_clip_t {name}_clips[{len(animations)}] = {{')
    for clip_name,clip in animations:
        lines.append(f'    {{.frames={name}_{clip_name}_poses, .frame_count={clip.frames}, '
                     f'.joint_count={clip.joints}, .rate_num={rate_num}, .rate_den={rate_den}, '
                     f'.flags={"SAT_CLIP_FLAG_LOOP" if clip.loop else "0"}}},')
    lines += ['};','']
    return '\n'.join(header), '\n'.join(lines), {
        'output':name, 'geometry_mode':'flat-color preview; no source textures',
        'pose_rate_assumption':f'{rate_num}/{rate_den} Hz (must be confirmed against original gameplay)',
        'skeleton_joints':len(model.bones), 'rigid_vertices':len(model.vertices),
        'native_quad_commands':len(model.faces),
        'source_materials':model.material_count, 'source_textures':model.texture_count,
        'weighted_source_matrices':model.weighted_count, 'gx_commands':model.gx_commands,
        'clips':info,
        'estimated_arrays_bytes':len(model.vertices)*(12+8)+len(model.faces)*(8+2)
            +sum(c.frames*c.joints*20 for _,c in animations),
        'notes':['ROM-dependent C generated locally only',
                 'source vertices are bone-local; deform before submitting any scene',
                 'source UV and textures intentionally not emitted',
                 'no runtime/hardware validation yet'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True,help='Local USA Rev0 .nds image')
    parser.add_argument('--model',default='ARCHIVE/arc0.narc:131',help='NitroFS path or NARC:index')
    parser.add_argument('--clip',action='append',default=[],help='name=NitroFS/path.bca (repeat)')
    parser.add_argument('--out',type=Path,required=True,help='Private generated-output directory')
    parser.add_argument('--name',default='mario_preview')
    parser.add_argument('--rate-num',type=int,default=30,help='Explicit nominal clip-rate numerator')
    parser.add_argument('--rate-den',type=int,default=1,help='Clip-rate denominator')
    a=parser.parse_args(argv)
    fs=Filesystem.from_file(a.rom)
    model=convert_bmd(fs.read(a.model))
    clips=a.clip or ['idle=data/player/su_wait.bca','walk=data/player/su_walk.bca',
                     'run=data/player/su_run.bca','jump=data/player/su_jump.bca']
    named=[]
    for item in clips:
        key,sep,path=item.partition('=')
        if not sep:
            parser.error('clip must be name=nitrofs/path')
        named.append((key,Animation(fs.read(path),len(model.bones))))
    header,source,report=emit_model(model,named,a.name,a.rate_num,a.rate_den)
    report.update(rom_sha256=fs.sha256, model=a.model, source_clips={x.split("=",1)[0]:x.split("=",1)[1] for x in clips})
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/f'{a.name}.h').write_text(header,encoding='utf8')
    (a.out/f'{a.name}.c').write_text(source,encoding='utf8')
    (a.out/f'{a.name}.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    try:
        main()
    except (FormatError, OSError) as err:
        raise SystemExit(f'asset conversion failed: {err}') from err