"""Nintendo DS SDAT (SWAR/SBNK/SSEQ) parser, offline renderer, and LibSaturn ADX encoder."""
from __future__ import annotations

import math
import shutil
import struct
import subprocess
from array import array
from dataclasses import dataclass
from pathlib import Path

from .common import FormatError

# Standard IMA-ADPCM step and index tables (shared by Nintendo DS SWAV type 2)
IMA_STEP_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371,
    408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166,
    1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024,
    3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845,
    8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500,
    20350, 22385, 24623, 27086, 29794, 32767,
)
IMA_INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8)


@dataclass(frozen=True)
class DecodedWave:
    sample_rate: int
    loop: bool
    loop_start: int  # in samples
    samples: array   # signed 16-bit ('h')


@dataclass(frozen=True)
class NoteDef:
    swav_id: int
    swar_slot: int
    base_note: int
    attack: int
    decay: int
    sustain: int
    release: int
    pan: int


@dataclass(frozen=True)
class SbnkInstrument:
    kind: int  # 1=single, 16=drum range, 17=key split
    low_note: int = 0
    high_note: int = 127
    note_def: NoteDef | None = None
    drum_notes: tuple[NoteDef | None, ...] = ()
    split_regions: tuple[tuple[int, NoteDef | None], ...] = ()

    def resolve(self, note: int) -> NoteDef | None:
        if self.kind == 1:
            return self.note_def
        if self.kind == 16:
            if self.low_note <= note <= self.high_note:
                idx = note - self.low_note
                if 0 <= idx < len(self.drum_notes):
                    return self.drum_notes[idx]
            return None
        if self.kind == 17:
            for max_note, nd in self.split_regions:
                if note <= max_note:
                    return nd
            return self.split_regions[-1][1] if self.split_regions else None
        return None


@dataclass(frozen=True)
class AdxTrack:
    payload: bytes
    sample_rate: int
    channels: int
    sample_count: int
    coeff1: int
    coeff2: int


class SdatArchive:
    """Minimal read-only parser for Nintendo DS SDAT archives."""

    def __init__(self, blob: bytes):
        if len(blob) < 0x40 or blob[:4] != b"SDAT":
            raise FormatError("invalid SDAT header")
        self.blob = blob
        (
            self.symb_off,
            self.symb_size,
            self.info_off,
            self.info_size,
            self.fat_off,
            self.fat_size,
        ) = struct.unpack_from("<IIIIII", blob, 0x10)
        self.info_recs = struct.unpack_from("<8I", blob, self.info_off + 8)
        self.symb_recs = (
            struct.unpack_from("<8I", blob, self.symb_off + 8)
            if self.symb_size >= 40
            else (0,) * 8
        )
        self.seq_by_name = self._read_symbol_table(0)
        self.war_by_name = self._read_symbol_table(3)

    def _read_symbol_table(self, rec_idx: int) -> dict[str, int]:
        ro = self.symb_recs[rec_idx]
        if not ro:
            return {}
        base = self.symb_off + ro
        cnt = struct.unpack_from("<I", self.blob, base)[0]
        out: dict[str, int] = {}
        for i in range(cnt):
            soff = struct.unpack_from("<I", self.blob, base + 4 + i * 4)[0]
            if soff:
                end = self.blob.index(b"\x00", self.symb_off + soff)
                name = self.blob[self.symb_off + soff : end].decode("latin1")
                out[name] = i
        return out

    def read_fat(self, file_id: int) -> bytes:
        off, size = struct.unpack_from("<II", self.blob, self.fat_off + 12 + file_id * 16)
        if off + size > len(self.blob):
            raise FormatError(f"SDAT FAT file {file_id} out of range")
        return self.blob[off : off + size]

    def read_swar(self, war_index: int) -> bytes:
        war_base = self.info_off + self.info_recs[3]
        eoff = struct.unpack_from("<I", self.blob, war_base + 4 + war_index * 4)[0]
        if not eoff:
            raise FormatError(f"missing SWAR {war_index}")
        file_id = struct.unpack_from("<H", self.blob, self.info_off + eoff)[0]
        return self.read_fat(file_id)

    def decode_swar_waves(self, war_index: int) -> list[DecodedWave]:
        swar = self.read_swar(war_index)
        if len(swar) < 0x3C or swar[:4] != b"SWAR":
            raise FormatError(f"invalid SWAR {war_index}")
        nw = struct.unpack_from("<I", swar, 0x38)[0]
        offsets = [struct.unpack_from("<I", swar, 0x3C + i * 4)[0] for i in range(nw)]
        waves: list[DecodedWave] = []
        for i, woff in enumerate(offsets):
            wend = offsets[i + 1] if i + 1 < nw else len(swar)
            waves.append(decode_swav(swar[woff:wend]))
        return waves

    def read_seq_info(self, seq_index: int) -> tuple[bytes, int, int, tuple[int, ...]]:
        seq_base = self.info_off + self.info_recs[0]
        eoff = struct.unpack_from("<I", self.blob, seq_base + 4 + seq_index * 4)[0]
        if not eoff:
            raise FormatError(f"missing SSEQ {seq_index}")
        fid, _unk, bank_id, vol = struct.unpack_from("<HHHB", self.blob, self.info_off + eoff)
        sseq = self.read_fat(fid)
        bnk_base = self.info_off + self.info_recs[2]
        beoff = struct.unpack_from("<I", self.blob, bnk_base + 4 + bank_id * 4)[0]
        bfid, _bunk, w0, w1, w2, w3 = struct.unpack_from("<HH4H", self.blob, self.info_off + beoff)
        sbnk = self.read_fat(bfid)
        return sseq, bank_id, vol, (w0, w1, w2, w3), sbnk


