"""Bounded SM64DS KCL prism decode; independent of render LOD geometry.

Positions are stored at 1/64 DS unit, normals at 1/1024. The prism
directory offset includes the 16-byte dummy entry (which overlaps the end
of the normal table). Rendering uses 1/1000 DS units. See upstream
include/dBgW_Kc.h and the line-query implementation for these conventions.
"""
from dataclasses import dataclass
import math
import struct
from .common import FormatError
from .compression import lz77


def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


@dataclass(frozen=True)
class Prism:
    vertices: tuple
    normal: tuple
    edges: tuple
    extent: float
    attribute: int


def decode_kcl(blob: bytes, world_scale: float = 64.0) -> list[Prism]:
    data = lz77(blob)
    if len(data) < 56 or not math.isfinite(world_scale) or world_scale <= 0:
        raise FormatError('invalid KCL header/scale')
    p, n, t, end = struct.unpack_from('<4I', data)
    start = t + 16
    if not (56 <= p <= n <= start < end <= len(data)) or (n-p)%12 or (start-n)%6 or (end-start)%16:
        raise FormatError('invalid KCL table ranges')
    factor = world_scale / 64000
    points = [tuple(v*factor for v in row) for row in struct.iter_unpack('<3i', data[p:n])]
    normals = [tuple(v/1024 for v in row) for row in struct.iter_unpack('<3h', data[n:start])]
    result = []
    for at in range(start, end, 16):
        length, pi, ni, e1, e2, e3, attribute = struct.unpack_from('<i6H', data, at)
        if pi >= len(points) or max(ni,e1,e2,e3) >= len(normals) or length <= 0:
            raise FormatError(f'invalid KCL prism at {at}')
        a, normal = points[pi], normals[ni]
        edges = tuple(normals[i] for i in (e1,e2,e3))
        extent = length * factor / 1024
        d1, d2 = cross(edges[0], normal), cross(normal, edges[1])
        den1, den2 = dot(d1, edges[2]), dot(d2, edges[2])
        if min(abs(den1),abs(den2)) < 1e-8:
            raise FormatError(f'degenerate KCL prism at {at}')
        b = tuple(a[i] + d1[i]*extent/den1 for i in range(3))
        c = tuple(a[i] + d2[i]*extent/den2 for i in range(3))
        if dot(cross(tuple(b[i]-a[i] for i in range(3)),tuple(c[i]-a[i] for i in range(3))),normal) < 0:
            b,c = c,b
        if any(not math.isfinite(v) or abs(v)>=32768 for point in (a,b,c) for v in point):
            raise FormatError('KCL vertex exceeds fixed-point world')
        result.append(Prism((a,b,c),normal,edges,extent,attribute))
    if not result or len(result)>65535:
        raise FormatError('KCL prism count exceeds runtime capacity')
    return result
