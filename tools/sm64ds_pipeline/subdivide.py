"""Split oversized static faces while retaining their UV interpolation."""
from math import dist


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