def decode_swav(data: bytes) -> DecodedWave:
    """Decode one Nintendo DS SWAV block (PCM8, PCM16, or IMA-ADPCM) to int16 PCM."""
    if len(data) < 12:
        raise FormatError("truncated SWAV")
    wtype, loop_flag, rate, _time, loop_start_w, nonloop_w = struct.unpack_from("<BBHHHI", data, 0)
    raw_len = (loop_start_w + nonloop_w) * 4
    payload = data[12 : 12 + raw_len]
    samples = array("h")
    if wtype == 0:
        # Signed 8-bit PCM
        for b in payload:
            s = b - 256 if b >= 128 else b
            samples.append(s << 8)
        loop_start = loop_start_w * 4
    elif wtype == 1:
        # Signed 16-bit little-endian PCM
        n = len(payload) // 2
        samples.extend(struct.unpack_from(f"<{n}h", payload, 0))
        loop_start = loop_start_w * 2
    elif wtype == 2:
        # Nintendo DS IMA-ADPCM: 4-byte header (s16 predictor, u8 index, u8 pad), low nibble first
        if len(payload) < 4:
            return DecodedWave(rate, bool(loop_flag), 0, samples)
        pred, idx = struct.unpack_from("<hB", payload, 0)
        idx = max(0, min(88, idx))
        for b in payload[4:]:
            for nib in (b & 0xF, (b >> 4) & 0xF):
                step = IMA_STEP_TABLE[idx]
                diff = step >> 3
                if nib & 1:
                    diff += step >> 2
                if nib & 2:
                    diff += step >> 1
                if nib & 4:
                    diff += step
                if nib & 8:
                    pred -= diff
                else:
                    pred += diff
                if pred > 32767:
                    pred = 32767
                elif pred < -32768:
                    pred = -32768
                idx += IMA_INDEX_TABLE[nib & 7]
                if idx < 0:
                    idx = 0
                elif idx > 88:
                    idx = 88
                samples.append(pred)
        # loop_start_w counts 32-bit words INCLUDING the 4-byte ADPCM header
        loop_start = max(0, (loop_start_w - 1) * 8)
    else:
        raise FormatError(f"unsupported SWAV type: {wtype}")
    return DecodedWave(
        sample_rate=rate,
        loop=bool(loop_flag),
        loop_start=min(loop_start, max(0, len(samples) - 1)),
        samples=samples,
    )


