#!/usr/bin/env python3
"""Compare converted animation joint matrices against the source Euler formula.

This host audit compares integer BCA frames and parent-first transforms. It is
not a runtime SH-2 trace or proof of fractional-frame interpolation parity.
"""
import argparse
import json
import math
from pathlib import Path
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.bca import Animation
from sm64ds_pipeline.common import quaternion


def mul(a,b):
    return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def source_local(translation,angles,scale):
    # ModelComponents::func_02045178 is a row-vector XYZ Euler matrix.
    ax,ay,az=(2*math.pi*(x&4095)/4096 for x in angles)
    a,A=math.sin(ax),math.cos(ax);b,B=math.sin(ay),math.cos(ay);c,C=math.sin(az),math.cos(az)
    row=((B*C,B*c,-b),(b*a*C-A*c,A*C+b*a*c,B*a),(a*c+b*A*C,b*A*c-a*C,B*A))
    return [[row[j][i]*(scale[j]/4096) if j<3 else translation[i]/4096 for j in range(4)]
            for i in range(3)]+[[0,0,0,1]]


def converted_local(translation,angles,scale):
    x,y,z,w=(v/32767 for v in quaternion(angles))
    m=((1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)),
       (2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)),
       (2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)))
    return [[m[i][j]*(scale[j]/4096) if j<3 else translation[i]/4096 for j in range(4)]
            for i in range(3)]+[[0,0,0,1]]


def transform(m,p):
    return tuple(sum(m[i][j]*p[j] for j in range(3))+m[i][3] for i in range(3))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--model',default='ARCHIVE/arc0.narc:131')
    p.add_argument('--clip',action='append',default=[],help='name=ROM selector')
    a=p.parse_args();fs=Filesystem.from_file(a.rom);model=convert_bmd(fs.read(a.model))
    clips=a.clip or ['idle=ARCHIVE/arc0.narc:179','walk=ARCHIVE/arc0.narc:180',
                     'run=ARCHIVE/arc0.narc:145','jump=ARCHIVE/arc0.narc:120']
    reports=[]
    for spec in clips:
        name,sep,selector=spec.partition('=')
        if not sep:p.error('clip must be name=selector')
        anim=Animation(fs.read(selector),len(model.bones));worst_matrix=(0,None);worst_vertex=(0,None)
        frame_min_y=[]
        for frame in range(anim.frames):
            source=[];converted=[]
            for j,(translation,angles,scale) in enumerate(anim.sample(frame)):
                a0=source_local(translation,angles,scale);b0=converted_local(translation,angles,scale)
                parent=model.bones[j].parent
                source.append(mul(source[parent],a0) if parent>=0 else a0)
                converted.append(mul(converted[parent],b0) if parent>=0 else b0)
                err=max(abs(source[j][r][c]-converted[j][r][c]) for r in range(3) for c in range(4))
                if err>worst_matrix[0]:worst_matrix=(err,{'frame':frame,'joint':j})
            min_y=float('inf')
            for i,vertex in enumerate(model.vertices):
                if vertex.joint>=len(model.bones):continue
                pos=tuple(v*(1<<model.scale_shift)/4096 for v in (vertex.x,vertex.y,vertex.z))
                s=transform(source[vertex.joint],pos);t=transform(converted[vertex.joint],pos)
                min_y=min(min_y,s[1])
                err=math.dist(s,t)
                if err>worst_vertex[0]:worst_vertex=(err,{'frame':frame,'vertex':i,'joint':vertex.joint})
            frame_min_y.append(min_y)
        reports.append({'clip':name,'frames':anim.frames,'max_matrix_component_error':worst_matrix[0],
                        'matrix_location':worst_matrix[1],'max_rigid_vertex_error':worst_vertex[0],
                        'vertex_location':worst_vertex[1],
                        'source_min_y_range':[min(frame_min_y),max(frame_min_y)],
                        'source_frame_zero_min_y':frame_min_y[0]})
    print(json.dumps({'model':a.model,'model_scale_shift':model.scale_shift,'clips':reports,
                      'notes':['floating-point source formula, not DS fixed-point trace',
                               'quaternion quantization only; SDK runtime precision is not measured',
                               'weighted vertices excluded']},indent=2))
if __name__=='__main__':main()
