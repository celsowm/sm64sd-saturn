#!/usr/bin/env python3
"""Audit SDK-split static geometry against its original source triangles."""
import argparse
import json
from collections import Counter
from pathlib import Path
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.sdk_split import split_nearby


def area(a,b,c):
    u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
    cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    return sum(x*x for x in cross)**0.5/2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--libsaturn-source',type=Path,required=True)
    p.add_argument('--grid',type=float,default=64);p.add_argument('--radius',type=float,default=48)
    p.add_argument('--refine-face',type=int,action='append',default=[])
    p.add_argument('--refine-grid',type=float,default=0)
    p.add_argument('--refine-override',action='append',default=[],metavar='FACE=GRID')
    p.add_argument('--refine-manifest',type=Path)
    p.add_argument('--pack-split-quads',action='store_true')
    a=p.parse_args();fs=Filesystem.from_file(a.rom)
    model=convert_bmd(fs.read('data/stage/main_castle/main_castle_all.bmd'))
    vertices=[tuple(c*(1<<model.scale_shift)*64/4096 for c in (v.x,v.y,v.z)) for v in model.vertices]
    overrides={int(face):float(grid) for face,grid in (v.split('=',1) for v in a.refine_override)}
    axes={}
    if a.refine_manifest:
        if a.refine_face or overrides:p.error('manifest cannot be combined with explicit faces or overrides')
        for entry in json.loads(a.refine_manifest.read_text()):
            i=entry['face']
            if not 0<=i<len(model.faces) or list(model.faces[i])!=entry['vertices'] or list(model.face_provenance[i])!=entry['provenance']:
                p.error(f'refinement face {i} does not match source model')
            a.refine_face.append(i)
            if 'grid' in entry:overrides[i]=entry['grid']
            if 'axes' in entry:axes[i]=entry['axes']
    pts,faces,uvs,mats,origin=split_nearby(vertices,model.faces,model.face_uvs,model.face_materials,
        a.libsaturn_source,center=(0,256),radius=a.radius,cell_size=a.grid,
        refine_faces=a.refine_face,refine_cell_size=a.refine_grid,refine_grids=overrides,refine_axes=axes,
        pack_quads=a.pack_split_quads)
    source_area=[]
    for face in model.faces:
        p0,p1,p2,p3=[vertices[i] for i in face]
        source_area.append(area(p0,p1,p2)+(0 if face[2]==face[3] else area(p0,p2,p3)))
    totals=Counter();small=[]
    for i,(face,src) in enumerate(zip(faces,origin)):
        p0,p1,p2,p3=[pts[j] for j in face]
        ar=area(p0,p1,p2)+(0 if face[2]==face[3] else area(p0,p2,p3))
        totals[src]+=ar
        if ar<1e-5:small.append({'face':i,'source':src,'area':ar})
    errors=sorted([{'source':i,'source_area':v,'output_area':totals[i],
                    'relative_error':abs(v-totals[i])/v if v else 0} for i,v in enumerate(source_area)],
                  key=lambda x:x['relative_error'],reverse=True)
    print(json.dumps({'faces':len(faces),'vertices':len(pts),'degenerate':small,
                      'largest_area_errors':errors[:10]},indent=2))
if __name__=='__main__':main()
