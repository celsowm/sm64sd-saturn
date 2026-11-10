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
from sm64ds_pipeline.geometry import Geometry
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
        from sm64ds_pipeline import Filesystem,convert_bmd
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        models=[n for n in fs.by_name if n.endswith('.bmd')]
        successes=0
        for name in models:
            try:convert_bmd(fs.read(name));successes+=1
            except FormatError as e:
                # Skybox/background-only records have no skeleton or faces.
                if 'BMD bone count' not in str(e):raise
        self.assertEqual((len(models),successes),(450,440))

if __name__=='__main__':unittest.main()
