"""Strict decoder for SM64DS-prefixed LZ10 streams."""
from __future__ import annotations
from .common import FormatError
MAX_OUTPUT=16*1024*1024

def lz77(data: bytes) -> bytes:
    """Strict SM64DS LZ77-wrapped LZ10 decoder; raw payloads pass through."""
    if data[:4] == b"LZ77":
        data = data[4:]
    else:
        return data  # Decompressed BCA data may itself begin with 0x10.
    if len(data) < 4 or data[0] != 0x10:
        raise FormatError("bad LZ10 header")
    total = int.from_bytes(data[1:4], 'little')
    if total == 0 or total > MAX_OUTPUT:
        raise FormatError(f"unsafe decompressed length: {total}")
    result = bytearray()
    pos = 4
    while len(result) < total:
        if pos >= len(data):
            raise FormatError("truncated LZ10 flag byte")
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if len(result) >= total:
                break
            if flags & (0x80 >> bit):
                if pos + 2 > len(data):
                    raise FormatError("truncated LZ10 back-reference")
                a, b = data[pos], data[pos + 1]
                pos += 2
                size = (a >> 4) + 3
                distance = (((a & 15) << 8) | b) + 1
                if distance > len(result) or len(result) + size > total:
                    raise FormatError("invalid LZ10 distance or output overrun")
                for _ in range(size):
                    result.append(result[-distance])
            else:
                if pos >= len(data):
                    raise FormatError("truncated LZ10 literal")
                result.append(data[pos])
                pos += 1
    return bytes(result)


