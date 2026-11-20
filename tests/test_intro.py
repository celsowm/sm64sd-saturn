"""Tests for the SM64DS intro 2D, SDAT/ADX audio, and 3D asset pipeline."""
from __future__ import annotations

import math
import os
import struct
import tempfile
import unittest
from pathlib import Path

from tools.sm64ds_pipeline.compression import lz77_auto
from tools.sm64ds_pipeline.ds2d import (
    extract_cloud_atlas,
    render_mario3d_banner,
    render_peach_letter_card,
)
from tools.sm64ds_pipeline.filesystem import Filesystem
from tools.sm64ds_pipeline.sdat import (
    SdatArchive,
    encode_adx_payload,
    render_sseq_pcm_s16be,
    resample_wave_s8,
)
from tools.prepare_intro import prepare_intro


ROM_ENV = os.environ.get("SM64DS_ROM")


class TestIntroPipelineNoRom(unittest.TestCase):
    def test_lz77_auto_handles_raw_and_prefixed(self):
        # Raw uncompressed passthrough
        raw = b"\x00\x01\x02\x03"
        self.assertEqual(lz77_auto(raw), raw)
        # Minimal valid raw DS BIOS LZ10 stream: 4 literal bytes "TEST"
        lz_raw = bytes([0x10, 4, 0, 0, 0x00]) + b"TEST"
        self.assertEqual(lz77_auto(lz_raw), b"TEST")
        self.assertEqual(lz77_auto(b"LZ77" + lz_raw), b"TEST")

    def test_adx_payload_framing_on_synthetic_sine(self):
        rate = 22050
        frames = 3200
        pcm = bytearray(frames * 2)
        for i in range(frames):
            v = int(16000.0 * math.sin(2.0 * math.pi * 440.0 * i / rate))
            struct.pack_into(">h", pcm, i * 2, v)
        adx = encode_adx_payload(bytes(pcm), sample_rate=rate, channels=1)
        expected_bytes = 4 + ((frames + 31) // 32) * 18 * 1
        self.assertEqual(len(adx.payload), expected_bytes)
        self.assertEqual(adx.sample_rate, rate)
        self.assertEqual(adx.channels, 1)
        self.assertEqual(adx.sample_count, frames)
        self.assertTrue(-32768 <= adx.coeff1 <= 32767)
        self.assertTrue(-32768 <= adx.coeff2 <= 32767)


@unittest.skipUnless(ROM_ENV and Path(ROM_ENV).is_file(), "SM64DS_ROM not set")
class TestIntroPipelineWithRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Path(ROM_ENV)
        cls.fs = Filesystem.from_file(cls.rom)

    def test_ds2d_banners_and_peach_letter_card(self):
        title = render_mario3d_banner(
            self.fs, [("SUPER MARIO", "BGYRGYRGYR"), ("64 DS", "RBYRG")]
        )
        self.assertEqual(title.width % 8, 0)
        self.assertGreater(sum(1 for p in title.pixels if p & 0x8000), 1000)

        card = render_peach_letter_card(
            self.fs, ["Dear Mario:", "Please come to", "the castle."]
        )
        self.assertEqual(card.width % 8, 0)
        # Every pixel of the opaque parchment card must have bit 15 set for VDP1 direct color
        self.assertTrue(all(p & 0x8000 for p in card.pixels))

        clouds = extract_cloud_atlas(self.fs)
        self.assertEqual((clouds.width, clouds.height), (256, 128))
        self.assertEqual(len(clouds.pixels), 16384)
        self.assertEqual(len(clouds.palette), 16)

    def test_sdat_intro_tracks_and_voice_waves(self):
        sdat = SdatArchive(self.fs.read("data/sound_data.sdat"))
        peach_waves = sdat.decode_swar_waves(1)
        self.assertEqual(len(peach_waves), 6)
        for w in peach_waves:
            self.assertGreater(len(w.samples), 8000)
            s8 = resample_wave_s8(w, 16000)
            self.assertGreater(len(s8), 4000)

        for seq_name, ch, dur in [("NCS_BGM_TITLE", 2, 3.0), ("NCS_BGM_PEACH", 2, 4.0), ("NCS_BGM_OPENING", 1, 3.0)]:
            pcm, frames = render_sseq_pcm_s16be(sdat, seq_name, sample_rate=22050, channels=ch, max_seconds=dur)
            vals = struct.unpack(f">{len(pcm)//2}h", pcm)
            rms = math.sqrt(sum(v * v for v in vals[::16]) / max(1, len(vals[::16])))
            self.assertGreater(rms, 1000.0, f"{seq_name} rendered nearly silent")
            adx = encode_adx_payload(pcm, sample_rate=22050, channels=ch)
            self.assertEqual(len(adx.payload), 4 + ((frames + 31) // 32) * 18 * ch)

    def test_prepare_intro_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = prepare_intro(self.rom, out)
            self.assertEqual(summary["mario_face"]["bones"], 29)
            self.assertEqual(summary["peach_actor"]["bones"], 21)
            for rel in (
                "mario_face.h", "mario_face.c",
                "intro_star.h", "intro_star.c",
                "peach_actor.h", "peach_actor.c",
                "intro_2d.h", "intro_2d.c",
                "intro_audio.h", "intro_audio.c",
                "intro_audio_meta.h",
                "disc_audio/AUDIO/TITLE.ADX",
                "disc_audio/AUDIO/PEACH.ADX",
                "disc_audio/AUDIO/OPENING.ADX",
            ):
                self.assertTrue((out / rel).is_file(), f"missing generated file {rel}")


if __name__ == "__main__":
    unittest.main()
