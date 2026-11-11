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
from sm64ds_pipeline.bmd import _weighted,WeightedMatrix
from sm64ds_pipeline.geometry import Geometry,identity
from sm64ds_pipeline.skinning import build_layout
from sm64ds_pipeline.textures import SourceTexture,decode_texture,bake_face,index_bakes
from sm64ds_pipeline.emit import emit_model


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
        self.assertEqual(geom.face_uvs[0][0],(1.,2.))
        self.assertIn('30',geom.gx_commands)

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
