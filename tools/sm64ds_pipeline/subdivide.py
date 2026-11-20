"""Split oversized static faces while retaining their UV interpolation."""
from math import ceil, dist


def _lerp_tuple(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _bilerp_tuple(c00, c10, c11, c01, u, v):
    top = _lerp_tuple(c00, c10, u)
    bot = _lerp_tuple(c01, c11, u)
    return _lerp_tuple(top, bot, v)


def split_long_edges(vertices, faces, uvs, materials, max_edge, *, colors=None,
                     high_y=None, high_max_edge=None, low_y=None, low_max_edge=None,
                     play_box=None, outside_max_edge=None, material_max_edges=None):
    """Parametrically split oversized faces along long edges, preserving UVs and vertex colors.

    Quads are split into an exact nu x nv bilinear grid along their own edges so
    diagonal walls and carpets subdivide cleanly into native quads without sliver
    triangles. Triangles bisect their longest edge recursively until all edges
    are <= max_edge. When high_y/high_max_edge or low_y/low_max_edge are given,
    faces wholly above high_y or wholly below low_y use the relaxed threshold so
    distant ceilings, upper towers, and deep moat walls stay compact.
    """
    if max_edge <= 0 or not (len(faces) == len(uvs) == len(materials)):
        raise ValueError('invalid subdivision input')
    if colors is not None and len(colors) != len(faces):
        raise ValueError('colors length must match faces length')
    out_vertices = list(vertices)
    intern = {tuple(round(c, 8) for c in v): i for i, v in enumerate(vertices)}
    out_faces = []
    out_uv = []
    out_material = []
    origins = []
    out_colors = [] if colors is not None else None

    def vertex(v):
        key = tuple(round(c, 8) for c in v)
        if key not in intern:
            intern[key] = len(out_vertices)
            out_vertices.append(key)
        return intern[key]

    def emit(pts, tex, col, mat, origin):
        out_faces.append(tuple(vertex(p) for p in pts))
        out_uv.append(tuple(tex))
        out_material.append(mat)
        origins.append(origin)
        if out_colors is not None:
            out_colors.append(tuple(tuple(round(ch) for ch in c) for c in col))

    def split_tri(pts, tex, col, mat, origin, limit):
        a, b, c = pts
        lab, lbc, lca = dist(a, b), dist(b, c), dist(c, a)
        mx = max(lab, lbc, lca)
        if mx <= limit:
            emit((a, b, c, c), (tex[0], tex[1], tex[2], tex[2]),
                 (col[0], col[1], col[2], col[2]) if col is not None else None,
                 mat, origin)
            return
        if lab == mx:
            mp = _lerp_tuple(a, b, 0.5)
            mu = _lerp_tuple(tex[0], tex[1], 0.5)
            mc = _lerp_tuple(col[0], col[1], 0.5) if col is not None else None
            split_tri((a, mp, c), (tex[0], mu, tex[2]),
                      (col[0], mc, col[2]) if col is not None else None, mat, origin, limit)
            split_tri((mp, b, c), (mu, tex[1], tex[2]),
                      (mc, col[1], col[2]) if col is not None else None, mat, origin, limit)
        elif lbc == mx:
            mp = _lerp_tuple(b, c, 0.5)
            mu = _lerp_tuple(tex[1], tex[2], 0.5)
            mc = _lerp_tuple(col[1], col[2], 0.5) if col is not None else None
            split_tri((a, b, mp), (tex[0], tex[1], mu),
                      (col[0], col[1], mc) if col is not None else None, mat, origin, limit)
            split_tri((a, mp, c), (tex[0], mu, tex[2]),
                      (col[0], mc, col[2]) if col is not None else None, mat, origin, limit)
        else:
            mp = _lerp_tuple(c, a, 0.5)
            mu = _lerp_tuple(tex[2], tex[0], 0.5)
            mc = _lerp_tuple(col[2], col[0], 0.5) if col is not None else None
            split_tri((a, b, mp), (tex[0], tex[1], mu),
                      (col[0], col[1], mc) if col is not None else None, mat, origin, limit)
            split_tri((mp, b, c), (mu, tex[1], tex[2]),
                      (mc, col[1], col[2]) if col is not None else None, mat, origin, limit)

    for index, (face, uv, mat) in enumerate(zip(faces, uvs, materials)):
        p = [vertices[i] for i in face]
        col = [tuple(float(ch) for ch in c) for c in colors[index]] if colors is not None else None
        limit = max_edge
        if material_max_edges and mat in material_max_edges:
            limit = material_max_edges[mat]
        elif play_box is not None and outside_max_edge is not None:
            pts_u = p[:3] if face[2] == face[3] else p
            cx = sum(q[0] for q in pts_u) / len(pts_u)
            cy = sum(q[1] for q in pts_u) / len(pts_u)
            cz = sum(q[2] for q in pts_u) / len(pts_u)
            x0, x1, y0, y1, z0, z1 = play_box
            if not (x0 <= cx <= x1 and y0 <= cy <= y1 and z0 <= cz <= z1):
                limit = outside_max_edge
        elif high_y is not None and high_max_edge is not None and min(q[1] for q in p) >= high_y:
            limit = high_max_edge
        elif low_y is not None and low_max_edge is not None and max(q[1] for q in p) <= low_y:
            limit = low_max_edge
        if face[2] == face[3]:
            split_tri(p[:3], uv[:3], col[:3] if col is not None else None, mat, index, limit)
        else:
            u_len = max(dist(p[0], p[1]), dist(p[3], p[2]))
            v_len = max(dist(p[1], p[2]), dist(p[0], p[3]))
            nu = max(1, ceil(u_len / limit))
            nv = max(1, ceil(v_len / limit))
            if nu == 1 and nv == 1:
                emit(p, uv, col, mat, index)
                continue
            for iv in range(nv):
                v0, v1 = iv / nv, (iv + 1) / nv
                for iu in range(nu):
                    u0, u1 = iu / nu, (iu + 1) / nu
                    corners = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
                    pts = tuple(_bilerp_tuple(p[0], p[1], p[2], p[3], cu, cv) for cu, cv in corners)
                    tex = tuple(_bilerp_tuple(uv[0], uv[1], uv[2], uv[3], cu, cv) for cu, cv in corners)
                    scol = (tuple(_bilerp_tuple(col[0], col[1], col[2], col[3], cu, cv) for cu, cv in corners)
                            if col is not None else None)
                    emit(pts, tex, scol, mat, index)

    if out_colors is not None:
        return out_vertices, out_faces, out_uv, out_material, origins, out_colors
    return out_vertices, out_faces, out_uv, out_material, origins


def split_large_faces(vertices, faces, uvs, materials, max_edge):
    """One four-way split per oversized triangle/quad, preserving face order.

    Returns new geometry and each piece's source face index. Triangle quads
    use the converter's (A,B,C,C) convention. Input positions and UVs are
    interpolated together so the child bakes cover the same source domain.
    """
    if max_edge <= 0 or not (len(faces)==len(uvs)==len(materials)):
        raise ValueError('invalid subdivision input')
    out_vertices=list(vertices); intern={tuple(v):i for i,v in enumerate(vertices)}
    out_faces=[];out_uv=[];out_material=[];origins=[]
    def vertex(v):
        v=tuple(v)
        if v not in intern:
            intern[v]=len(out_vertices);out_vertices.append(v)
        return intern[v]
    def mid(a,b): return tuple((x+y)/2 for x,y in zip(a,b))
    def emit(corners, tex, mat, origin):
        out_faces.append(tuple(vertex(p) for p in corners));out_uv.append(tuple(tex))
        out_material.append(mat);origins.append(origin)
    for index,(face,uv,mat) in enumerate(zip(faces,uvs,materials)):
        p=[vertices[i] for i in face]; uv=list(uv)
        if max(dist(a,b) for a in p for b in p)<=max_edge:
            emit(p,uv,mat,index);continue
        if face[2]==face[3]:
            a,b,c=p[:3];u,v,w=uv[:3]
            ab,bc,ca=mid(a,b),mid(b,c),mid(c,a)
            uvab,uvbc,uvca=mid(u,v),mid(v,w),mid(w,u)
            for pts,tex in [((a,ab,ca,ca),(u,uvab,uvca,uvca)),
                            ((ab,b,bc,bc),(uvab,v,uvbc,uvbc)),
                            ((ca,bc,c,c),(uvca,uvbc,w,w)),
                            ((ab,bc,ca,ca),(uvab,uvbc,uvca,uvca))]:
                emit(pts,tex,mat,index)
        else:
            a,b,c,d=p;u,v,w,x=uv
            ab,bc,cd,da=mid(a,b),mid(b,c),mid(c,d),mid(d,a)
            uvab,uvbc,uvcd,uvda=mid(u,v),mid(v,w),mid(w,x),mid(x,u)
            center=mid(ab,cd);uvcenter=mid(uvab,uvcd)
            for pts,tex in [((a,ab,center,da),(u,uvab,uvcenter,uvda)),
                            ((ab,b,bc,center),(uvab,v,uvbc,uvcenter)),
                            ((center,bc,c,cd),(uvcenter,uvbc,w,uvcd)),
                            ((da,center,cd,d),(uvda,uvcenter,uvcd,x))]:
                emit(pts,tex,mat,index)
    return out_vertices,out_faces,out_uv,out_material,origins


def _clip_poly_axis(poly, axis, bound, keep_le, eps=1e-5):
    """Clip a convex polygon of (pos, uv, col) tuples to pos[axis] <= bound (or >= bound)."""
    if not poly:
        return []

    def inside(pt):
        v = pt[0][axis]
        return v <= bound + eps if keep_le else v >= bound - eps

    def intersect(a, b):
        va, vb = a[0][axis], b[0][axis]
        denom = vb - va
        t = 0.0 if abs(denom) < 1e-12 else (bound - va) / denom
        t = max(0.0, min(1.0, t))
        pos = _lerp_tuple(a[0], b[0], t)
        uv = _lerp_tuple(a[1], b[1], t)
        col = _lerp_tuple(a[2], b[2], t) if a[2] is not None else None
        return (pos, uv, col)

    out = []
    n = len(poly)
    for i in range(n):
        cur = poly[i]
        nxt = poly[(i + 1) % n]
        ci, ni = inside(cur), inside(nxt)
        if ci:
            out.append(cur)
            if not ni:
                out.append(intersect(cur, nxt))
        elif ni:
            out.append(intersect(cur, nxt))
    # Remove near-duplicate consecutive vertices.
    cleaned = []
    for pt in out:
        if not cleaned or dist(cleaned[-1][0], pt[0]) > 1e-4:
            cleaned.append(pt)
    if len(cleaned) >= 2 and dist(cleaned[0][0], cleaned[-1][0]) <= 1e-4:
        cleaned.pop()
    return cleaned if len(cleaned) >= 3 else []


def _poly_xz_area(poly):
    area = 0.0
    n = len(poly)
    for i in range(n):
        x0, _, z0 = poly[i][0]
        x1, _, z1 = poly[(i + 1) % n][0]
        area += x0 * z1 - x1 * z0
    return abs(area) * 0.5


def cut_faces_against_boxes(vertices, faces, uvs, materials, origins, source_sets,
                            target_materials, boxes, *, colors=None):
    """Subtract axis-aligned XZ occluder boxes (x0, x1, z0, z1, y_top) from ground faces.

    Prevents continuous DS ground triangles passing underneath raised structures
    (such as Castle Grounds hedges) from sorting over the structure walls under
    average-depth Painter's sorting on Saturn. Preserves UVs, vertex colors, and
    exact edge alignment along box boundaries.
    """
    if not boxes or not target_materials:
        return vertices, faces, uvs, materials, origins, source_sets, colors
    out_vertices = list(vertices)
    intern = {tuple(round(c, 8) for c in v): i for i, v in enumerate(vertices)}
    out_faces = []
    out_uvs = []
    out_materials = []
    out_origins = []
    out_source_sets = []
    out_colors = [] if colors is not None else None

    def vertex(v):
        key = tuple(round(c, 8) for c in v)
        if key not in intern:
            intern[key] = len(out_vertices)
            out_vertices.append(key)
        return intern[key]

    def emit_poly(poly, mat, orig, srcs):
        # Pack convex n-gon into quads + optional triangle fan from vertex 0.
        n = len(poly)
        i = 1
        while i + 1 < n:
            if i + 2 < n:
                quad = (poly[0], poly[i], poly[i + 1], poly[i + 2])
                i += 2
            else:
                quad = (poly[0], poly[i], poly[i + 1], poly[i + 1])
                i += 1
            out_faces.append(tuple(vertex(pt[0]) for pt in quad))
            out_uvs.append(tuple(pt[1] for pt in quad))
            out_materials.append(mat)
            out_origins.append(orig)
            out_source_sets.append(srcs)
            if out_colors is not None:
                out_colors.append(tuple(tuple(round(ch) for ch in pt[2]) for pt in quad))

    for idx, (face, uv, mat, orig, srcs) in enumerate(zip(faces, uvs, materials, origins, source_sets)):
        col = colors[idx] if colors is not None else None
        if mat not in target_materials:
            out_faces.append(face)
            out_uvs.append(uv)
            out_materials.append(mat)
            out_origins.append(orig)
            out_source_sets.append(srcs)
            if out_colors is not None:
                out_colors.append(col)
            continue
        k = 3 if face[2] == face[3] else 4
        poly0 = [
            (vertices[face[j]], uv[j], tuple(float(ch) for ch in col[j]) if col is not None else None)
            for j in range(k)
        ]
        pieces = [poly0]
        for x0, x1, z0, z1, y_top in boxes:
            next_pieces = []
            for poly in pieces:
                xs = [pt[0][0] for pt in poly]
                ys = [pt[0][1] for pt in poly]
                zs = [pt[0][2] for pt in poly]
                if max(ys) >= y_top - 0.5 or max(xs) <= x0 + 1e-3 or min(xs) >= x1 - 1e-3 or max(zs) <= z0 + 1e-3 or min(zs) >= z1 - 1e-3:
                    next_pieces.append(poly)
                    continue
                rem = poly
                for axis, bound, keep_le in ((0, x0, True), (0, x1, False), (2, z0, True), (2, z1, False)):
                    outside = _clip_poly_axis(rem, axis, bound, keep_le)
                    if outside and _poly_xz_area(outside) > 1e-3:
                        next_pieces.append(outside)
                    rem = _clip_poly_axis(rem, axis, bound, not keep_le)
                    if not rem:
                        break
                # Whatever survives in `rem` lies strictly inside the occluder box and is discarded.
            pieces = next_pieces
        for poly in pieces:
            emit_poly(poly, mat, orig, srcs)

    return out_vertices, out_faces, out_uvs, out_materials, out_origins, out_source_sets, out_colors
