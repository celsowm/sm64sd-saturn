"""Merge coplanar, UV/color-consistent triangle pairs into native VDP1 quads."""
from __future__ import annotations
from collections import defaultdict
import math


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(a):
    return math.sqrt(_dot(a, a))


def _uv_cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _is_uv_quad_clean(uv0, uv1, uv2, uv3):
    """Check that the quad UV polygon is non-folded and matches both triangles."""
    u1 = _uv_cross(uv0, uv1, uv3)
    u2 = _uv_cross(uv2, uv3, uv1)
    if u1 * u2 < -1e-6:
        return False
    # Also check opposite diagonal winding so the UV quad itself is convex/degenerate.
    u3 = _uv_cross(uv1, uv2, uv0)
    u4 = _uv_cross(uv3, uv0, uv2)
    if u3 * u4 < -1e-6:
        return False
    return True


def merge_coplanar_quads(vertices, faces, uvs, materials, *, colors=None,
                         origins=None, min_dot=0.998, max_plane_dist=0.25,
                         rel_plane_dist=0.005):
    """Pair coplanar triangles with consistent UVs and colors into native quads.

    Returns (faces, uvs, materials, colors, origins, source_sets) where
    source_sets[i] is the tuple of original input face indices merged into face i.
    """
    n_faces = len(faces)
    if origins is None:
        origins = list(range(n_faces))
    if colors is None:
        colors = [((31, 31, 31),) * 4 for _ in range(n_faces)]

    edge_map = defaultdict(list)
    for fi, f in enumerate(faces):
        if f[2] != f[3]:
            continue
        tri = (f[0], f[1], f[2])
        if len(set(tri)) != 3:
            continue
        for k in range(3):
            u, v = tri[k], tri[(k + 1) % 3]
            opp = tri[(k + 2) % 3]
            edge_map[(min(u, v), max(u, v))].append((fi, (u, v), opp))

    candidates = []
    for (u, v), entries in edge_map.items():
        if len(entries) != 2:
            continue
        (f1, e1, a1), (f2, e2, a2) = entries
        if materials[f1] != materials[f2]:
            continue
        if e1[0] != e2[1] or e1[1] != e2[0] or a1 == a2:
            continue
        if a1 in e1 or a2 in e1:
            continue

        def corner_map(fi):
            f = faces[fi]
            uv = uvs[fi]
            col = colors[fi]
            return {f[k]: (uv[k], col[k]) for k in range(3)}

        c1 = corner_map(f1)
        c2 = corner_map(f2)
        match = True
        for sv in e1:
            uv_a, col_a = c1[sv]
            uv_b, col_b = c2[sv]
            if abs(uv_a[0] - uv_b[0]) > 1e-3 or abs(uv_a[1] - uv_b[1]) > 1e-3:
                match = False
                break
            if any(abs(col_a[k] - col_b[k]) > 0.5 for k in range(3)):
                match = False
                break
        if not match:
            continue

        p_a1, p_e0, p_e1, p_a2 = vertices[a1], vertices[e1[0]], vertices[e1[1]], vertices[a2]
        cr1 = _cross(_sub(p_e0, p_a1), _sub(p_e1, p_a1))
        cr2 = _cross(_sub(p_e1, p_a2), _sub(p_e0, p_a2))
        l1, l2 = _length(cr1), _length(cr2)
        if l1 <= 1e-9 or l2 <= 1e-9:
            continue
        n1 = (cr1[0] / l1, cr1[1] / l1, cr1[2] / l1)
        n2 = (cr2[0] / l2, cr2[1] / l2, cr2[2] / l2)
        if _dot(n1, n2) < min_dot:
            continue
        diag_len = _length(_sub(p_e1, p_e0))
        if diag_len <= 1e-9:
            continue
        if abs(_dot(_sub(p_a2, p_a1), n1)) > max(max_plane_dist, rel_plane_dist * diag_len):
            continue

        # Strict convexity check for quad (a1, e1[0], a2, e1[1]) preserving normal n1.
        quad_pts = (p_a1, p_e0, p_a2, p_e1)
        area_scale = l1 + l2
        convex = True
        for k in range(4):
            q0, q1, q2 = quad_pts[k], quad_pts[(k + 1) % 4], quad_pts[(k + 2) % 4]
            if _dot(_cross(_sub(q1, q0), _sub(q2, q1)), n1) <= 1e-4 * area_scale:
                convex = False
                break
        if not convex:
            continue

        uv_a1, col_a1 = c1[a1]
        uv_e0, col_e0 = c1[e1[0]]
        uv_e1, col_e1 = c1[e1[1]]
        uv_a2, col_a2 = c2[a2]
        if not _is_uv_quad_clean(uv_a1, uv_e0, uv_a2, uv_e1):
            continue

        # Score: prefer more rectangular/symmetric quads (low skew, longer diagonal).
        mid_diag = tuple(0.5 * (p_e0[k] + p_e1[k]) for k in range(3))
        mid_opp = tuple(0.5 * (p_a1[k] + p_a2[k]) for k in range(3))
        skew = _length(_sub(mid_diag, mid_opp)) / diag_len
        if skew > 0.45:
            continue

        quad_face = (a1, e1[0], a2, e1[1])
        quad_uv = (uv_a1, uv_e0, uv_a2, uv_e1)
        quad_col = (col_a1, col_e0, col_a2, col_e1)
        # Prefer low skew (true rectangles/trapezoids) and longer shared diagonal.
        candidates.append((round(skew, 3), -diag_len, min(f1, f2), max(f1, f2), f1, f2, quad_face, quad_uv, quad_col))

    candidates.sort()
    merged_partner = {}
    merged_data = {}
    used = set()
    for _, _, _, _, f1, f2, qf, quv, qcol in candidates:
        if f1 in used or f2 in used:
            continue
        used.add(f1)
        used.add(f2)
        keep, drop = (f1, f2) if f1 < f2 else (f2, f1)
        merged_partner[drop] = keep
        merged_data[keep] = (qf, quv, qcol, (origins[f1], origins[f2]), materials[f1])

    out_faces = []
    out_uvs = []
    out_mats = []
    out_cols = []
    out_origins = []
    out_sources = []
    for fi in range(n_faces):
        if fi in merged_partner:
            continue
        if fi in merged_data:
            qf, quv, qcol, srcs, mat = merged_data[fi]
            out_faces.append(qf)
            out_uvs.append(quv)
            out_mats.append(mat)
            out_cols.append(qcol)
            out_origins.append(srcs[0])
            out_sources.append(srcs)
        else:
            out_faces.append(faces[fi])
            out_uvs.append(uvs[fi])
            out_mats.append(materials[fi])
            out_cols.append(colors[fi])
            out_origins.append(origins[fi])
            out_sources.append((origins[fi],))
    return out_faces, out_uvs, out_mats, out_cols, out_origins, out_sources
