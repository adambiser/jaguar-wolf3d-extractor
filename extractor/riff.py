import struct as _struct
import typing as _typing


def _uint32_to_bytes(value):
    return _struct.pack('<I', value)


def make_chunk(identifier: bytes, data: bytes):
    assert len(identifier) == 4
    if len(data) % 2 == 1:
        data += b'\x00'
    return identifier + _uint32_to_bytes(len(data)) + data


def _make_list_chunk(chunk_identifier: bytes, list_identifier: bytes, chunks: _typing.Iterable[bytes]):
    assert len(chunk_identifier) == 4
    assert len(list_identifier) == 4
    data = b''.join(chunks)
    return chunk_identifier + _uint32_to_bytes(len(data) + len(list_identifier)) + list_identifier + data


def make_list(identifier: bytes, chunks: _typing.Iterable[bytes]):
    return _make_list_chunk(b'LIST', identifier, chunks)


def make_riff(identifier: bytes, chunks: _typing.Iterable[bytes]):
    return _make_list_chunk(b'RIFF', identifier, chunks)
