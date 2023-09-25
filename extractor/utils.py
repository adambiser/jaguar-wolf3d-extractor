import struct


def read_ubyte(f) -> int:
    return struct.unpack('<B', f.read(1))[0]


def read_ushort(f) -> int:
    return struct.unpack('<H', f.read(2))[0]


def write_short(f, x: int):
    """Writes a signed short"""
    f.write(struct.pack('<h', x))


def write_int(f, x: int):
    """Writes a signed integer."""
    f.write(struct.pack('<i', x))
