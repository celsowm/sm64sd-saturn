"""Convert DS joint-local or blended-matrix vertices to LibSaturn skin records.

For weighted BMD matrices, the DS uses a sum of (current joint world *
rest inverse), weighted by 8-bit weights. LibSaturn stores the per-influence
joint-local anchors directly; the rest inverse is applied offline here.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from .common import FormatError,quaternion
from .bmd import Model

@dataclass(frozen=True)
class Rigid:
    pos:tuple[int,int,int]
    joint:int

@dataclass(frozen=True)
class Blend:
    joints:tuple[int,int,int]
    count:int
    weights:tuple[int,int]
    positions:tuple[tuple[int,int,int],tuple[int,int,int],tuple[int,int,int]]

@dataclass(frozen=True)
class Layout:
    rigid:tuple[Rigid,...]
    blend:tuple[Blend,...]
    indices:tuple[tuple[int,int,int,int],...]
    order:tuple[int,...]  # output index -> source vertex index
    pos_shift:int
    quant_error:float


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def mm(a,b):
    return [[sum(a[r][k]*b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def mv(a,x):
    return tuple(dot(row,x) for row in a)


def inverse3(m):
    a,b,c=m[0];d,e,f=m[1];g,h,i=m[2]
    cof=[[e*i-f*h,c*h-b*i,b*f-c*e],
         [f*g-d*i,a*i-c*g,c*d-a*f],
         [d*h-e*g,b*g-a*h,a*e-b*d]]
    det=a*cof[0][0]+b*cof[1][0]+c*cof[2][0]
    if not math.isfinite(det) or abs(det)<1e-10:
        raise FormatError('singular BMD rest transform for weighted matrix')
    return [[x/det for x in row] for row in cof]


def rest_world(model:Model):
    result=[]
    for bone in model.bones:
        x,y,z,w=(v/32767 for v in quaternion(bone.angles))
        r=[[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
           [2*(x*y+z*w),1-2*(x*x+z*z), 2*(y*z-x*w)],
           [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
        s=[v/4096 for v in bone.scale]
        l=[[r[row][col]*s[col] for col in range(3)] for row in range(3)]
        t=tuple(v/4096 for v in bone.trans)
        if bone.parent>=0:
            pl,pt=result[bone.parent]
            result.append((mm(pl,l),tuple(a+b for a,b in zip(mv(pl,t),pt))))
        else:
            result.append((l,t))
    return result


def build_layout(model:Model)->Layout:
    if len(model.bones)>255:raise FormatError('LibSaturn supports <=255 skin joints')
    world=rest_world(model) if model.weighted else []
    source=[]
    for v in model.vertices:
        p=tuple(coord * (1<<model.scale_shift)/4096 for coord in (v.x,v.y,v.z))
        if v.joint<len(model.bones):
            source.append(('rigid',((v.joint,p),),p))
        else:
            index=v.joint-len(model.bones)
            if index<0 or index>=len(model.weighted):
                raise FormatError('weighted matrix reference out of range')
            influences=model.weighted[index].influences
            anchors=[]
            for joint,weight in influences:
                linear,trans=world[joint]
                inv=inverse3(linear)
                anchors.append((joint,mv(inv,tuple(a-b for a,b in zip(p,trans))),weight))
            source.append(('blend',tuple(anchors),p))
    # Store rigid vertices first, exactly as sat_skin_asset_t promises.
    order=tuple(i for i,(kind,_,__) in enumerate(source) if kind=='rigid') + \
          tuple(i for i,(kind,_,__) in enumerate(source) if kind=='blend')
    inv_order={old:new for new,old in enumerate(order)}
    positions=[]
    for kind,anchors,_ in source:
        if kind=='rigid':positions.append(anchors[0][1])
        else:positions.extend(x[1] for x in anchors)
    shift=min(15,12-model.scale_shift)
    def fit(n):return all(-32768<=round(v*(1<<n))<=32767 for pos in positions for v in pos)
    while shift>0 and not fit(shift):shift-=1
    if not fit(shift):raise FormatError('skin anchors exceed signed16 even with pos_shift=0')
    def q(pos):return tuple(round(v*(1<<shift)) for v in pos)
    error=max((abs(c/(1<<shift)-v) for p in positions for c,v in zip(q(p),p)),default=0.)
    rigid=[];blend=[]
    for old in order:
        kind,anchors,_=source[old]
        if kind=='rigid':
            joint,p=anchors[0];rigid.append(Rigid(q(p),joint))
        else:
            count=len(anchors)
            if not 1<=count<=3:raise FormatError('LibSaturn blending supports 1..3 nonzero influences')
            joints=[a[0] for a in anchors]+[0]*(3-count)
            weights=[a[2]*128 for a in anchors[:2]]+[0]*max(0,2-count)
            p=[q(a[1]) for a in anchors]+[(0,0,0)]*(3-count)
            blend.append(Blend(tuple(joints),count,tuple(weights[:2]),tuple(p)))
    faces=tuple(tuple(inv_order[v] for v in face) for face in model.faces)
    return Layout(tuple(rigid),tuple(blend),faces,order,shift,error)
