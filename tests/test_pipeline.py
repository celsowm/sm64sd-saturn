"""Format-level and regression tests without commercial ROM bytes."""
from __future__ import annotations
import os
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from sm64ds_pipeline.common import FormatError
from sm64ds_pipeline import Bone,Model,Animation,Vertex
from sm64ds_pipeline.bmd import _weighted,WeightedMatrix,_load_matrix_slots,_draw_schedule
from sm64ds_pipeline.geometry import Geometry,identity
from sm64ds_pipeline.skinning import build_layout
from sm64ds_pipeline.textures import SourceTexture,decode_texture,bake_face,index_bakes
from sm64ds_pipeline.emit import emit_model
from sm64ds_pipeline.subdivide import split_large_faces
from sm64ds_pipeline.sdk_split import split_nearby
from sm64ds_pipeline.adaptive_bake import adaptive_bakes
from audit_pose_conversion import source_local,converted_local,transform


def fifo(commands):
    """Pack DS GX command words and their following parameter payloads."""
    result=bytearray()
    for i in range(0,len(commands),4):
        group=commands[i:i+4]
        word=sum(cmd<<(8*j) for j,(cmd,_) in enumerate(group))
        result.extend(struct.pack('<I',word))
        for cmd,args in group:
            result.extend(struct.pack('<'+'I'*len(args),*args))
    return bytes(result)


