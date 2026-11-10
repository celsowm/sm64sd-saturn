"""BMD model: hierarchy, material assignment, DS textures and GX streams."""
from __future__ import annotations
from dataclasses import dataclass,field as dc_field
from .common import FormatError,field,region
from .compression import lz77
from .geometry import Geometry,Vertex,gx_params
from .textures import SourceTexture,decode_texture

@dataclass(frozen=True)
class Bone:
    idx:int
    parent:int
    trans:tuple[int,int,int]
    scale:tuple[int,int,int]
    angles:tuple[int,int,int]

@dataclass(frozen=True)
class WeightedMatrix:
    influences:tuple[tuple[int,int],...]  # joint ID / byte weight (256=unity)

@dataclass
class Model:
    bones:list[Bone]
    vertices:list[Vertex]
    faces:list[tuple[int,int,int,int]]
    scale_shift:int
    material_count:int
    texture_count:int
    weighted_count:int
    gx_commands:dict[str,int]
    face_uvs:list[tuple[tuple[float,float],...]]=dc_field(default_factory=list)
    face_materials:list[int]=dc_field(default_factory=list)
    material_textures:list[SourceTexture|None]=dc_field(default_factory=list)
    weighted:list[WeightedMatrix]=dc_field(default_factory=list)


def _weighted(data:bytes,skin_at:int,num_weighted:int,nb:int)->list[WeightedMatrix]:
    if num_weighted==0:return []
    if not skin_at:raise FormatError('BMD weighted matrix block missing')
    by_off, joint_off, ranges_off, _bind = field(data,skin_at,'IIII')
    region(data,ranges_off,num_weighted*4)
    result=[]
    for i in range(num_weighted):
        count,start=field(data,ranges_off+i*4,'HH')
        if not 1<=count<=3:
            raise FormatError(f'weighted matrix {i}: {count} influences, LibSaturn supports 1..3')
        weights=region(data,by_off+start,count)
        influence=[]
        for j,w in enumerate(weights):
            bone=field(data,joint_off+2*(start+j),'H')
            if bone>=nb:raise FormatError('weighted matrix joint outside skeleton')
            if w:influence.append((bone,w))
        if sum(w for _,w in influence)!=256:
            raise FormatError(f'weighted matrix {i}: byte weights do not sum to 256')
        result.append(WeightedMatrix(tuple(influence)))
    return result


def convert_bmd(blob:bytes)->Model:
    data=lz77(blob)
    if len(data)<0x38:raise FormatError('truncated BMD')
    shift=data[0]; nb=field(data,4,'I')
    num_weighted=field(data,0x30,'I')
    # The ten vrbox backgrounds use scaleShift=13.  This is a legal DS
    # source scale (their geometry reaches ~58,982 world units), but it is NOT
    # directly representable by a 16.16 Saturn world coordinate.  The BMD
    # parser must preserve that scale; the dedicated skybox exporter later
    # normalizes it in camera-relative space instead of wrapping an int32.
    if not 1<=nb<=255 or shift>13:
        raise FormatError('BMD bone count or scaleShift unsupported (tested through 13)')
    if num_weighted>255:raise FormatError('more than 255 weighted BMD matrices')
    bones_at=field(data,8,'I')
    bones=[]
    # Preserve original bone IDs so BCA tracks remain indexed exactly as in the
    # game. Reordered source records are fine if IDs and parent order are valid.
    by_id={}
    for i in range(nb):
        at=bones_at+0x40*i;region(data,at,0x40)
        bid,parent_delta=field(data,at,'h'),field(data,at+8,'h')
        if not 0<=bid<nb or bid in by_id:
            raise FormatError(f'bad duplicate/missing bone ID at record {i}: {bid}')
        parent=bid+parent_delta
        if parent==bid:parent=-1
        if parent>=bid or parent< -1:raise FormatError(f'non-parent-first BMD joint ID {bid}')
        by_id[bid]=Bone(bid,parent,field(data,at+0x24,'iii'),
                        field(data,at+0x10,'iii'),field(data,at+0x1c,'HHH'))
    if len(by_id)!=nb:raise FormatError('incomplete BMD bones')
    bones=[by_id[i] for i in range(nb)]
    weighted=_weighted(data,field(data,0x34,'I'),num_weighted,nb)
    map_at=field(data,0x2c,'I')
    if not map_at:raise FormatError('missing BMD transformBoneMap')
    group_count,groups_at=field(data,0x0c,'II')
    if not 1<=group_count<=1024:raise FormatError('invalid BMD display group count')
    ntex,ptex=field(data,0x14,'II')
    npal,ppal=field(data,0x1c,'II')
    nmat,pmat=field(data,0x24,'II')
    if max(ntex,npal,nmat)>4096:raise FormatError('impossible BMD material/texture count')
    material_textures=[]
    tex_cache={}
    for i in range(nmat):
        at=pmat+i*0x30;region(data,at,0x30)
        texid,palid=field(data,at+4,'II')
        if texid>=ntex or palid>=npal:
            material_textures.append(None);continue
        key=(texid,palid)
        if key not in tex_cache:
            tex_cache[key]=decode_texture(data,ptex+texid*0x14,ppal+palid*0x10)
        material_textures.append(tex_cache[key])

    # The game's render traversal uses bone.materialIds[k] and
    # bone.displayListIds[k], not 'group index = material index'.
    draw_groups:dict[int,list[int]]={}
    for i in range(nb):
        at=bones_at+i*0x40
        count=field(data,at+0x30,'H')
        mats=field(data,at+0x34,'I');groups=field(data,at+0x38,'I')
        if count>4096:raise FormatError('malformed BMD bone material mapping')
        if count:
            mid_bytes=region(data,mats,count)
            group_bytes=region(data,groups,count)
            for mat,group in zip(mid_bytes,group_bytes):
                if mat>=nmat or group>=group_count:
                    raise FormatError('bone references invalid material/display group')
                dest=draw_groups.setdefault(group,[])
                if mat not in dest:dest.append(mat)
    geometry=Geometry()
    def resolve_slot(index:int)->int:
        # The DS MTX_RESTORE slot indexes the transformBoneMap (16-bit entries),
        # which may refer to one of the extra weighted matrices.
        if index<0 or index>=32:raise FormatError('DS matrix slot out of range')
        ref=field(data,map_at+index*2,'H')
        if ref>=nb+num_weighted:
            raise FormatError(f'GX slot {index} resolves to invalid matrix {ref}')
        return ref
    for group in range(group_count):
        at=groups_at+group*8
        count,lists_at=field(data,at,'II')
        if count>10000:raise FormatError('too many GX lists in BMD group')
        for mat in draw_groups.get(group,[0]):
            for di in range(count):
                _reserved,_ptr,length,offset=field(data,lists_at+di*0x10,'IIII')
                if length&3:raise FormatError('unaligned GX display list')
                geometry.decode(region(data,offset,length),resolve_slot,mat)
    if not geometry.vertices or not geometry.faces or len(geometry.faces)>=65536:
        raise FormatError('BMD has empty or oversized geometry')
    return Model(bones,geometry.vertices,geometry.faces,shift,nmat,ntex,num_weighted,
                 dict(geometry.gx_commands),geometry.face_uvs,
                 geometry.face_materials,material_textures,weighted)
