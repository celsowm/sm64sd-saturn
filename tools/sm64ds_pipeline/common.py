"""Shared bounded binary and fixed-point helpers."""
from __future__ import annotations
import math
import struct

class FormatError(ValueError):
    """Input cannot be safely or faithfully converted."""


def field(data: bytes, at: int, fmt: str):
    n = struct.calcsize(fmt)
    if at < 0 or at + n > len(data):
        raise FormatError(f"truncated buffer at 0x{at:x}, requires {n} bytes")
    return struct.unpack_from("<" + fmt, data, at)[0] if len(fmt) == 1 else struct.unpack_from("<" + fmt, data, at)


def region(data: bytes, offset: int, size: int) -> bytes:
    if size < 0 or offset < 0 or offset + size > len(data):
        raise FormatError(f"invalid span 0x{offset:x}+{size} in {len(data)} bytes")
    return data[offset:offset + size]


def signed10(n: int) -> int:
    n &= 1023
    return n - 1024 if n & 512 else n


def signed16(n: int) -> int:
    n &= 65535
    return n - 65536 if n & 32768 else n


def checked_fx(raw20_12: int) -> int:
    result = raw20_12 * 16  # 20.12 -> 16.16: never a reinterpret cast.
    if not -(2**31) <= result < 2**31:
        raise FormatError("20.12 -> 16.16 overflow; needs coordinate origin/scale")
    return result


def quaternion(angles: tuple[int, int, int]) -> tuple[int, int, int, int]:
    """Match func_02045178 XYZ Euler row matrix; transpose to LibSaturn basis."""
    ax, ay, az = (2.0 * math.pi * (v & 0xfff) / 4096.0 for v in angles)
    a0, a1 = math.sin(ax), math.cos(ax)
    b0, b1 = math.sin(ay), math.cos(ay)
    c0, c1 = math.sin(az), math.cos(az)
    # Source matrix: row-vector convention, transpose for standard quaternion.
    row = [[b1*c1, b1*c0, -b0],
           [b0*a0*c1 - a1*c0, a1*c1 + b0*a0*c0, b1*a0],
           [a0*c0 + b0*a1*c1, b0*a1*c0 - a0*c1, b1*a1]]
    m = [[row[c][r] for c in range(3)] for r in range(3)]
    trace = sum(m[i][i] for i in range(3))
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = ((m[2][1]-m[1][2])/s, (m[0][2]-m[2][0])/s,
             (m[1][0]-m[0][1])/s, s/4)
    else:
        k = max(range(3), key=lambda i: m[i][i]); j=(k+1)%3; l=(k+2)%3
        s = math.sqrt(1.0 + m[k][k] - m[j][j] - m[l][l]) * 2
        qv = [0.0]*4; qv[k] = s/4
        qv[3] = (m[l][j] - m[j][l]) / s
        qv[j] = (m[k][j] + m[j][k]) / s
        qv[l] = (m[k][l] + m[l][k]) / s
        q = tuple(qv)
    norm = math.sqrt(sum(x*x for x in q))
    return tuple(max(-32767, min(32767, round(x/norm*32767))) for x in q)


