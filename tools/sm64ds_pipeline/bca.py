"""BCA keyframe, angle and translation sampling."""
from __future__ import annotations
from dataclasses import dataclass
from .common import FormatError,field,region
from .compression import lz77

@dataclass(frozen=True)
class Channel:
    shift: int
    animated: int
    index: int


class Animation:
    def __init__(self, blob: bytes, joints: int):
        data = lz77(blob)
        if len(data) < 0x18:
            raise FormatError("truncated BCA")
        self.data = data
        self.frames = field(data, 2, 'H')
        self.loop = bool(data[4])
        if self.frames < 1 or self.frames > 10000:
            raise FormatError("unsupported animation frame count")
        self.joints = joints
        self.pools = field(data, 8, 'III')
        base = field(data, 0x14, 'I')
        region(data, base, joints * 0x24)
        self.tracks = []
        for joint in range(joints):
            row = [Channel(*field(data, base + joint * 0x24 + i * 4, 'BBH')) for i in range(9)]
            if any(c.shift > 2 or c.animated not in (0, 1) for c in row):
                raise FormatError("unsupported BCA track shift or animation flag")
            self.tracks.append(row)

    def sample_channel(self, joint: int, channel: int, frame: int) -> int:
        if not (0 <= joint < self.joints and 0 <= channel < 9 and 0 <= frame < self.frames):
            raise FormatError("BCA channel/frame outside range")
        ch = self.tracks[joint][channel]
        p = self.pools[0 if channel < 3 else (1 if channel < 6 else 2)]
        is_rotation = 3 <= channel < 6
        kind = 'h' if is_rotation else 'i'
        width = 2 if is_rotation else 4

        def at(n: int):
            return field(self.data, p + (ch.index + n) * width, kind)

        if not ch.animated:
            return at(0)
        if not ch.shift:
            return at(frame)
        base = ((self.frames - 1) >> ch.shift) << ch.shift
        k = frame >> ch.shift
        if frame >= base:
            return at(k + frame - base)
        lo, hi = at(k), at(k + 1)
        rem = frame - (k << ch.shift)
        if rem == 0:
            return lo
        gap = 1 << ch.shift
        if is_rotation and abs(lo - hi) >= 0x800:
            if lo > hi:
                hi += 0x1000
            else:
                lo += 0x1000
            return ((lo * (gap - rem) + hi * rem) >> ch.shift) & 0xfff
        return (lo * (gap - rem) + hi * rem) >> ch.shift

    def sample(self, frame: int):
        out = []
        for joint in range(self.joints):
            scales = tuple(self.sample_channel(joint, k, frame) for k in range(3))
            rotations = tuple(self.sample_channel(joint, k, frame) for k in range(3, 6))
            translation = tuple(self.sample_channel(joint, k, frame) for k in range(6, 9))
            # BCA explicitly animates scale. The LibSaturn clip type has no
            # scale channel, so export a synchronized per-frame scale stream
            # consumed by our own world-matrix evaluator.
            out.append((translation, rotations, scales))
        return out


