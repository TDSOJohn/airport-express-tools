"""AirPort CFL binary plist ('CFB0' ... 'END!') parse/compose, ported from airpyrt-tools.

Mapping: data <-> bytes, UTF-8 string <-> str, int, bool, None, array <-> list, dict <-> dict.
"""
import struct

HEADER, FOOTER = b'CFB0', b'END!'


def _pack(obj):
    if obj is None:
        return b'\x00'
    if isinstance(obj, bool):
        return b'\x09' if obj else b'\x08'
    if isinstance(obj, int):
        if obj < 0:                     # like bplist: only the 8-byte form is signed
            if obj < -(1 << 63):
                raise ValueError(f'int too small: {obj}')
            return b'\x13' + struct.pack('>q', obj)
        for exp, fmt in enumerate(('>B', '>H', '>I', '>Q')):
            if obj < (1 << (8 << exp)):
                return bytes([0x10 + exp]) + struct.pack(fmt, obj)
        raise ValueError(f'int too large: {obj}')
    if isinstance(obj, float):
        return b'\x22' + struct.pack('>f', obj)
    if isinstance(obj, (bytes, bytearray)):
        n = len(obj)
        return (bytes([0x40 + n]) if n < 0xF else b'\x4f' + _pack(n)) + bytes(obj)
    if isinstance(obj, str):
        return b'\x70' + obj.encode('utf-8') + b'\x00'
    if isinstance(obj, (list, tuple)):
        return b'\xa0' + b''.join(_pack(e) for e in obj) + b'\x00'
    if isinstance(obj, dict):
        return b'\xd0' + b''.join(_pack(k) + _pack(v) for k, v in obj.items()) + b'\x00'
    raise TypeError(f'unsupported type: {type(obj)}')


def _unpack(data, i):
    marker = data[i]
    i += 1
    kind, info = marker & 0xF0, marker & 0x0F
    if kind == 0x00:
        if info in (0, 8, 9):
            return {0: None, 8: False, 9: True}[info], i
    elif kind == 0x10:
        size = 1 << info
        # 1/2/4-byte ints are unsigned, 8-byte ones signed (ACPd sends -52 dBm, -6727 so)
        return int.from_bytes(data[i:i + size], 'big', signed=size == 8), i + size
    elif kind == 0x20:
        size = 1 << info
        return struct.unpack('>f' if size == 4 else '>d', data[i:i + size])[0], i + size
    elif kind == 0x40:
        n = info
        if info == 0xF:
            count_marker = data[i]
            if count_marker & 0xF0 != 0x10:
                raise ValueError('expected int object for data length')
            size = 1 << (count_marker & 0x0F)
            n = int.from_bytes(data[i + 1:i + 1 + size], 'big')
            i += 1 + size
        return bytes(data[i:i + n]), i + n
    elif kind == 0x70:
        end = data.index(0, i)
        return data[i:end].decode('utf-8'), end + 1
    elif kind == 0xA0:
        out = []
        while data[i] != 0:
            element, i = _unpack(data, i)
            out.append(element)
        return out, i + 1
    elif kind == 0xD0:
        out = {}
        while data[i] != 0:
            key, i = _unpack(data, i)
            out[key], i = _unpack(data, i)
        return out, i + 1
    raise ValueError(f'unsupported CFL object marker 0x{marker:02x} at offset {i - 1}')


def parse(data):
    if data[:4] != HEADER:
        raise ValueError(f'bad CFL header {data[:4]!r}')
    obj, i = _unpack(data, 4)
    if data[i:] != FOOTER:
        raise ValueError(f'bad CFL footer {data[i:i + 8]!r}')
    return obj


def compose(obj):
    return HEADER + _pack(obj) + FOOTER
