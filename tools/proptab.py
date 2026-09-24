#!/usr/bin/env python3
"""Dump ACPd's ACP property table.

`FUN_00807418` (the property lookup) walks a flat array of 12-byte records
{fourcc, type, flags} starting at VMA 0xc5af38 and ending at a zero fourcc.
VMA = file offset + 0x400000.

Usage: python3 tools/proptab.py ACPd.bin [fourcc ...]

ACPd.bin is Apple firmware and is NOT shipped with this repo - pull it off your own
base station first (see docs/extracting-acpd.md).
"""
import os
import struct
import sys

BASE = 0x400000
TABLE_VMA = 0xc5af38

TYPES = {1: 'byte', 2: 'string', 5: 'uint32', 6: 'bool', 7: 'ipv4', 8: 'mac',
         9: 'phys', 10: 'action', 12: 'ipv6', 13: 'data'}
# flag bits checked by ACPGetPropertyDirect / ACPSetPropertyDirectEx
FLAGS = {0x04: 'set-needs-priv', 0x08: 'set-needs-auth', 0x10: 'set-forces-flag-0x10',
         0x20: 'set-refused', 0x40: 'handler-only(0x40)', 0x80: 'handler-only(0x80)'}


def entries(path):
    data = open(path, 'rb').read()
    off = TABLE_VMA - BASE
    while True:
        fourcc = data[off:off + 4]
        if fourcc == b'\0\0\0\0' or len(fourcc) < 4:
            return
        typ, flags = struct.unpack('>II', data[off + 4:off + 12])
        yield off + BASE, fourcc.decode('latin1'), typ, flags
        off += 12


def main():
    args = sys.argv[1:]
    if not args or not os.path.exists(args[0]):
        sys.exit('usage: proptab.py /path/to/ACPd.bin [fourcc ...]   '
                 '(see docs/extracting-acpd.md)')
    path = args[0]
    wanted = set(args[1:])
    n = 0
    for vma, fourcc, typ, flags in entries(path):
        n += 1
        if wanted and fourcc not in wanted:
            continue
        names = ' '.join(v for k, v in FLAGS.items() if flags & k) or '-'
        print(f'0x{vma:08x}  {fourcc!r:8} type={typ:<2} ({TYPES.get(typ, "?"):8}) '
              f'flags=0x{flags:02x} {names}')
    if not wanted:
        print(f'### {n} properties')


if __name__ == '__main__':
    main()
