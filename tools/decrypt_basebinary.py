#!/usr/bin/env python3
"""Decrypt + inflate an Apple AirPort ".basebinary" firmware image (offline, no device).

An Apple .basebinary is two nested APPLE-FIRMWARE containers; the inner one's payload is
AES-128-CBC encrypted (in 0x8000-byte chunks) then gzip'd. This tool peels both
containers, decrypts, and writes the inflated bank image (a NetBSD kernel + md0 FFS
ramdisk). Feed that image to ufs1.py to list/extract the root filesystem.

The per-model AES keys and the key-obfuscation/IV scheme are PUBLIC — they were published
in airpyrt-tools (https://github.com/x56/airpyrt-tools, acp/basebinary.py); this is an
independent, verified Python-3 reimplementation. Verified correct on an A1392 (model 115):
the extracted /sbin/ACPd is byte-identical to the binary dumped from the live device.

Usage:
    decrypt_basebinary.py IN.basebinary [OUT.img]     # OUT defaults to IN with .img

The container format (from ACPd FUN_00807cec / FUN_00699a84), all big-endian:
    32-byte header ">15sB2I4BI":
      magic "APPLE-FIRMWARE\\0"(15) | byte_0x0F(1) | model(u32 @0x10) | version(u32 @0x14)
      | b18 b19 b1A | flags(@0x1b) | unk(u32 @0x1c)
    payload  = data[32:-4]
    trailer  = Adler-32 (big-endian) over header+payload
    flags & 2  =>  payload is AES-128-CBC encrypted; IV = header[:15] + byte_0x0F,
                   key[i] = model_key[i] ^ (i + 0x19), reset per 0x8000 chunk,
                   a sub-16-byte tail of any chunk is left in the clear.
Verification is Adler-32 only -- there is no signature (see docs/boot.md).
"""
import struct, zlib, sys, os

try:
    from Cryptodome.Cipher import AES          # pycryptodomex
except ImportError:
    from Crypto.Cipher import AES              # pycryptodome

# Published in airpyrt-tools (acp/basebinary.py). 115 = A1392 dual-band AirPort Express.
_BASEBINARY_KEYS = {
    107: "5249c351028bf1fd2bd1849e28b23f24",   # AirPort Express 802.11n (A1264)
    108: "bb7deb0970d8ee2e00fa46cb1c3c098e",
    115: "1075e806f4770cd4763bd285a64e9174",   # A1392 (this repo's device)
    120: "688cdd3b1b6bdda207b6cec2735292d2",
}
MAGIC = b"APPLE-FIRMWARE\x00"
HDR = struct.Struct(">15sB2I4BI")              # 32 bytes


def _derive_key(model):
    if model not in _BASEBINARY_KEYS:
        raise SystemExit(f"no key for model {model}; known models: "
                         f"{sorted(_BASEBINARY_KEYS)}")
    k = bytes.fromhex(_BASEBINARY_KEYS[model])
    return bytes((k[i] ^ (i + 0x19)) & 0xff for i in range(len(k)))


def _decrypt(data, key, iv):
    out = bytearray()
    for off in range(0, len(data), 0x8000):
        chunk = data[off:off + 0x8000]
        body = len(chunk) & ~0xf               # whole 16-byte blocks only
        out += AES.new(key, AES.MODE_CBC, iv).decrypt(chunk[:body])
        out += chunk[body:]                    # sub-16 tail: cleartext passthrough
    return bytes(out)


def parse(data, label=""):
    """Return the inner payload of one APPLE-FIRMWARE container (decrypted if flagged)."""
    header, payload = data[:HDR.size], data[HDR.size:-4]
    stored, = struct.unpack(">I", data[-4:])
    magic, b0f, model, version, b18, b19, b1a, flags, unk = HDR.unpack(header)
    if magic != MAGIC:
        raise SystemExit("bad APPLE-FIRMWARE magic")
    if flags & 2:
        payload = _decrypt(payload, _derive_key(model), MAGIC + bytes([b0f]))
    calc = zlib.adler32(header + payload) & 0xffffffff
    print(f"  [{label:5}] model={model} ver=0x{version:08x} flags=0x{flags:02x} "
          f"enc={bool(flags & 2)} payload={len(payload)} adler={'OK' if calc == stored else 'MISMATCH'}",
          file=sys.stderr)
    if calc != stored:
        raise SystemExit(f"checksum mismatch (stored 0x{stored:08x} != calc 0x{calc:08x})")
    return payload


def unpack(data):
    inner = parse(data, "outer")               # outer container is not encrypted
    plain = parse(inner, "inner")              # inner payload decrypts to a gzimg
    gz = plain.find(b"\x1f\x8b\x08")
    if gz < 0:
        raise SystemExit("no gzip stream after decrypt (wrong key/model?)")
    return zlib.decompress(plain[gz:], 16 + zlib.MAX_WBITS)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".img"
    img = unpack(open(src, "rb").read())
    open(dst, "wb").write(img)
    print(f"inflated bank image -> {dst} ({len(img)} bytes)", file=sys.stderr)
