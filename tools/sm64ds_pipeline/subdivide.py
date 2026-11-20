"""Split oversized static faces while retaining their UV interpolation."""
from math import ceil, dist


def _lerp_tuple(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _bilerp_tuple(c00, c10, c11, c01, u, v):
    top = _lerp_tuple(c00, c10, u)
    bot = _lerp_tuple(c01, c11, u)
    return _lerp_tuple(top, bot, v)


def split_long_edges(vertices, faces, uvs, materials, max_edge, *, colors=None, high_y=None, high_max_edge=None):
    """Parametrically split oversized faces along long edges, preserving UVs and vertex colors.

    Quads are split into an exact nu x nv bilinear grid along their own edges so
    diagonal walls and carpets subdivide cleanly into native quads without sliver
    triangles. Triangles bisect their longest edge recursively until all edges
    are <= max_edge. When high_y and high_max_edge are given, faces whose lowest
    vertex is >= high_y use high_max_edge so distant ceilings stay compact.
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
        limit = high_max_edge if (high_y is not None and high_max_edge is not None and min(q[1] for q in p) >= high_y) else max_edge
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
