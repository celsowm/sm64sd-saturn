"""ROM-free host skybox tests and optional locally supplied ASME integration.

The C host shim checks behavior, not SDK ABI, SH-2 linking or VDP1 timing.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.skybox import emit_skybox


class BackgroundHostTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'),'C compiler missing')
    def test_camera_follow_palette_safety_queue_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable=Path(tmp)/'background_test'
            subprocess.run([
                shutil.which('cc'),'-std=c11','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'tests/host_shim'),'-I',str(ROOT/'runtime'),
                str(ROOT/'runtime/sm64ds_background.c'),
                str(ROOT/'tests/host_background.c'),
                '-o',str(executable)],check=True,capture_output=True,text=True)
            subprocess.run([str(executable)],check=True,capture_output=True,text=True)

    def test_camera_background_pass_precedes_actors(self):
        h=(ROOT/'runtime/sm64ds_background.h').read_text()
        self.assertIn('#define SM64DS_BACKGROUND_PASS 0u',h)
        self.assertIn('#define SM64DS_ACTOR_PASS 1u',h)


@unittest.skipUnless(os.environ.get('SM64DS_ROM'),'local ROM absent')
class BackgroundRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))

    def test_skybox_palette_is_separate_from_mario(self):
        from sm64ds_pipeline.emit import emit_model
        from sm64ds_pipeline.bca import Animation
        mario=convert_bmd(self.fs.read('ARCHIVE/arc0.narc:131'))
        _,_,report=emit_model(
            mario,[('idle',Animation(self.fs.read('data/player/su_wait.bca'),16))],
            'mario_preview')
        actor_bytes=report['texture_pixels_bytes']
        self.assertGreater(actor_bytes,0)
        skyboxes=sorted(p for p in self.fs.by_name
                        if p.startswith('data/vrbox/') and p.endswith('.bmd'))
        self.assertEqual(len(skyboxes),10)
        for path in skyboxes:
            with self.subTest(path=path):
                model=convert_bmd(self.fs.read(path))
                header,source,r=emit_skybox(model,'skybox_preview')
                self.assertEqual(r['palette_base'],1)
                self.assertIn('.palette_base=1,',source)
                self.assertEqual(r['faces_without_texture'],0)
                self.assertEqual(r['native_quad_commands'],len(model.faces))
                self.assertLess(actor_bytes+r['estimated_vdp1_texture_bytes'],192*1024)
                self.assertLess(246+r['native_quad_commands'],800)

    @unittest.skipUnless(shutil.which('cc'),'C compiler missing')
    def test_generated_skybox_compiles_against_descriptor_shim(self):
        m=convert_bmd(self.fs.read('data/vrbox/vr02.bmd'))
        header,source,report=emit_skybox(m,'skybox_preview')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'skybox_preview.h').write_text(header)
            (p/'skybox_preview.c').write_text(source)
            subprocess.run([
                shutil.which('cc'),'-std=c11','-Wall','-Wextra','-Werror',
                '-fsyntax-only','-I',str(ROOT/'tests/host_shim'),
                str(p/'skybox_preview.c')],check=True,capture_output=True,text=True)
        self.assertGreater(report['texture_tiles'],0)


if __name__=='__main__':unittest.main()