def resample_wave_s16(wave: DecodedWave, target_rate: int) -> array:
    """Linearly resample a mono int16 wave to target_rate."""
    src = wave.samples
    if not src or wave.sample_rate <= 0:
        return array("h")
    if wave.sample_rate == target_rate:
        return array("h", src)
    ratio = wave.sample_rate / float(target_rate)
    out_len = max(1, int(round(len(src) / ratio)))
    out = array("h", [0] * out_len)
    last = len(src) - 1
    for i in range(out_len):
        pos = i * ratio
        i0 = int(pos)
        if i0 >= last:
            out[i] = src[last]
        else:
            frac = pos - i0
            out[i] = int(src[i0] + (src[i0 + 1] - src[i0]) * frac)
    return out


def resample_wave_s8(wave: DecodedWave, target_rate: int) -> bytes:
    """Resample a mono wave to signed 8-bit PCM bytes for compact SCSP Sound RAM storage."""
    s16 = resample_wave_s16(wave, target_rate)
    return bytes(((s >> 8) & 0xFF) for s in s16)


def _read_note_def(data: bytes, off: int) -> NoteDef:
    swav_id, swar_slot, base_note, atk, dec, sus, rel, pan = struct.unpack_from("<HHBBBBBB", data, off)
    return NoteDef(swav_id, swar_slot, base_note, atk, dec, sus, rel, pan)


def parse_sbnk(data: bytes) -> list[SbnkInstrument | None]:
    """Parse Nintendo DS SBNK instrument records (types 1, 16, 17)."""
    if len(data) < 0x3C or data[:4] != b"SBNK":
        raise FormatError("invalid SBNK header")
    ninst = struct.unpack_from("<I", data, 0x38)[0]
    insts: list[SbnkInstrument | None] = []
    for i in range(ninst):
        rec = struct.unpack_from("<I", data, 0x3C + i * 4)[0]
        kind = rec & 0xFF
        off = (rec >> 8) & 0xFFFF
        if kind == 0 or off == 0 or off >= len(data):
            insts.append(None)
        elif kind == 1:
            insts.append(SbnkInstrument(kind=1, note_def=_read_note_def(data, off)))
        elif kind == 16:
            low, high = data[off], data[off + 1]
            p = off + 2
            notes: list[NoteDef | None] = []
            for _ in range(high - low + 1):
                sub_t = struct.unpack_from("<H", data, p)[0]
                p += 2
                nd = _read_note_def(data, p) if (sub_t & 0xFF) == 1 else None
                p += 10
                notes.append(nd)
            insts.append(SbnkInstrument(kind=16, low_note=low, high_note=high, drum_notes=tuple(notes)))
        elif kind == 17:
            bounds = list(data[off : off + 8])
            count = 0
            for b in bounds:
                if b == 0:
                    break
                count += 1
            p = off + 8
            regions: list[tuple[int, NoteDef | None]] = []
            for r in range(count):
                sub_t = struct.unpack_from("<H", data, p)[0]
                p += 2
                nd = _read_note_def(data, p) if (sub_t & 0xFF) == 1 else None
                p += 10
                regions.append((bounds[r], nd))
            insts.append(SbnkInstrument(kind=17, split_regions=tuple(regions)))
        else:
            insts.append(None)
    return insts


