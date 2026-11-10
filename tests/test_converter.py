"""Asset pipeline tests. Standard tests never require copyrighted ROM data."""
import os
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import sm64ds_convert as m


class FormatTests(unittest.TestCase):
    def test_lz10_literal_and_overlap(self):
        # LZ77 prefix + LZ10: literals ABC and a length-6 distance-3 overlap.
        packed = b'LZ77\x10\x09\0\0\x10ABC\x30\x02'
        self.assertEqual(m.lz77(packed), b'ABCABCABC')
        self.assertEqual(m.lz77(b'\x10\x00\x00\x00'), b'\x10\x00\x00\x00')
        with self.assertRaises(m.FormatError):
            m.lz77(b'LZ77\x10\x09\0\0\x10ABC\x30\x09')
        with self.assertRaises(m.FormatError):
            m.lz77(b'LZ77\x10\x05\0\0\x00ABC')
        with self.assertRaises(m.FormatError):
            m.lz77(b'LZ77\x10\xff\xff\xff')

    def test_fnt(self):
        fnt = struct.pack('<IHH',8,0,1)+b'\x05hello\x00'
        self.assertEqual(m.fnt_names(fnt),{0:'hello'})
        with self.assertRaises(m.FormatError):
            m.fnt_names(struct.pack('<IHH',99,0,1))

    def test_narc(self):
        fnt = struct.pack('<IHH',8,0,1)+b'\x04blob\0'
        a = b'GMIF'+struct.pack('<I',8+5)+b'abcde'
        b = b'BTNF'+struct.pack('<I',8+len(fnt))+fnt
        c = b'BTAF'+struct.pack('<II',20,1)+struct.pack('<II',0,5)
        contents=c+b+a
        header=struct.pack('<4sHHIHH',b'NARC',0xFFFE,0x100,len(contents)+16,16,3)
        n=m.Narc(header+contents)
        self.assertEqual(n.read(0),b'abcde')
        self.assertEqual(n.read('blob'),b'abcde')
        with self.assertRaises(m.FormatError):
            n.read(1)
        with self.assertRaises(m.FormatError):
            m.Narc(header+contents[:-1])

    def test_fixed(self):
        self.assertEqual(m.checked_fx(-4096),-65536)
        self.assertEqual(m.checked_fx(4096),65536)
        with self.assertRaises(m.FormatError):
            m.checked_fx(0x10000000)

    def test_quaternion(self):
        self.assertEqual(m.quaternion((0,0,0)),(0,0,0,32767))
        q=m.quaternion((1024,0,0))
        self.assertAlmostEqual(q[0],23170,delta=2)
        self.assertAlmostEqual(q[3],23170,delta=2)
        # 0xF800 in the BMD is a signed 12-bit negative angle in low 12 bits.
        self.assertEqual(m.quaternion((0xf800,0,0)), m.quaternion((0x800,0,0)))

    def test_bca_frame_sampling_and_shortest_rotation(self):
        data = bytearray(0x18 + 0x24 + 18 * 2 + 4 * 4)
        struct.pack_into('<H',data,2,7)
        data[4]=1
        # scale pool = 0x60, rot pool = 0x70, translation pool=0x80,
        # track offset=0x18 (fit within 0x24 bytes).
        struct.pack_into('<IIII',data,8,0x60,0x70,0x80,0x18)
        data.extend(b'\0'*0x80)
        for i in range(9):
            struct.pack_into('<BBH',data,0x18+i*4,0,0,0)
        for j in range(3):
            struct.pack_into('<i',data,0x60,4096)
            struct.pack_into('<i',data,0x80,0)
        # Rotation X uses 4-frame keys; 7 frames means tail indices at 4,5,6.
        struct.pack_into('<BBH',data,0x18+3*4,2,1,0)
        for i, v in enumerate((0x7fe, -0x7fe, 0, 0)):
            struct.pack_into('<h',data,0x70+i*2,v)
        a=m.Animation(bytes(data),1)
        self.assertEqual(a.sample_channel(0,3,0),0x7fe)
        self.assertEqual(a.sample_channel(0,3,4),-0x7fe)
        # Midpoint must travel shortest arc across 0x800 discontinuity.
        self.assertTrue(0x800 <= (a.sample_channel(0,3,2)&0xfff) <= 0xfff)

    def test_gx_rejects_unknown(self):
        # An unknown command must never silently turn into wrong geometry.
        source=bytearray(0x90)
        struct.pack_into('<IIII',source,0,0,1,0x38,1)
        struct.pack_into('<II',source,0x0c,1,0x40)
        struct.pack_into('<II',source,0x40,1,0x48)
        struct.pack_into('<IIII',source,0x48,0,0,4,0x70)
        struct.pack_into('<I',source,0x70,0x00000099)
        struct.pack_into('<h',source,0x38,0)
        struct.pack_into('<h',source,0x40,0)
        with self.assertRaises(m.FormatError):
            m.convert_bmd(bytes(source))


@unittest.skipUnless(os.environ.get('SM64DS_ROM'), 'local ROM not supplied')
class LocalRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fs=m.Filesystem.from_file(Path(os.environ['SM64DS_ROM']))

    def test_catalog(self):
        self.assertEqual(len(self.fs.fat),1936)
        self.assertEqual(len(self.fs.names),1833)
        self.assertEqual(self.fs.by_name['ARCHIVE/arc0.narc'],105)

    def test_mario_source_and_skin(self):
        a=m.Narc(self.fs.read_id(105))
        self.assertEqual(a.name_ids['data/player/mario_model.bmd'],131)
        model=m.convert_bmd(self.fs.read('ARCHIVE/arc0.narc:131'))
        self.assertEqual(len(model.bones),16)
        self.assertEqual(model.weighted_count,0)
        self.assertEqual(len(model.faces),246)
        self.assertEqual(len(model.vertices),131)
        self.assertTrue(all(v.joint < 16 for v in model.vertices))
        self.assertEqual(model.bones[15].parent,8)

    def test_clips(self):
        for name,frames in [('wait',120),('walk',30),('run',30),('jump',11)]:
            b=m.Animation(self.fs.read(f'data/player/su_{name}.bca'),16)
            self.assertEqual(b.frames,frames)
            self.assertEqual(len(b.sample(0)),16)
            self.assertEqual(len(b.sample(frames-1)),16)

    def test_full_emission(self):
        model=m.convert_bmd(self.fs.read('ARCHIVE/arc0.narc:131'))
        clips=[(key,m.Animation(self.fs.read(f'data/player/su_{path}.bca'),16))
               for key,path in [('idle','wait'),('walk','walk'),('run','run'),('jump','jump')]]
        h,c,j=m.emit_model(model,clips,'mario_preview')
        self.assertIn('sat_skin_rigid_t',c)
        self.assertIn('sat_skeleton_clip_t',c)
        self.assertIn('sat_model_asset_t',c)
        self.assertIn('.joint_count=16',c)
        self.assertEqual(j['native_quad_commands'],246)


if __name__=='__main__':
    unittest.main()