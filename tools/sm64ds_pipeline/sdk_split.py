"""Adapter to LibSaturn's position/UV plane splitter for static BMD faces."""
from pathlib import Path
import sys
from .common import FormatError


def split_nearby(vertices, faces, uvs, materials, sdk, *, center, radius, cell_size,
                 refine_faces=(), refine_cell_size=0, refine_grids=None, refine_axes=None):
    """Split faces near an XZ point on a world-aligned X/Z grid.

    All polygons are split by LibSaturn's canonical plane splitter, retaining
    interpolated UVs and source IDs. Nonplanar quads are triangulated first.
    """
    if radius<=0 or cell_size<=0:
        raise FormatError('SDK split radius and cell size must be positive')
    refine_faces=set(refine_faces)
    refine_grids=refine_grids or {}
    refine_axes=refine_axes or {}
    if refine_faces and (refine_cell_size<=0 or any(i<0 or i>=len(faces) for i in refine_faces)):
        raise FormatError('invalid refinement grid or source face ID')
    if any(i not in refine_faces or grid<=0 for i,grid in refine_grids.items()):
        raise FormatError('invalid per-face refinement grid')
    if any(i not in refine_faces or not axes or any(a not in 'xyz' for a in axes) or len(set(axes))!=len(axes)
           for i,axes in refine_axes.items()):
        raise FormatError('invalid per-face refinement axes')
    tools=Path(sdk).resolve()/'tools'
    if not (tools/'model_pipeline'/'intersections.py').is_file():
        raise FormatError('LibSaturn intersections.py is missing')
    sys.path.insert(0,str(tools))
    from model_pipeline.intersections import Face, split_by_plane
    points=list(vertices); intern={tuple(v):i for i,v in enumerate(points)}
    result=[];out_uv=[];out_mat=[];origins=[]
    def intern_point(p):
        p=tuple(round(x,8) for x in p)
        if p not in intern:intern[p]=len(points);points.append(p)
        return intern[p]
    def emit(poly,src,mat):
        corners=poly.corners
        for i in range(1,len(corners)-1):
            tri=[corners[0],corners[i],corners[i+1]]
            result.append(tuple(intern_point(c[0]) for c in (tri+[tri[-1]])))
            out_uv.append(tuple(c[1] for c in (tri+[tri[-1]])))
            out_mat.append(mat);origins.append(src)
    import math
    for src,(face,uv,mat) in enumerate(zip(faces,uvs,materials)):
        pos=[vertices[i] for i in face]
        minx,maxx=min(p[0] for p in pos),max(p[0] for p in pos)
        minz,maxz=min(p[2] for p in pos),max(p[2] for p in pos)
        nearby=(minx<=center[0]+radius and maxx>=center[0]-radius and
                minz<=center[1]+radius and maxz>=center[1]-radius)
        if not nearby and src not in refine_faces:
            result.append(face);out_uv.append(uv);out_mat.append(mat);origins.append(src);continue
        grid=refine_grids.get(src,refine_cell_size) if src in refine_faces else cell_size
        axes=refine_axes.get(src,'xz')
        triangles=[(0,1,2)] if face[2]==face[3] else [(0,1,2),(0,2,3)]
        for tri in triangles:
            pieces=[Face([(pos[k],uv[k]) for k in tri],src)]
            for axis in ('xyz'.index(a) for a in axes):
                lo=min(p[axis] for p in pos);hi=max(p[axis] for p in pos)
                for n in range(math.floor(lo/grid)+1,math.ceil(hi/grid)):
                    normal=tuple(1. if i==axis else 0. for i in range(3))
                    plane=(normal,n*grid,grid)
                    next_pieces=[]
                    for piece in pieces:
                        front,back=split_by_plane(piece,plane)
                        next_pieces.extend(p for p in (front,back) if p is not None)
                    pieces=next_pieces
            for piece in pieces:emit(piece,src,mat)
    return points,result,out_uv,out_mat,origins
