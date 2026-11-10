"""Pure Nintendo DS geometry FIFO decoder -> bone-local VDP1 face IR.

BMD render-state writes are accepted explicitly; position-matrix commands
are interpreted in DS row-vector order and are NOT silently dropped. Matrix
restore references the source transformBoneMap, which may point to a rigid
joint or a weighted matrix. UVs are preserved until the texture-baking stage.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass,field as dc_field
from math import isfinite
from .common import FormatError,field,region,signed10,signed16

@dataclass(frozen=True)
class Vertex:
    x: int
    y: int
    z: int
    joint: int

@dataclass(frozen=True)
class Corner:
    vertex: int
    uv: tuple[float,float]

PARAM_COUNTS = {0x00:0,0x10:1,0x11:0,0x12:1,0x13:1,0x14:1,0x15:0,
                0x16:16,0x17:12,0x18:16,0x19:12,0x1A:9,0x1B:3,0x1C:3,
                0x20:1,0x21:1,0x22:1,0x23:2,0x24:1,0x25:1,0x26:1,
                0x27:1,0x28:1,0x29:1,0x2A:1,0x2B:1,0x30:1,0x31:1,
                0x32:1,0x33:1,0x34:32,0x40:1,0x41:0,0x50:1,0x60:1,
                0x70:3,0x71:2,0x72:1}

def gx_params(cmd: int)->int:
    if cmd not in PARAM_COUNTS:raise FormatError(f'unknown GX opcode 0x{cmd:02x}')
    return PARAM_COUNTS[cmd]

def identity():
    return (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)

def mul(a,b):
    return tuple(sum(a[r*4+k]*b[k*4+c] for k in range(4)) for r in range(4) for c in range(4))

def affine(words,n):
    if n==16:
        return tuple(signed32(v)/4096 for v in words)
    if n==12:
        return tuple(signed32(words[r*3+c])/4096 if c<3 else (1. if r==3 else 0.)
                     for r in range(4) for c in range(4))
    if n==9:
        return tuple(signed32(words[r*3+c])/4096 if r<3 and c<3 else (1. if r==c else 0.)
                     for r in range(4) for c in range(4))
    raise FormatError('bad matrix width')

def signed32(n):
    n &= 0xffffffff
    return n-0x100000000 if n&0x80000000 else n

@dataclass
class Geometry:
    vertices:list[Vertex]=dc_field(default_factory=list)
    faces:list[tuple[int,int,int,int]]=dc_field(default_factory=list)
    face_uvs:list[tuple[tuple[float,float],...]]=dc_field(default_factory=list)
    face_materials:list[int]=dc_field(default_factory=list)
    gx_commands:Counter=dc_field(default_factory=Counter)
    _intern:dict=dc_field(default_factory=dict)

    def _vertex(self,xyz,joint,uv)->Corner:
        vx=Vertex(*xyz,joint)
        if vx not in self._intern:
            if len(self.vertices)>=65535:raise FormatError('more than 65535 unique model vertices')
            self._intern[vx]=len(self.vertices);self.vertices.append(vx)
        return Corner(self._intern[vx],uv)

    def _face(self,corners,material):
        self.faces.append(tuple(c.vertex for c in corners))
        self.face_uvs.append(tuple(c.uv for c in corners))
        self.face_materials.append(material)

    def decode(self,stream:bytes,map_slot,material:int)->None:
        pos=0;prim=-1;corners=[]
        vx=vy=vz=0;uv=(0.,0.);uv_current=False
        mode=2;slot=0;local=identity();tex_mtx=identity()
        saved={};stack=[]
        while pos<len(stream):
            word=field(stream,pos,'I');pos+=4
            for j in range(4):
                op=(word>>(j*8))&255
                self.gx_commands[f'{op:02x}']+=1
                n=gx_params(op)
                args=() if not n else (field(stream,pos,'I'),) if n==1 else field(stream,pos,'I'*n)
                pos+=n*4
                if op==0x10:mode=args[0]&3
                elif op==0x11:
                    if mode in (1,2):stack.append((slot,local))
                    else:raise FormatError('GX matrix push in projection/texture mode needs dedicated raster support')
                elif op==0x12:
                    delta=signed10(args[0]&0x3f)
                    if delta<0 or delta>=len(stack):raise FormatError('GX MTX_POP outside local stack')
                    slot,local=stack[-1-delta];del stack[-1-delta:]
                elif op==0x13:
                    if mode not in (1,2):raise FormatError('unsupported MTX_STORE in non-position mode')
                    saved[args[0]&31]=(slot,local)
                elif op==0x14:
                    if mode not in (1,2):raise FormatError('MTX_RESTORE outside position mode')
                    k=args[0]&31
                    if k in saved:slot,local=saved[k]
                    else:slot=map_slot(k);local=identity()
                elif op==0x15:
                    if mode in (1,2):slot=map_slot(0);local=identity()
                    elif mode==3:tex_mtx=identity()
                    else:raise FormatError('projection matrix change in model stream')
                elif op in (0x16,0x17,0x18,0x19,0x1A,0x1B,0x1C):
                    if op in (0x16,0x18):m=affine(args,16)
                    elif op in (0x17,0x19):m=affine(args,12)
                    elif op==0x1A:m=affine(args,9)
                    elif op==0x1B:
                        scales=[signed32(v)/4096 for v in args]
                        m=tuple(scales[r] if r==c and r<3 else (1. if r==c else 0.)
                                for r in range(4) for c in range(4))
                    else:
                        m=list(identity());m[12:15]=(signed32(v)/4096 for v in args);m=tuple(m)
                    if mode==0:raise FormatError('projection matrix in model display list')
                    if mode==3:tex_mtx=m if op in (0x16,0x17) else mul(m,tex_mtx)
                    else:
                        if op in (0x16,0x17):
                            # A full matrix is no longer relative to an arbitrary skeleton
                            # bone. Only permit a root-local load, never silently misbind.
                            if slot!=map_slot(0):raise FormatError('absolute GX MTX_LOAD over a joint')
                            local=m
                        else:local=mul(m,local)
                elif op==0x22:
                    u=signed16(args[0])/16.;v=signed16(args[0]>>16)/16.
                    if mode==3:
                        u,v=(u*tex_mtx[0]+v*tex_mtx[4]+tex_mtx[12],
                             u*tex_mtx[1]+v*tex_mtx[5]+tex_mtx[13])
                    uv=(u,v);uv_current=True
                elif op==0x40:
                    if prim>=0:raise FormatError('nested BEGIN_VTXS')
                    prim=args[0]&3;corners=[]
                elif op==0x41:
                    if prim<0:raise FormatError('END_VTXS without BEGIN')
                    if prim in (0,1) and corners:raise FormatError('incomplete triangle/quad')
                    prim=-1;corners=[]
                elif op in (0x23,0x24,0x25,0x26,0x27,0x28):
                    if prim<0:raise FormatError('vertex outside BEGIN/END')
                    if op==0x23:
                        vx,vy,vz=signed16(args[0]),signed16(args[0]>>16),signed16(args[1])
                    elif op==0x24:
                        vx,vy,vz=(signed10(args[0]>>(10*k))*64 for k in range(3))
                    elif op==0x25:vx,vy=signed16(args[0]),signed16(args[0]>>16)
                    elif op==0x26:vx,vz=signed16(args[0]),signed16(args[0]>>16)
                    elif op==0x27:vy,vz=signed16(args[0]),signed16(args[0]>>16)
                    else:
                        vx+=signed10(args[0]);vy+=signed10(args[0]>>10);vz+=signed10(args[0]>>20)
                    if not all(-32768<=v<=32767 for v in (vx,vy,vz)):
                        raise FormatError('GX vertex outside signed16')
                    xyz=(vx/4096.,vy/4096.,vz/4096.)
                    xyz=tuple(round(4096*sum(xyz[k]*local[k*4+i] for k in range(3))+4096*local[12+i])
                              for i in range(3))
                    if not all(-32768<=v<=32767 for v in xyz):
                        raise FormatError('GX local matrix moved vertex beyond signed16, needs rescale')
                    co=self._vertex(xyz,slot,uv)
                    corners.append(co)
                    k=len(corners)
                    if prim==0 and k==3:
                        a,b,c=corners;self._face((a,c,b,b),material);corners=[]
                    elif prim==1 and k==4:
                        a,b,c,d=corners;self._face((a,d,c,b),material);corners=[]
                    elif prim==2 and k>=3:
                        a,b,c=corners[-3:]
                        if (k-3)&1:a,b=b,a
                        self._face((a,c,b,b),material)
                    elif prim==3 and k>=4 and k%2==0:
                        a,b,c,d=corners[-4:];self._face((a,c,d,b),material)
                # Other recognized opcodes change DS rendering state only (light,
                # colors, test ports, texture registers); geometry is still decoded.
                # Texture/material transfer is handled from the BMD records,
                # including texture coord generation when source op 0x22 exists.
        if prim>=0 or pos!=len(stream):raise FormatError('unfinished GX primitive/stream')
