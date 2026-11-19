"""Adapter to LibSaturn's position/UV plane splitter for static BMD faces."""
from pathlib import Path
import math
import sys
from .common import FormatError


def _is_planar_quad(pos):
    """True if 4-point quad is coplanar within a small geometric tolerance."""
    p0, p1, p2, p3 = pos
    e1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    e2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
    nx = e1[1] * e2[2] - e1[2] * e2[1]
    ny = e1[2] * e2[0] - e1[0] * e2[2]
    nz = e1[0] * e2[1] - e1[1] * e2[0]
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 1e-9:
        return False
    d = abs(((p3[0] - p0[0]) * nx + (p3[1] - p0[1]) * ny + (p3[2] - p0[2]) * nz) / length)
    return d <= 0.05


def _max_edge_length(pos, is_tri):
    pts = pos[:3] if is_tri else pos
    n = len(pts)
    return max(
        math.sqrt(sum((pts[i][k] - pts[(i + 1) % n][k]) ** 2 for k in range(3)))
        for i in range(n)
    )


def split_nearby(vertices, faces, uvs, materials, sdk, *, center, radius, cell_size,
                 refine_faces=(), refine_cell_size=0, refine_grids=None, refine_axes=None,
                 pack_quads=False, colors=None, max_edge=0, max_edge_radius=0):
    """Split faces near an XZ point on a world-aligned X/Z grid.

    All polygons are split by LibSaturn's canonical plane splitter, retaining
    interpolated UVs, optional vertex colors, and source IDs. Nonplanar quads
    are triangulated first. With pack_quads, pair adjacent fan triangles into
    native VDP1 quads.
    """
    if radius <= 0 or cell_size <= 0:
        raise FormatError('SDK split radius and cell size must be positive')
    refine_faces = set(refine_faces)
    refine_grids = refine_grids or {}
    refine_axes = refine_axes or {}
    if refine_faces and (refine_cell_size <= 0 or any(i < 0 or i >= len(faces) for i in refine_faces)):
        raise FormatError('invalid refinement grid or source face ID')
    if any(i not in refine_faces or grid <= 0 for i, grid in refine_grids.items()):
        raise FormatError('invalid per-face refinement grid')
    if any(i not in refine_faces or not axes or any(a not in 'xyz' for a in axes) or len(set(axes)) != len(axes)
           for i, axes in refine_axes.items()):
        raise FormatError('invalid per-face refinement axes')
    if colors is not None and len(colors) != len(faces):
        raise FormatError('colors length must match faces length')
    tools = Path(sdk).resolve() / 'tools'
    if not (tools / 'model_pipeline' / 'intersections.py').is_file():
        raise FormatError('LibSaturn intersections.py is missing')
    sys.path.insert(0, str(tools))
    from model_pipeline.intersections import Face, split_by_plane
    if pack_quads:
        from model_pipeline.intersections import to_corner_lists
    points = list(vertices)
    intern = {tuple(v): i for i, v in enumerate(points)}
    result = []
    out_uv = []
    out_mat = []
    origins = []
    out_col = [] if colors is not None else None

    def intern_point(p):
        p = tuple(round(x, 8) for x in p)
        if p not in intern:
            intern[p] = len(points)
            points.append(p)
        return intern[p]

    def emit(poly, src, mat):
        corners = poly.corners
        pieces = (to_corner_lists(poly) if pack_quads else
                  ([corners[0], corners[i], corners[i + 1]] for i in range(1, len(corners) - 1)))
        for piece in pieces:
            if len(piece) == 3:
                piece.append(piece[-1])
            result.append(tuple(intern_point(c[0]) for c in piece))
            if colors is not None:
                out_uv.append(tuple((c[1][0], c[1][1]) for c in piece))
                out_col.append(tuple((c[1][2], c[1][3], c[1][4]) for c in piece))
            else:
                out_uv.append(tuple(c[1] for c in piece))
            out_mat.append(mat)
            origins.append(src)

    for src, (face, uv, mat) in enumerate(zip(faces, uvs, materials)):
        pos = [vertices[i] for i in face]
        col = colors[src] if colors is not None else None
        minx, maxx = min(p[0] for p in pos), max(p[0] for p in pos)
        minz, maxz = min(p[2] for p in pos), max(p[2] for p in pos)
        nearby = (minx <= center[0] + radius and maxx >= center[0] - radius and
                  minz <= center[1] + radius and maxz >= center[1] - radius)
        edge_split = False
        if max_edge > 0 and not nearby and src not in refine_faces:
            in_range = True
            if max_edge_radius > 0:
                in_range = (minx <= center[0] + max_edge_radius and maxx >= center[0] - max_edge_radius and
                            minz <= center[1] + max_edge_radius and maxz >= center[1] - max_edge_radius)
            if in_range and _max_edge_length(pos, face[2] == face[3]) > max_edge:
                edge_split = True
        if not nearby and src not in refine_faces and not edge_split:
            result.append(face)
            out_uv.append(uv)
            out_mat.append(mat)
            origins.append(src)
            if out_col is not None:
                out_col.append(col)
            continue
        if src in refine_faces:
            grid = refine_grids.get(src, refine_cell_size)
            axes = refine_axes.get(src, 'xz')
        elif nearby:
            grid = cell_size
            axes = 'xz'
        else:
            grid = max_edge
            dy = max(p[1] for p in pos) - min(p[1] for p in pos)
            axes = 'xyz' if dy > grid else 'xz'

        if face[2] == face[3]:
            polys = [(0, 1, 2)]
        elif _is_planar_quad(pos):
            polys = [(0, 1, 2, 3)]
        else:
            polys = [(0, 1, 2), (0, 2, 3)]

        for corner_ids in polys:
            if colors is not None:
                corners = [(pos[k], (uv[k][0], uv[k][1], float(col[k][0]), float(col[k][1]), float(col[k][2])))
                           for k in corner_ids]
            else:
                corners = [(pos[k], uv[k]) for k in corner_ids]
            pieces = [Face(corners, src)]
            for axis in ('xyz'.index(a) for a in axes):
                lo = min(p[axis] for p in pos)
                hi = max(p[axis] for p in pos)
                for n in range(math.floor(lo / grid) + 1, math.ceil(hi / grid)):
                    normal = tuple(1.0 if i == axis else 0.0 for i in range(3))
                    plane = (normal, n * grid, grid)
                    next_pieces = []
                    for piece in pieces:
                        front, back = split_by_plane(piece, plane)
                        next_pieces.extend(p for p in (front, back) if p is not None)
                    pieces = next_pieces
            for piece in pieces:
                emit(piece, src, mat)

    if out_col is not None:
        return points, result, out_uv, out_mat, origins, out_col
    return points, result, out_uv, out_mat, origins