class FormatTests(unittest.TestCase):
    def test_pose_oracle_compound_rotation_and_scale(self):
        translation=(4096,-8192,2048);angles=(400,700,1100);scale=(2048,4096,8192)
        expected=source_local(translation,angles,scale)
        converted=converted_local(translation,angles,scale)
        for basis in ((0,0,0),(1,0,0),(0,1,0),(0,0,1)):
            a=transform(expected,basis);b=transform(converted,basis)
            self.assertLess(sum((x-y)**2 for x,y in zip(a,b))**.5,0.0002)

    def test_filtered_bake_averages_subtexels_without_transparent_color_bleed(self):
        pixels=tuple((255,0,0,255) if x%2 else (0,0,255,0)
                     for y in range(16) for x in range(16))
        tex=SourceTexture(16,16,pixels)
        uv=((0,0),(16,0),(16,16),(0,16))
        baked=bake_face(tex,uv,8,samples=2)
        self.assertTrue(all(p==(255,0,0,128) for p in baked.rgba))
        with self.assertRaises(FormatError):bake_face(tex,uv,8,samples=3)

    def test_draw_schedule_retains_source_order_and_repeated_bindings(self):
        data=bytearray(0x100)
        struct.pack_into('<H',data,0x30,4)
        struct.pack_into('<II',data,0x34,0x80,0x90)
        data[0x80:0x84]=bytes([1,0,1,2])
        data[0x90:0x94]=bytes([2,1,2,0])
        self.assertEqual(_draw_schedule(bytes(data),0,1,3,[0,0,0x80000000]),
                         [(2,1),(1,0),(2,1)])
        data[0x90]=3
        with self.assertRaises(FormatError):
            _draw_schedule(bytes(data),0,1,3,[0,0,0])

    def test_adaptive_bake_selects_detail_and_honors_budget(self):
        pixels=tuple(((255 if (x+y)%2 else 0),0,0,255) for y in range(16) for x in range(16))
        tex=SourceTexture(16,16,pixels)
        uv=((0,0),(16,0),(16,16),(0,16))
        tiles,_,face,selected=adaptive_bakes([tex],[uv],high_face_limit=1,byte_budget=256)
        self.assertEqual(selected,[0]);self.assertEqual((tiles[face[0]].width,tiles[face[0]].height),(16,16))
        tiles,_,face,selected=adaptive_bakes([tex],[uv],high_face_limit=1,byte_budget=64)
        self.assertEqual(selected,[]);self.assertEqual(len(tiles[face[0]].pixels),64)
        _,low_palette,_,_=adaptive_bakes([tex],[uv],high_face_limit=0,byte_budget=256,samples=4)
        _,high_palette,_,chosen=adaptive_bakes([tex],[uv],high_face_limit=1,byte_budget=256,samples=4)
        self.assertEqual(low_palette,high_palette)
        self.assertEqual(chosen,[0])
        _,_,_,chosen=adaptive_bakes([tex],[uv],high_face_limit=1,byte_budget=256,priorities=[0])
        self.assertEqual(chosen,[])

    @unittest.skipUnless((Path(__file__).resolve().parents[2]/'lib-saturn/tools/model_pipeline/intersections.py').is_file(),
                         'local LibSaturn source absent')
    def test_sdk_partition_preserves_triangle_area_and_uvs(self):
        sdk=Path(__file__).resolve().parents[2]/'lib-saturn'
        vertices=[(-2,0,-2),(2,0,-2),(0,0,2)]
        face=(0,1,2,2);uv=((-2,-2),(2,-2),(0,2),(0,2))
        points,faces,tex,mats,origins=split_nearby(vertices,[face],[uv],[3],sdk,
            center=(0,0),radius=5,cell_size=2)
        self.assertGreater(len(faces),1)
        area=0
        for f,u in zip(faces,tex):
            p=[points[i] for i in f[:3]]
            for pos,t in zip(p,u):self.assertEqual((pos[0],pos[2]),t)
            area+=abs((p[1][0]-p[0][0])*(p[2][2]-p[0][2])-
                      (p[2][0]-p[0][0])*(p[1][2]-p[0][2]))/2
        self.assertAlmostEqual(area,8)
        self.assertEqual(set(mats),{3});self.assertEqual(set(origins),{0})
        # Explicit refinement applies even outside the default radius and
        # keeps the same source/material/UV association.
        refined=split_nearby(vertices,[face],[uv],[3],sdk,center=(100,100),
            radius=1,cell_size=2,refine_faces=[0],refine_cell_size=1)
        self.assertGreater(len(refined[1]),len(faces))
        self.assertEqual(set(refined[3]),{3});self.assertEqual(set(refined[4]),{0})
        for part,coords in zip(refined[1],refined[2]):
            for index,coord in zip(part,coords):
                p=refined[0][index];self.assertEqual((p[0],p[2]),coord)
        finer=split_nearby(vertices,[face],[uv],[3],sdk,center=(100,100),
            radius=1,cell_size=2,refine_faces=[0],refine_cell_size=2,refine_grids={0:1})
        self.assertEqual(refined,finer)
        with self.assertRaises(FormatError):
            split_nearby(vertices,[face],[uv],[3],sdk,center=(0,0),radius=5,
                         cell_size=2,refine_faces=[1],refine_cell_size=1)
        with self.assertRaises(FormatError):
            split_nearby(vertices,[face],[uv],[3],sdk,center=(0,0),radius=5,
                         cell_size=2,refine_grids={0:1})
        wall=[(0,0,0),(0,4,0),(0,0,4)]
        wall_uv=((0,0),(4,0),(0,4),(0,4))
        pts,parts,coords,_,_=split_nearby(wall,[face],[wall_uv],[3],sdk,center=(100,100),
            radius=1,cell_size=2,refine_faces=[0],refine_cell_size=2,refine_axes={0:'xyz'})
        self.assertGreater(len(parts),1)
        area=0
        for part,part_uv in zip(parts,coords):
            for idx,texcoord in zip(part,part_uv):self.assertEqual(pts[idx][1:],texcoord)
            a,b,c=(pts[idx] for idx in part[:3])
            area+=abs((b[1]-a[1])*(c[2]-a[2])-(c[1]-a[1])*(b[2]-a[2]))/2
        self.assertAlmostEqual(area,8)

    def test_subdivision_preserves_triangle_and_quad_uvs(self):
        vertices=[(0,0,0),(8,0,0),(8,8,0),(0,8,0)]
        uv=[(0,0),(8,0),(8,8),(0,8)]
        for face,coords in [((0,1,2,3),uv),((0,1,2,2),uv[:3]+uv[2:3])]:
            points,faces,uvs,mats,origins=split_large_faces(vertices,[face],[coords],[7],4)
            self.assertEqual((len(faces),mats,origins),(4,[7]*4,[0]*4))
            for part,part_uv in zip(faces,uvs):
                for index,tex in zip(part,part_uv):
                    self.assertEqual(points[index][:2],tex)
            def area(f):
                p=[points[i] for i in f]
                return abs(sum(p[i][0]*p[(i+1)%4][1]-p[(i+1)%4][0]*p[i][1] for i in range(4)))/2
            self.assertEqual(sum(map(area,faces)),64 if face[2]!=face[3] else 32)

    def test_display_list_matrix_slots_follow_part_remap(self):
        slots=[None]*32
        bone_map=[4,7,9]
        _load_matrix_slots(slots,bytes([2,0,1]),lambda n:bone_map[n])
        stream=fifo([(0x14,(0,)),(0x40,(0,)),(0x23,(0,0)),
                     (0x14,(1,)),(0x23,(4096,0)),(0x14,(2,)),
                     (0x23,(0,4096)),(0x41,())])
        geom=Geometry();geom.decode(stream,lambda slot:slots[slot],0)
        self.assertEqual([v.joint for v in geom.vertices],[9,4,7])
        _load_matrix_slots(slots,bytes([0xff,2]),lambda n:bone_map[n])
        self.assertEqual(slots[:3],[9,9,7])
        with self.assertRaises(FormatError):
            _load_matrix_slots(slots,bytes(33),lambda n:n)

    def test_material_texture_matrix_applies_outside_matrix_mode_texture(self):
        # Material bind sets TEXGEN=TEXCOORD, then position mode is restored
        # for the display list. That must not disable the material's SRT.
        stream=fifo([(0x40,(0,)),(0x22,(16|32<<16,)),(0x23,(0,0)),
                     (0x23,(4096,0)),(0x23,(0,4096)),(0x41,())])
        matrix=list(identity());matrix[0]=2
        geom=Geometry();geom.decode(stream,lambda k:k,0,
            texture_matrix=matrix,texture_generation=1)
        self.assertEqual(geom.face_uvs[0],((2.,2.),)*4)

    def test_mirrored_texture_repeat_preserves_both_eyes(self):
        tex=SourceTexture(8,8,tuple((x*32,0,0,255) for y in range(8) for x in range(8)),
                          repeat_s=True,flip_s=True)
        tile=bake_face(tex,((0,0),(16,0),(16,8),(0,8)),16)
        self.assertEqual([p[0] for p in tile.rgba[:16]],
                         [0,32,64,96,128,160,192,224,224,192,160,128,96,64,32,0])

    def test_gx_material_state_and_uv(self):
        stream=fifo([(0x30,(0x7fff,)),(0x40,(0,)),(0x22,(16|32<<16,)),
                     (0x23,(0,0)),(0x22,(32|32<<16,)),(0x23,(4096,0)),
                     (0x22,(16|48<<16,)),(0x23,(0,4096)),(0x41,())])
        geom=Geometry();geom.decode(stream,lambda k:k,3)
        self.assertEqual(len(geom.faces),1)
        self.assertEqual(geom.face_materials,[3])
        self.assertEqual(geom.face_provenance,[(-1,-1,-1,0)])
        self.assertEqual(geom.face_uvs[0][0],(1.,2.))
        self.assertIn('30',geom.gx_commands)

    def test_all_gx_primitives_preserve_winding_and_corner_uvs(self):
        # Independent index expectations use the source submission order;
        # every corner has a unique UV so index-only equality cannot hide a seam.
        cases={0:(6,[(0,2,1,1),(3,5,4,4)]),
               1:(8,[(0,3,2,1),(4,7,6,5)]),
               2:(5,[(0,2,1,1),(2,3,1,1),(2,4,3,3)]),
               3:(6,[(0,2,3,1),(2,4,5,3)])}
        for primitive,(count,expected) in cases.items():
            commands=[(0x40,(primitive,))]
            for i in range(count):
                commands.extend([(0x22,((i+1)*16|((i+2)*16)<<16,)),
                                 (0x23,((i+1)*256,(i+2)*256))])
            commands.append((0x41,()))
            geom=Geometry();geom.decode(fifo(commands),lambda k:k,0)
            actual=[tuple((geom.vertices[index].x//256)-1 for index in face) for face in geom.faces]
            self.assertEqual(actual,expected)
            for face,uvs in zip(expected,geom.face_uvs):
                self.assertEqual(uvs,tuple((float(i+1),float(i+2)) for i in face))
            self.assertTrue(all(row[3]==primitive for row in geom.face_provenance))

    def test_ds_4x4_compressed_format5(self):
        d=bytearray(0x180)
        # 8x8 = 4 blocks. Every texel selects palette entry 0, index table
        # follows the 16-byte packed 4x4 texel stream.
        struct.pack_into('<II',d,0x14+4,0x40,16)
        struct.pack_into('<I',d,0x14+0x10,5<<26)
        struct.pack_into('<II',d,0x28+4,0x80,8)
        struct.pack_into('<4H',d,0x80,0x001f,0x03e0,0x7c00,0x7fff)
        result=decode_texture(bytes(d),0x14,0x28)
        self.assertEqual((result.width,result.height),(8,8))
        self.assertEqual(result.pixels[0],(255,0,0,255))
        tile=bake_face(result,((0,0),(7,0),(7,7),(0,7)),8)
        indexed,pal,faces=index_bakes([tile,tile])
        self.assertEqual(len(indexed),1)
        self.assertEqual(faces,[0,0])
        self.assertEqual(indexed[0].pixels[0],1)
        self.assertEqual(pal[1],0x001f)

    def test_material_texture_flags_control_zero_transparency_and_wrap(self):
        d=bytearray(0x100)
        struct.pack_into('<II',d,0x14+4,0x40,16)
        struct.pack_into('<I',d,0x14+0x10,2<<26)
        struct.pack_into('<II',d,0x28+4,0x80,8)
        struct.pack_into('<4H',d,0x80,0x001f,0x03e0,0x7c00,0x7fff)
        d[0x40]=4  # first pixel index zero, second index one
        opaque=decode_texture(bytes(d),0x14,0x28)
        cutout=decode_texture(bytes(d),0x14,0x28,material_flags=(1<<29)|0x50000)
        self.assertEqual(opaque.pixels[0][3],255)
        self.assertEqual(cutout.pixels[0][3],0)
        self.assertEqual(cutout.pixels[1],(0,255,0,255))
        self.assertTrue(cutout.repeat_s and cutout.flip_s)

    def test_weighted_bmd_mapping_and_inverse_rest(self):
        d=bytearray(0x120)
        struct.pack_into('<IIII',d,0x80,0xa0,0xb0,0xc0,0)
        d[0xa0:0xa2]=b'\x80\x80'
        struct.pack_into('<HH',d,0xb0,0,1)
        struct.pack_into('<HH',d,0xc0,2,0)
        weights=_weighted(bytes(d),0x80,1,2)
        self.assertEqual(weights,[WeightedMatrix(((0,128),(1,128)))])
        bones=[Bone(0,-1,(0,0,0),(4096,)*3,(0,)*3),
               Bone(1,0,(4096,0,0),(4096,)*3,(0,)*3)]
        m=Model(bones,[Vertex(0,0,0,0),Vertex(2048,0,0,2)],
                [(0,1,1,0)],0,1,1,1,{},weighted=weights)
        skin=build_layout(m)
        self.assertEqual((len(skin.rigid),len(skin.blend)),(1,1))
        self.assertEqual(skin.blend[0].joints,(0,1,0))
        self.assertEqual(skin.blend[0].weights[0],16384)
        self.assertEqual(skin.blend[0].positions[0],(2048,0,0))
        self.assertEqual(skin.blend[0].positions[1],(-2048,0,0))
        self.assertEqual(skin.indices,((0,1,1,0),))
        # A malformed unsupported four-anchor blend is a hard error.
        struct.pack_into('<HH',d,0xc0,4,0)
        with self.assertRaises(FormatError):_weighted(bytes(d),0x80,1,2)

    def test_animated_nonunit_scale_is_exported(self):
        d=bytearray(0x180)
        struct.pack_into('<H',d,2,2);d[4]=1
        struct.pack_into('<IIII',d,8,0x80,0xc0,0xe0,0x18)
        for i in range(9):struct.pack_into('<BBH',d,0x18+4*i,0,0,0)
        for axis,s in enumerate((4096,2048,4096)):
            struct.pack_into('<BBH',d,0x18+4*axis,0,0,axis)
            struct.pack_into('<i',d,0x80+4*axis,s)
        struct.pack_into('<i',d,0xe0,0)
        a=Animation(bytes(d),1)
        self.assertEqual(a.sample(0)[0][2],(4096,2048,4096))
        m=Model([Bone(0,-1,(0,0,0),(4096,)*3,(0,)*3)],
                [Vertex(0,0,0,0),Vertex(4096,0,0,0),Vertex(0,4096,0,0)],
                [(0,2,1,1)],0,0,0,0,{})
        hdr,source,report=emit_model(m,[('squash',a)],'squash_test',textured=False)
        self.assertIn('squash_test_squash_scales',source)
        self.assertIn('32768',source)
        self.assertTrue(report['clip_stats'][0]['animated_scales'])


@unittest.skipUnless(os.environ.get('SM64DS_ROM'),'local ROM not supplied')
class ActualRomTests(unittest.TestCase):
    def test_castle_retains_original_double_sided_materials(self):
        from sm64ds_pipeline import Filesystem,convert_bmd
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        model=convert_bmd(fs.read('data/stage/main_castle/main_castle_all.bmd'))
        self.assertEqual([i for i,flags in enumerate(model.material_flags)
                          if (flags & 0xc0)==0xc0],[5,22])
        self.assertEqual(sum((model.material_flags[i]&0xc0)==0xc0
                             for i in model.face_materials),48)
        self.assertEqual({(flags>>16)&31 for flags in model.material_flags},{12,15,31})

    def test_mario_eye_material_scale_and_mirror(self):
        from sm64ds_pipeline import Filesystem,convert_bmd
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        head=convert_bmd(fs.read('ARCHIVE/arc0.narc:129'))
        eye=head.material_textures[0]
        self.assertEqual((eye.width,eye.height),(16,32))
        self.assertTrue(eye.repeat_s and eye.repeat_t and eye.flip_s and eye.flip_t)
        coords=[uv for mat,face in zip(head.face_materials,head.face_uvs) if mat==0 for uv in face]
        self.assertEqual(min(uv[0] for uv in coords),-0.125)
        self.assertEqual(max(uv[0] for uv in coords),32.125)

    def test_full_textured_mario(self):
        from sm64ds_pipeline import Filesystem,convert_bmd
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        model=convert_bmd(fs.read('ARCHIVE/arc0.narc:131'))
        clips=[(k,Animation(fs.read('data/player/su_'+n+'.bca'),16))
               for k,n in [('idle','wait'),('walk','walk'),('run','run'),('jump','jump')]]
        hdr,source,report=emit_model(model,clips,'mario_preview')
        self.assertEqual(report['rigid_vertices'],131)
        self.assertEqual(report['native_quad_commands'],246)
        self.assertGreater(report['texture_tiles'],0)
        self.assertLess(report['texture_pixels_bytes'],262144)
        self.assertIn('sat_model_texture_asset_t',source)
        self.assertIn('sm64ds_scale_clip_t',source)
        self.assertIn('MARIO_PREVIEW_TEXTURE_COUNT',hdr)

    def test_top_level_bmd_coverage(self):
        """All 450 must parse; none may be counted as a tolerated failure."""
        from sm64ds_pipeline import Filesystem,convert_bmd
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        models=[n for n in fs.by_name if n.endswith('.bmd')]
        self.assertEqual(len(models),450)
        for name in models:
            with self.subTest(model=name):
                m=convert_bmd(fs.read(name))
                self.assertTrue(m.vertices)
                self.assertTrue(m.faces)
                self.assertEqual(len(m.faces),len(m.face_uvs))

    def test_all_nested_narc_bmd_models(self):
        """The same BMD decoder must continue to accept 52 nested models."""
        from sm64ds_pipeline import Filesystem,Narc,convert_bmd
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        count=0
        for path in sorted(p for p in fs.by_name if p.endswith('.narc')):
            archive=Narc(fs.read(path))
            for index,name in archive.names.items():
                if not name.endswith('.bmd'):continue
                with self.subTest(model=path+':'+name):
                    model=convert_bmd(fs.read(f'{path}:{index}'))
                    self.assertTrue(model.faces)
                    self.assertTrue(model.vertices)
                count+=1
        self.assertEqual(count,52)

    def test_all_ten_skyboxes_emit_indexed_textures(self):
        from sm64ds_pipeline import Filesystem,convert_bmd
        from sm64ds_pipeline.skybox import emit_skybox,normalize_skybox
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        skyboxes=[n for n in fs.by_name if n.startswith('data/vrbox/') and n.endswith('.bmd')]
        self.assertEqual(len(skyboxes),10)
        for name in sorted(skyboxes):
            with self.subTest(model=name):
                m=convert_bmd(fs.read(name))
                self.assertEqual((m.scale_shift,len(m.bones)),(13,1))
                header,source,report=emit_skybox(m,'skybox_check',tile_size=8)
                self.assertEqual(report['scale_divisor'],512)
                self.assertEqual(report['max_scale_quant_error'],0)
                self.assertEqual(report['faces_without_texture'],0)
                self.assertGreater(report['texture_tiles'],0)
                self.assertLess(report['estimated_vdp1_texture_bytes'],262144)
                self.assertIn('sat_model_asset_t skybox_check_model',source)
                self.assertIn('SKYBOX_CHECK_SCALE_DIVISOR 512u',header)


class SkyboxTests(unittest.TestCase):
    """ROM-free validation of the high-scale static-background path."""

    @staticmethod
    def fixture():
        return Model(
            [Bone(0,-1,(0,0,0),(4096,4096,4096),(0,0,0))],
            [Vertex(-29491,0,0,0),Vertex(29491,0,0,0),
             Vertex(0,-15422,0,0),Vertex(0,15422,0,0)],
            [(0,1,3,2)],13,0,0,0,{},
            face_uvs=[((0.,0.),(7.,0.),(7.,7.),(0.,7.))],
            face_materials=[0],material_textures=[])

    def test_vrbox_exact_power_of_two_normalization(self):
        from sm64ds_pipeline.skybox import normalize_skybox
        m=self.fixture();geo=normalize_skybox(m)
        self.assertEqual(geo.scale_divisor,512)
        self.assertEqual(geo.vertices_fx16[0],(-29491*256,0,0))
        self.assertEqual(geo.vertices_fx16[1],(29491*256,0,0))
        self.assertEqual(geo.max_quant_error,0)
        self.assertLess(geo.target_max_units,128)
        self.assertGreater(geo.source_max_units,32767)
        self.assertEqual(geo.vertices_fx16[3][1],15422*256)

    def test_static_skybox_emit_without_fabricated_animation(self):
        from sm64ds_pipeline.skybox import emit_skybox
        m=self.fixture()
        header,source,report=emit_skybox(m,'skybox_test',textured=False)
        self.assertIn('SKYBOX_TEST_SCALE_DIVISOR 512u',header)
        self.assertIn('sat_model_asset_t skybox_test_model',source)
        self.assertNotIn('sat_skin_asset_t',source)
        self.assertNotIn('sat_skeleton_clip_t',source)
        self.assertEqual(report['kind'],'camera-relative-static-skybox')
        self.assertEqual(report['native_quad_commands'],1)
        self.assertEqual(report['faces_without_texture'],1)

    def test_skybox_fail_closed_when_root_transform_is_nonidentity(self):
        from sm64ds_pipeline.skybox import normalize_skybox
        m=self.fixture()
        m.bones[0]=Bone(0,-1,(4096,0,0),(4096,)*3,(0,)*3)
        with self.assertRaises(FormatError):normalize_skybox(m)
        with self.assertRaises(FormatError):normalize_skybox(self.fixture(),target_radius=0)



if __name__=='__main__':unittest.main()
