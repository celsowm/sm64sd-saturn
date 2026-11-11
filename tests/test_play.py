"""Synthetic KCL and native locomotion regressions; optional real-ROM checks."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import contextlib
import io
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from sm64ds_pipeline.kcl import decode_kcl
from sm64ds_pipeline.common import FormatError


def fixture():
    # A right triangle 64 world units wide, with an overlapping dummy prism.
    header=struct.pack('<4I',56,68,76,108)+bytes(40)
    return (header+struct.pack('<3i',0,0,0)+
            struct.pack('<12h',0,1024,0,0,0,-1024,-1024,0,0,724,0,724)+
            struct.pack('<i6H',64000*724,0,0,1,2,3,7))


class PlayTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv('SM64DS_ROM'),'local ROM absent')
    def test_default_mario_clips_are_normal_gameplay_assets(self):
        from sm64ds_pipeline.cli import main
        from sm64ds_pipeline.filesystem import Filesystem, Narc
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        archive=Narc(fs.read('ARCHIVE/arc0.narc'))
        for i,name in ((179,'wait'),(180,'walk'),(145,'run'),(120,'jump')):
            self.assertEqual(archive.names[i],f'data/player/{name}.bca')
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                main(['--rom',os.environ['SM64DS_ROM'],'--out',tmp])
            report=json.loads((Path(tmp)/'mario_preview.json').read_text())
            self.assertEqual(report['source_clips'],{
                'idle':'ARCHIVE/arc0.narc:179','walk':'ARCHIVE/arc0.narc:180',
                'run':'ARCHIVE/arc0.narc:145','jump':'ARCHIVE/arc0.narc:120'})

    def test_prism_scale_normal_and_attribute(self):
        p,=decode_kcl(fixture())
        self.assertEqual(p.vertices,((0,0,0),(0,0,64),(64,0,0)))
        self.assertEqual(p.normal,(0,1,0))
        self.assertEqual(p.attribute,7)

    def test_bad_kcl_offsets_and_indices_fail_closed(self):
        for offset,value in ((0,200),(100,9999)):
            b=bytearray(fixture())
            struct.pack_into('<I' if offset==0 else '<H',b,offset,value)
            with self.assertRaises(FormatError):decode_kcl(b)
        with self.assertRaises(FormatError):decode_kcl(fixture()[:-1])

    @unittest.skipUnless(shutil.which('cc'),'C compiler missing')
    def test_native_player_contacts_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            (path/'saturn').mkdir()
            (path/'saturn/math3d.h').write_text('#include <stdint.h>\ntypedef struct {int32_t x,y,z;} sat_vec3_t;\n')
            target=path/'play'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                '-I',str(path),'-I',str(ROOT/'runtime'),str(ROOT/'runtime/sm64ds_play.c'),
                str(ROOT/'tests/host_play.c'),'-o',str(target)],check=True,capture_output=True,text=True)
            subprocess.run([str(target)],check=True,capture_output=True,text=True)

    @unittest.skipUnless(os.getenv('SM64DS_ROM'),'local ROM absent')
    def test_castle_kcl_render_scale_alignment(self):
        from sm64ds_pipeline.filesystem import Filesystem
        from sm64ds_pipeline.bmd import convert_bmd
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        prisms=decode_kcl(fs.read('data/stage/main_castle/main_castle.kcl'))
        self.assertEqual(len(prisms),1243)
        model=convert_bmd(fs.read('data/stage/main_castle/main_castle_all.bmd'))
        vertices=[tuple(c*128/4096 for c in (v.x,v.y,v.z)) for v in model.vertices]
        # Reconstructed KCL corners match BMD corners closely despite
        # separately quantized normals and invisible collision-only walls.
        distances=sorted(min(sum((a-b)**2 for a,b in zip(point,v)) for v in vertices)**.5
                         for p in prisms for point in p.vertices)
        self.assertLess(distances[len(distances)//2],0.04)

    @unittest.skipUnless(os.getenv('SM64DS_ROM'),'local ROM absent')
    def test_gameplay_head_matches_body_attachment_space(self):
        from sm64ds_pipeline.filesystem import Filesystem, Narc
        from sm64ds_pipeline.bmd import convert_bmd
        from sm64ds_pipeline.skybox import emit_skybox
        fs=Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        arc=Narc(fs.read('ARCHIVE/arc0.narc'))
        self.assertEqual(arc.names[129],'data/player/mario_head_cap.bmd')
        head=convert_bmd(fs.read('ARCHIVE/arc0.narc:129'))
        _,_,report=emit_skybox(head,'mario_head',palette_base=4)
        self.assertEqual(head.scale_shift,0)
        self.assertEqual(report['scale_divisor'],1)
        self.assertEqual(report['faces_without_texture'],0)
        self.assertEqual(report['native_quad_commands'],206)
