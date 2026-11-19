"""Synthetic unit tests for vertex-color baking, quad merging, and VDP1 LUT4 textures."""
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from sm64ds_pipeline.geometry import Geometry
from sm64ds_pipeline.quad_merge import merge_coplanar_quads
from sm64ds_pipeline.textures import SourceTexture, bake_face, index_bakes_lut4
from sm64ds_pipeline.adaptive_bake import adaptive_lut4_bakes
from sm64ds_pipeline.sdk_split import split_nearby
from sm64ds_pipeline.level_objects import blz_decompress, extract_castle_props
from sm64ds_pipeline.filesystem import Filesystem


def _pack_gx(*cmds):
    out = bytearray()
    for i in range(0, len(cmds), 4):
        chunk = cmds[i:i + 4]
        ops = [c[0] for c in chunk] + [0] * (4 - len(chunk))
        out.extend(struct.pack('<I', ops[0] | (ops[1] << 8) | (ops[2] << 16) | (ops[3] << 24)))
        for _, args in chunk:
            for a in args:
                out.extend(struct.pack('<I', a & 0xffffffff))
    return bytes(out)


class VisualUpgradeTests(unittest.TestCase):
    def test_gx_vertex_color_decode_and_bake_modulation(self):
        # Triangle with initial color white, then 0x20 black on vertex 1, red on vertex 2.
        stream = _pack_gx(
            (0x40, (0,)),  # BEGIN TRIANGLES
            (0x20, (0x0000,)),  # black
            (0x23, (0, 0)),
            (0x20, (0x001f,)),  # pure red
            (0x23, (4096 & 0xffff, 0)),
            (0x20, (0x7fff,)),  # white
            (0x23, ((4096 & 0xffff) << 16, 0)),
            (0x41, ()),
        )
        g = Geometry()
        g.decode(stream, lambda s: s, 0)
        self.assertEqual(len(g.faces), 1)
        # Geometry stores (a, c, b, b) for prim==0 triangles.
        self.assertEqual(g.face_colors[0], ((0, 0, 0), (31, 31, 31), (31, 0, 0), (31, 0, 0)))

        # White alpha-cutout shadow texture modulated by pure black vertex color.
        pixels = tuple((255, 255, 255, 255 if (x + y) % 2 == 0 else 0) for y in range(8) for x in range(8))
        tex = SourceTexture(8, 8, pixels)
        baked = bake_face(tex, ((0, 0), (8, 0), (8, 8), (0, 8)), 8, colors=((0, 0, 0),) * 4)
        opaque = [p for p in baked.rgba if p[3] >= 128]
        transparent = [p for p in baked.rgba if p[3] < 128]
        self.assertTrue(opaque and transparent)
        self.assertTrue(all(p[:3] == (0, 0, 0) for p in opaque))

    def test_merge_coplanar_quads_preserves_winding_uv_and_color(self):
        verts = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 0.0, 10.0), (0.0, 0.0, 10.0)]
        # Two coplanar triangles sharing diagonal (0, 2) with opposite winding.
        faces = [(0, 1, 2, 2), (0, 2, 3, 3)]
        uvs = [((0.0, 0.0), (16.0, 0.0), (16.0, 16.0), (16.0, 16.0)),
               ((0.0, 0.0), (16.0, 16.0), (0.0, 16.0), (0.0, 16.0))]
        mats = [5, 5]
        cols = [((31, 31, 31), (20, 20, 20), (10, 10, 10), (10, 10, 10)),
                ((31, 31, 31), (10, 10, 10), (20, 20, 20), (20, 20, 20))]
        out_f, out_u, out_m, out_c, out_o, srcs = merge_coplanar_quads(verts, faces, uvs, mats, colors=cols)
        self.assertEqual(len(out_f), 1)
        self.assertNotEqual(out_f[0][2], out_f[0][3])
        self.assertEqual(out_m, [5])
        self.assertEqual(set(srcs[0]), {0, 1})
        # Verify corner colors and UVs stayed bound to their exact vertices.
        expected_uv = {0: (0.0, 0.0), 1: (16.0, 0.0), 2: (16.0, 16.0), 3: (0.0, 16.0)}
        expected_col = {0: (31, 31, 31), 1: (20, 20, 20), 2: (10, 10, 10), 3: (20, 20, 20)}
        for vi, uv, col in zip(out_f[0], out_u[0], out_c[0]):
            self.assertEqual(uv, expected_uv[vi])
            self.assertEqual(col, expected_col[vi])

        # Reject merge when shared-edge vertex color disagrees.
        bad_cols = [cols[0], ((0, 0, 0), (10, 10, 10), (20, 20, 20), (20, 20, 20))]
        out_f2, *_ = merge_coplanar_quads(verts, faces, uvs, mats, colors=bad_cols)
        self.assertEqual(len(out_f2), 2)

    def test_nonsquare_lut4_packing_and_adaptive_budget(self):
        # Striped brick-like texture 32x16 with transparent border.
        pixels = tuple(
            (240, 60, 40, 255) if (x // 4 + y // 4) % 2 == 0 else (180, 180, 180, 255)
            for y in range(16) for x in range(32)
        )
        tex = SourceTexture(32, 16, pixels, repeat_s=True, repeat_t=True)
        b = bake_face(tex, ((0, 0), (32, 0), (32, 16), (0, 16)), 16, height=8)
        self.assertEqual((b.width, b.height), (16, 8))
        textures, luts, lut_count, f_idx = index_bakes_lut4([b], groups=[(0, 2)])
        self.assertEqual(lut_count, 1)
        self.assertEqual(len(luts), 16)
        self.assertEqual(luts[0], 0x0000)
        self.assertTrue(all((c & 0x8000) != 0 for c in luts[1:] if c != 0))
        self.assertEqual(len(textures[0].pixels), 16 * 8 // 2)

        # Adaptive LUT4 honors tight budget and chooses non-square sizes for wide UVs.
        sources = [tex, tex]
        uvs = [((0, 0), (64, 0), (64, 16), (0, 16)), ((0, 0), (4, 0), (4, 4), (0, 4))]
        mats = [0, 1]
        cols = [((31, 31, 31),) * 4, ((16, 16, 16),) * 4]
        out_t, out_luts, n_luts, f_tex, sizes = adaptive_lut4_bakes(
            sources, uvs, mats, colors=cols, byte_budget=512, samples=1, max_size=32
        )
        vram = n_luts * 32 + sum((len(t.pixels) + 7) & ~7 for t in out_t)
        self.assertLessEqual(vram, 512)
        self.assertGreater(sizes[0][0], sizes[0][1])

    def test_sdk_split_interpolates_vertex_colors(self):
        sdk = ROOT.parent / 'lib-saturn'
        if not (sdk / 'tools/model_pipeline/intersections.py').is_file():
            self.skipTest('LibSaturn checkout not present')
        verts = [(0.0, 0.0, 0.0), (64.0, 0.0, 0.0), (64.0, 0.0, 64.0), (0.0, 0.0, 64.0)]
        faces = [(0, 1, 2, 3)]
        uvs = [((0.0, 0.0), (32.0, 0.0), (32.0, 32.0), (0.0, 32.0))]
        mats = [0]
        cols = [((0, 0, 0), (31, 0, 0), (31, 31, 0), (0, 31, 0))]
        pts, rf, ruv, rmat, orig, rcol = split_nearby(
            verts, faces, uvs, mats, sdk, center=(32, 32), radius=64, cell_size=32,
            pack_quads=True, colors=cols
        )
        self.assertEqual(len(rf), 4)
        # Every vertex's interpolated (r, g) must match (x/64*31, z/64*31).
        for face, fcol in zip(rf, rcol):
            for vi, c in zip(face, fcol):
                x, _, z = pts[vi]
                self.assertAlmostEqual(c[0], x / 64.0 * 31.0, places=3)
                self.assertAlmostEqual(c[1], z / 64.0 * 31.0, places=3)
                self.assertAlmostEqual(c[2], 0.0, places=3)

    def test_blz_decompress_and_castle_props(self):
        # Synthetic BLZ stream (read backwards): flags=0x08 -> 4 literals ('D','C','B','A'
        # written to out[15..12]), then bit 3 = backref (len=12 -> 9<<12, disp=4 -> 1)
        # copying "ABCD" three more times into out[11..0] -> b'ABCD' * 4.
        payload = bytes([0x01, 0x90, ord('A'), ord('B'), ord('C'), ord('D'), 0x08])
        footer = struct.pack('<II', (8 << 24) | 15, 1)
        self.assertEqual(blz_decompress(payload + footer), b'ABCD' * 4)

        rom = os.environ.get('SM64DS_ROM')
        if not rom or not Path(rom).is_file():
            self.skipTest('SM64DS_ROM not set')
        fs = Filesystem.from_file(Path(rom))
        trees, signs = extract_castle_props(fs)
        self.assertEqual(len(trees), 21)
        self.assertEqual(len(signs), 5)
        # First wooden sign sits near Mario's starting path around (-102.4, 16.3, 346.2).
        self.assertTrue(any(abs(s.position[0] + 102.4) < 1.0 and abs(s.position[2] - 346.2) < 1.0 for s in signs))


if __name__ == '__main__':
    unittest.main()
