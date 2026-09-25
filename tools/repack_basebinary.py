#!/usr/bin/env python3
"""Rebuild an A1392 ".basebinary" after replacing a file inside its md0 RAM disk (offline).

The reverse of decrypt_basebinary.py. The inner container's plaintext is a gzboot loader
followed by a gzip'd kernel image (with the md0 FFS root embedded in it) and zero padding
to a 4-byte boundary. The loader stores no lengths, so the gzip stream can be regenerated.
zlib level 9 reproduces Apple's deflate stream byte-for-byte, which `roundtrip` checks.

Usage:
    repack_basebinary.py roundtrip IN.basebinary
        unpack and repack without changes; must reproduce IN exactly
    repack_basebinary.py replace IN.basebinary /path/in/ramdisk NEWFILE OUT.basebinary
        swap one regular file's contents and write a new image

`replace` edits in place: the new contents must fit in the fragments already allocated to
that file (direct blocks only), so no FFS allocation is needed. Only di_size changes.
Container headers (model, version, flags) are copied from IN. The only integrity check at
flash and boot time is Adler-32 (see docs/boot.md), which this tool recomputes.
"""
import struct, sys, zlib

from decrypt_basebinary import HDR, MAGIC, _derive_key, parse
from ufs1 import UFS1, IFMT, IFREG

try:
    from Cryptodome.Cipher import AES
except ImportError:
    from Crypto.Cipher import AES


def _encrypt(data, key, iv):
    out = bytearray()
    for off in range(0, len(data), 0x8000):
        chunk = data[off:off + 0x8000]
        body = len(chunk) & ~0xf
        out += AES.new(key, AES.MODE_CBC, iv).encrypt(chunk[:body])
        out += chunk[body:]                    # sub-16 tail stays in the clear
    return bytes(out)


def _wrap(header, payload):
    """Build one container from a template header and a plaintext payload."""
    magic, b0f, model, *_ , flags, _unk = HDR.unpack(header)
    adler = zlib.adler32(header + payload) & 0xffffffff
    if flags & 2:
        payload = _encrypt(payload, _derive_key(model), MAGIC + bytes([b0f]))
    return header + payload + struct.pack(">I", adler)


def split(data):
    """Return (outer_hdr, inner_hdr, loader, gzip_header, image) for a .basebinary."""
    inner = parse(data, "outer")
    plain = parse(inner, "inner")
    gz = plain.find(b"\x1f\x8b\x08")
    name_end = plain.index(b"\0", gz + 10) + 1     # gzip FNAME is set by Apple's build
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    image = d.decompress(plain[gz:])
    if d.unused_data.strip(b"\0"):
        raise SystemExit("unexpected data after the gzip stream")
    return data[:HDR.size], inner[:HDR.size], plain[:gz], plain[gz:name_end], image


def join(outer_hdr, inner_hdr, loader, gz_hdr, image):
    c = zlib.compressobj(9, zlib.DEFLATED, -15, 8)
    stream = gz_hdr + c.compress(image) + c.flush() + struct.pack(
        "<II", zlib.crc32(image) & 0xffffffff, len(image) & 0xffffffff)
    plain = loader + stream
    plain += b"\0" * (-len(plain) % 4)
    return _wrap(outer_hdr, _wrap(inner_hdr, plain))


def replace_file(image, path, new):
    img = bytearray(image)
    fs = UFS1(bytes(img))
    ino = next((i for p, i, m, s in fs.walk() if p == path), None)
    if ino is None:
        raise SystemExit(f"not found in ramdisk: {path}")
    node = fs.inode(ino)
    if node["mode"] & IFMT != IFREG:
        raise SystemExit(f"not a regular file: {path}")
    # allocated space: whole blocks for all but the last, fragments for the last one
    di_blocks = struct.unpack_from(">i", node["raw"], 0x68)[0]   # in 512-byte sectors
    room = di_blocks * 512
    if any(node["ib"]) or len(new) > room or len(new) > fs.NDADDR * fs.bsize:
        raise SystemExit(f"{path}: {len(new)} bytes won't fit in {room} allocated")
    nblk = (node["size"] + fs.bsize - 1) // fs.bsize
    if (len(new) + fs.bsize - 1) // fs.bsize != nblk:
        raise SystemExit(f"{path}: new size changes the block count")
    for bi in range(nblk):
        part = new[bi * fs.bsize:(bi + 1) * fs.bsize]
        cap = min(fs.bsize, room - bi * fs.bsize)
        o = fs._byte(node["db"][bi])
        img[o:o + cap] = part + b"\0" * (cap - len(part))
    # rewrite di_size in the on-disk inode (same address math as UFS1.inode)
    cg, inc = ino // fs.ipg, ino % fs.ipg
    cgimin = fs.fpg * cg + fs.cgoffset * (cg & ~fs.cgmask) + fs.iblkno
    off = fs._byte(cgimin + (inc // fs.inopb) * fs.frag) + (ino % fs.inopb) * fs.DINODE
    struct.pack_into(">Q", img, off + 0x08, len(new))
    check = UFS1(bytes(img))
    if check.read_file(ino) != new:
        raise SystemExit("read-back mismatch after patch")
    return bytes(img)


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "roundtrip":
        data = open(a[1], "rb").read()
        same = join(*split(data)) == data
        print("roundtrip:", "IDENTICAL" if same else "DIFFERENT")
        sys.exit(0 if same else 1)
    if len(a) == 5 and a[0] == "replace":
        _, src, path, newfile, dst = a
        parts = list(split(open(src, "rb").read()))
        parts[4] = replace_file(parts[4], path, open(newfile, "rb").read())
        out = join(*parts)
        split(out)                                 # re-parse: headers, Adler-32, gzip
        open(dst, "wb").write(out)
        print(f"wrote {dst} ({len(out)} bytes)", file=sys.stderr)
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
