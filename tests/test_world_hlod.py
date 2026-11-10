"""ROM-free correctness and optional real-ROM regression for static world HLOD."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from sm64ds_pipeline.bmd import Model, Bone, convert_bmd
from sm64ds_pipeline.geometry import Vertex
from sm64ds_pipeline.textures import SourceTexture
from sm64ds_pipeline.world_hlod import static_source, build_world_hlod, materials_manifest
from sm64ds_pipeline.common import FormatError
from sm64ds_pipeline.filesystem import Filesystem

ROOT_BONE = Bone(0,-1,(0,0,0),(4096,4096,4096),(0,0,0))


def tiny_model(*, shift=1, quad=True):
    verts = [Vertex(0,0,0,0),Vertex(4096,0,0,0),Vertex(4096,4096,0,0),Vertex(0,4096,0,0)]
    faces = [(0,1,2,3)] if quad else [(0,1,2,2)]
    uv = [(0.,0.),(8.,0.),(8.,8.),(0.,8.)] if quad else [(0.,0.),(8.,0.),(8.,8.),(8.,8.)]
    tex = SourceTexture(8,8,tuple([(80,120,200,255)]*64))
    return Model([ROOT_BONE],verts,faces,shift,1,1,0,{},
                 [tuple(uv)],[0],[tex],[])


class WorldHlodAdapterTests(unittest.TestCase):
    def test_quad_to_two_triangles_preserves_winding_and_uv(self):
        s = static_source(tiny_model())
        self.assertEqual(s.triangles,[(0,1,2),(0,2,3)])
        self.assertEqual(s.uvs,[(0.,0.),(8.,0.),(8.,8.),(0.,8.)])
        self.assertEqual(s.report['source_quads'],1)
        self.assertEqual(s.report['zero_area_removed'],0)
        self.assertEqual(s.vertices[2],(2.,2.,0.))
        self.assertEqual(s.tri_materials,[0,0])

    def test_degenerate_face_is_audited_not_emitted(self):
        m = tiny_model()
        m.faces.append((0,1,1,1))
        m.face_uvs.append(m.face_uvs[0])
        m.face_materials.append(0)
        s = static_source(m)
        self.assertEqual(len(s.triangles),2)
        self.assertEqual(s.report['zero_area_removed'],1)
        self.assertEqual(s.report['zero_area_details'][0]['face'],1)

    def test_corner_uv_seams_are_not_collapsed(self):
        m = tiny_model()
        m.faces.append((0,1,2,3))
        m.face_uvs.append(((1.,0.),(9.,0.),(9.,8.),(1.,8.)))
        m.face_materials.append(0)
        s = static_source(m)
        self.assertEqual(len(s.vertices),8)
        self.assertEqual(len(s.triangles),4)
        self.assertNotEqual(s.triangles[0][0],s.triangles[2][0])

    def test_reject_skinned_or_nonidentity_static_root(self):
        m = tiny_model()
        m.vertices[0] = Vertex(0,0,0,1)
        with self.assertRaisesRegex(FormatError,'joint'):
            static_source(m)
        m = tiny_model()
        m.bones=[Bone(0,-1,(100,0,0),(4096,4096,4096),(0,0,0))]
        with self.assertRaisesRegex(FormatError,'non-identity'):
            static_source(m)

    def test_material_metadata_no_rom_pixels(self):
        manifest=materials_manifest(tiny_model())
        self.assertEqual(manifest['materials'][0]['texture_index'],0)
        self.assertEqual(len(manifest['textures']),1)
        self.assertNotIn('pixels_rgba',manifest['textures'][0])
        self.assertEqual(len(manifest['textures'][0]['sha256']),64)

    def test_missing_libsaturn_source_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FormatError,'not found'):
                build_world_hlod(tiny_model(),Path(tmp))

    @unittest.skipUnless(os.getenv('SM64DS_ROM'), 'Provide own ROM through SM64DS_ROM')
    def test_actual_castle_and_garden_lossless_ir(self):
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        expected={
            'main_castle':(1337,33,1370,0,24,24),
            'main_garden':(631,32,661,2,20,19),
        }
        for name,counts in expected.items():
            with self.subTest(name=name):
                m=convert_bmd(fs.read(f'data/stage/{name}/{name}_all.bmd'))
                s=static_source(m)
                self.assertEqual(tuple(s.report[k] for k in (
                    'source_faces','source_quads','output_triangles','zero_area_removed',
                    'material_count','unique_textures')),counts)
                self.assertTrue(all(0<=i<len(s.vertices) for tri in s.triangles for i in tri))
                self.assertTrue(all(0<=mid<len(s.materials) for mid in s.tri_materials))
                self.assertTrue(all(len(set(tri))==3 for tri in s.triangles))


if __name__ == '__main__':
    unittest.main()