def _read_vlq(data: bytes, pos: int) -> tuple[int, int]:
    val = 0
    for _ in range(4):
        b = data[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    return val, pos


@dataclass
class _NoteEvent:
    start_sec: float
    dur_sec: float
    note: int
    vel: int
    program: int
    vol: int
    expr: int
    pan: int
    transpose: int
    bend: int
    bend_range: int


def _collect_sseq_events(sseq: bytes, *, max_seconds: float) -> tuple[list[_NoteEvent], float]:
    """Execute SSEQ bytecode across all tracks and collect timed note events."""
    if len(sseq) < 0x1C or sseq[:4] != b"SSEQ":
        raise FormatError("invalid SSEQ header")
    data_off = struct.unpack_from("<I", sseq, 0x18)[0]
    body = sseq[data_off:]

    # Track state
    tracks: dict[int, dict] = {
        0: {
            "pos": 0,
            "tick": 0,
            "program": 0,
            "vol": 127,
            "expr": 127,
            "pan": 64,
            "transpose": 0,
            "bend": 0,
            "bend_range": 2,
            "stack": [],
            "loop_stack": [],
            "jumps": 0,
            "ended": False,
        }
    }
    tempo_changes: list[tuple[int, int]] = [(0, 120)]  # (tick, bpm)
    raw_notes: list[tuple[int, int, int, int, int, int, int, int, int, int, int]] = []

    def tick_to_sec(target_tick: int) -> float:
        sec = 0.0
        prev_t = 0
        bpm = 120
        for t, nbpm in tempo_changes:
            if t >= target_tick:
                break
            sec += (t - prev_t) * (60.0 / (bpm * 48.0))
            prev_t = t
            bpm = max(20, nbpm)
        sec += (target_tick - prev_t) * (60.0 / (bpm * 48.0))
        return sec

    # Approximate max ticks conservatively (will trim exact seconds later)
    max_ticks = int(max_seconds * 48.0 * 4.0) + 192

    # Step active tracks in chronological tick order
    step_guard = 0
    while step_guard < 250000:
        step_guard += 1
        active = [tid for tid, tr in tracks.items() if not tr["ended"] and tr["tick"] <= max_ticks]
        if not active:
            break
        tid = min(active, key=lambda i: (tracks[i]["tick"], i))
        tr = tracks[tid]
        pos = tr["pos"]
        if pos >= len(body):
            tr["ended"] = True
            continue
        op = body[pos]
        pos += 1
        if op < 0x80:
            vel = body[pos]
            pos += 1
            dur, pos = _read_vlq(body, pos)
            raw_notes.append((
                tr["tick"], dur, op, vel, tr["program"],
                tr["vol"], tr["expr"], tr["pan"], tr["transpose"], tr["bend"], tr["bend_range"]
            ))
        elif op == 0x80:
            wait, pos = _read_vlq(body, pos)
            tr["tick"] += wait
        elif op == 0x81:
            prog, pos = _read_vlq(body, pos)
            tr["program"] = prog
        elif op == 0x93:
            child_id = body[pos]
            off = body[pos + 1] | (body[pos + 2] << 8) | (body[pos + 3] << 16)
            pos += 4
            tracks[child_id] = {
                "pos": off,
                "tick": tr["tick"],
                "program": 0,
                "vol": 127,
                "expr": 127,
                "pan": 64,
                "transpose": 0,
                "bend": 0,
                "bend_range": 2,
                "stack": [],
                "loop_stack": [],
                "jumps": 0,
                "ended": False,
            }
        elif op == 0x94:
            off = body[pos] | (body[pos + 1] << 8) | (body[pos + 2] << 16)
            pos += 3
            tr["jumps"] += 1
            if tr["jumps"] > 32 or tick_to_sec(tr["tick"]) >= max_seconds:
                tr["ended"] = True
            else:
                pos = off
        elif op == 0x95:
            off = body[pos] | (body[pos + 1] << 8) | (body[pos + 2] << 16)
            pos += 3
            tr["stack"].append(pos)
            pos = off
        elif op == 0xA0:
            # Random parameter prefix: subop + 4 bytes min/max
            sub = body[pos]
            pos += 1
            if sub < 0x80:
                pos += 1 + 4
            else:
                pos += 4
        elif op == 0xA1:
            # Variable parameter prefix
            sub = body[pos]
            pos += 1
            pos += 2 if sub < 0x80 else 1
        elif op == 0xA2:
            # Conditional prefix (skip flag, execute next)
            pass
        elif 0xB0 <= op <= 0xBD:
            pos += 3
        elif op == 0xC0:
            tr["pan"] = body[pos]
            pos += 1
        elif op == 0xC1:
            tr["vol"] = body[pos]
            pos += 1
        elif op == 0xC2:
            pos += 1  # master vol
        elif op == 0xC3:
            tr["transpose"] = struct.unpack_from("<b", body, pos)[0]
            pos += 1
        elif op == 0xC4:
            tr["bend"] = struct.unpack_from("<b", body, pos)[0]
            pos += 1
        elif op == 0xC5:
            tr["bend_range"] = body[pos]
            pos += 1
        elif 0xC6 <= op <= 0xD3:
            pos += 1
        elif op == 0xD4:
            cnt = body[pos]
            pos += 1
            tr["loop_stack"].append([pos, cnt])
        elif op == 0xD5:
            tr["expr"] = body[pos]
            pos += 1
        elif op == 0xD6:
            pos += 1
        elif op == 0xE0:
            pos += 2
        elif op == 0xE1:
            bpm = struct.unpack_from("<H", body, pos)[0]
            pos += 2
            if not tempo_changes or tempo_changes[-1][0] != tr["tick"]:
                tempo_changes.append((tr["tick"], max(20, bpm)))
            else:
                tempo_changes[-1] = (tr["tick"], max(20, bpm))
        elif op == 0xE3:
            pos += 2
        elif op == 0xFC:
            if tr["loop_stack"]:
                top = tr["loop_stack"][-1]
                if top[1] == 0:
                    if tick_to_sec(tr["tick"]) >= max_seconds:
                        tr["loop_stack"].pop()
                    else:
                        pos = top[0]
                elif top[1] > 1:
                    top[1] -= 1
                    pos = top[0]
                else:
                    tr["loop_stack"].pop()
        elif op == 0xFD:
            if tr["stack"]:
                pos = tr["stack"].pop()
            else:
                tr["ended"] = True
        elif op == 0xFE:
            pos += 2  # track allocation bitmask
        elif op == 0xFF:
            tr["ended"] = True
        else:
            # Unknown opcode: stop track safely
            tr["ended"] = True
        tr["pos"] = pos

    tempo_changes.sort(key=lambda x: x[0])
    events: list[_NoteEvent] = []
    max_end = 0.0
    for tick, dur, note, vel, prog, vol, expr, pan, transp, bend, brange in raw_notes:
        t0 = tick_to_sec(tick)
        if t0 >= max_seconds:
            continue
        t1 = min(max_seconds, tick_to_sec(tick + max(1, dur)))
        events.append(_NoteEvent(
            start_sec=t0,
            dur_sec=max(0.015, t1 - t0),
            note=note,
            vel=vel,
            program=prog,
            vol=vol,
            expr=expr,
            pan=pan,
            transpose=transp,
            bend=bend,
            bend_range=brange,
        ))
        if t1 > max_end:
            max_end = t1
    return events, min(max_seconds, max_end + 0.35)


def render_sseq_pcm_s16be(
    sdat: SdatArchive,
    seq_name_or_index: str | int,
    *,
    sample_rate: int = 22050,
    channels: int = 2,
    max_seconds: float = 18.0,
) -> tuple[bytes, int]:
    """Synthesize an SDAT SSEQ track offline using its authentic SBNK/SWAR samples.

    Returns (big_endian_s16_pcm_bytes, frame_count).
    """
    seq_idx = (
        sdat.seq_by_name[seq_name_or_index]
        if isinstance(seq_name_or_index, str)
        else seq_name_or_index
    )
    sseq, _bank_id, seq_vol, war_ids, sbnk = sdat.read_seq_info(seq_idx)
    insts = parse_sbnk(sbnk)
    swar_waves: dict[int, list[DecodedWave]] = {}
    for slot, wid in enumerate(war_ids):
        if wid != 0xFFFF:
            swar_waves[slot] = sdat.decode_swar_waves(wid)

    events, total_sec = _collect_sseq_events(sseq, max_seconds=max_seconds)
    total_frames = max(32, int(math.ceil(total_sec * sample_rate)))
    # Align to 32-frame ADX blocks
    total_frames = ((total_frames + 31) // 32) * 32

    mix_l = [0.0] * total_frames
    mix_r = [0.0] * total_frames if channels == 2 else mix_l
    seq_gain = (seq_vol / 127.0) ** 1.4

    for ev in events:
        if ev.program >= len(insts) or insts[ev.program] is None:
            continue
        nd = insts[ev.program].resolve(ev.note)
        if nd is None:
            continue
        waves = swar_waves.get(nd.swar_slot)
        if not waves or nd.swav_id >= len(waves):
            continue
        w = waves[nd.swav_id]
        src = w.samples
        n_src = len(src)
        if n_src < 2:
            continue

        semitones = (ev.note + ev.transpose - nd.base_note) + (ev.bend / 127.0) * ev.bend_range
        step = (w.sample_rate / float(sample_rate)) * (2.0 ** (semitones / 12.0))
        if step <= 0.001 or step > 32.0:
            continue

        # DS quadratic velocity/volume curve
        amp = (
            seq_gain
            * ((ev.vel / 127.0) ** 1.6)
            * ((ev.vol / 127.0) ** 1.5)
            * ((ev.expr / 127.0) ** 1.5)
            * 0.34
        )
        if amp < 1e-4:
            continue

        pan_val = (ev.pan + nd.pan - 64)
        pan_f = max(0.0, min(1.0, pan_val / 127.0))
        if channels == 2:
            gain_l = amp * math.cos(pan_f * math.pi * 0.5)
            gain_r = amp * math.sin(pan_f * math.pi * 0.5)
        else:
            gain_l = amp
            gain_r = amp

        start_frame = int(ev.start_sec * sample_rate)
        hold_frames = max(1, int(ev.dur_sec * sample_rate))
        # Soft release tail scaled from DS release byte (0..127; higher = faster release)
        rel_sec = max(0.03, min(0.45, (128 - nd.release) / 260.0))
        rel_frames = int(rel_sec * sample_rate)
        atk_frames = max(1, int(max(0.0, (127 - nd.attack) / 400.0) * sample_rate))
        sus_level = max(0.25, min(1.0, nd.sustain / 127.0))

        end_frame = min(total_frames, start_frame + hold_frames + rel_frames)
        loop_start = w.loop_start
        loop_len = n_src - loop_start
        pos = 0.0
        for f in range(start_frame, end_frame):
            age = f - start_frame
            if age < atk_frames:
                env = (age + 1) / float(atk_frames)
            elif age < hold_frames:
                # Gentle decay toward sustain
                decay_t = (age - atk_frames) / float(max(1, hold_frames))
                env = 1.0 - (1.0 - sus_level) * min(1.0, decay_t * 0.7)
            else:
                rel_t = (age - hold_frames) / float(max(1, rel_frames))
                env = sus_level * max(0.0, 1.0 - rel_t)

            if pos >= n_src - 1:
                if w.loop and loop_len > 1:
                    pos = loop_start + ((pos - loop_start) % loop_len)
                else:
                    break
            i0 = int(pos)
            frac = pos - i0
            i1 = i0 + 1
            if i1 >= n_src:
                i1 = loop_start if (w.loop and loop_len > 1) else (n_src - 1)
            val = (src[i0] + (src[i1] - src[i0]) * frac) * env
            if channels == 2:
                mix_l[f] += val * gain_l
                mix_r[f] += val * gain_r
            else:
                mix_l[f] += val * gain_l
            pos += step

    # Normalize cleanly to ~85% full scale so output is loud, clear, and never clips
    peak = max(
        max((abs(v) for v in mix_l), default=1.0),
        max((abs(v) for v in mix_r), default=1.0) if channels == 2 else 1.0,
    )
    scale = (28000.0 / peak) if peak > 1.0 else 1.0

    # Gentle 15ms fade-in/out at boundaries to eliminate clicks on loop/stop
    edge = min(330, total_frames // 8)
    out = bytearray(total_frames * channels * 2)
    pack_into = struct.pack_into
    for f in range(total_frames):
        fade = 1.0
        if f < edge:
            fade = f / float(edge)
        elif f >= total_frames - edge:
            fade = (total_frames - 1 - f) / float(edge)
        s = scale * fade
        if channels == 2:
            vl = max(-32767, min(32767, int(mix_l[f] * s)))
            vr = max(-32767, min(32767, int(mix_r[f] * s)))
            pack_into(">hh", out, f * 4, vl, vr)
        else:
            vm = max(-32767, min(32767, int(mix_l[f] * s)))
            pack_into(">h", out, f * 2, vm)
    return bytes(out), total_frames


def encode_adx_payload(
    pcm_s16be: bytes,
    *,
    sample_rate: int = 22050,
    channels: int = 2,
    ffmpeg: str | None = None,
) -> AdxTrack:
    """Encode big-endian S16 PCM to LibSaturn's SAT_AUDIO_ADX_ADPCM format via FFmpeg."""
    ffmpeg_bin = ffmpeg or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    frame_bytes = channels * 2
    if not pcm_s16be or (len(pcm_s16be) % frame_bytes) != 0:
        raise FormatError("invalid PCM byte length for ADX encoding")
    sample_count = len(pcm_s16be) // frame_bytes
    command = [
        ffmpeg_bin, "-v", "error", "-f", "s16be", "-ar", str(sample_rate),
        "-ac", str(channels), "-i", "pipe:0", "-c:a", "adpcm_adx",
        "-f", "adx", "pipe:1",
    ]
    encoded = subprocess.run(command, input=pcm_s16be, check=True, stdout=subprocess.PIPE).stdout
    if len(encoded) < 36 or encoded[:2] != b"\x80\x00" or encoded[4:8] != bytes((3, 18, 4, channels)):
        raise FormatError("FFmpeg did not generate CRI ADX encoding 3")
    data_offset = int.from_bytes(encoded[2:4], "big") + 4
    if (
        data_offset < 24
        or encoded[data_offset - 6 : data_offset] != b"(c)CRI"
        or int.from_bytes(encoded[8:12], "big") != sample_rate
    ):
        raise FormatError("unexpected CRI ADX header")
    data_bytes = ((sample_count + 31) // 32) * 18 * channels
    if len(encoded) < data_offset + data_bytes:
        raise FormatError("truncated ADX output")
    cutoff = int.from_bytes(encoded[16:18], "big")
    if cutoff <= 0 or sample_rate <= 2 * cutoff:
        raise FormatError(f"invalid ADX cutoff {cutoff} for rate {sample_rate}")
    a = math.sqrt(2.0) - math.cos(2.0 * math.pi * cutoff / sample_rate)
    b = math.sqrt(2.0) - 1.0
    c = (a - math.sqrt((a + b) * (a - b))) / b
    coeff1 = round(c * 2.0 * 4096)
    coeff2 = round(-c * c * 4096)
    if not (-32768 <= coeff1 <= 32767 and -32768 <= coeff2 <= 32767):
        raise FormatError("ADX LPC coefficient overflow")
    payload = struct.pack(">hh", coeff1, coeff2) + encoded[data_offset : data_offset + data_bytes]
    return AdxTrack(
        payload=payload,
        sample_rate=sample_rate,
        channels=channels,
        sample_count=sample_count,
        coeff1=coeff1,
        coeff2=coeff2,
    )
