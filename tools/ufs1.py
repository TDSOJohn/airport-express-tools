#!/usr/bin/env python3
"""Read-only NetBSD FFS / UFS1 (big-endian) reader -- list or extract the A1392 root.

The bank image produced by decrypt_basebinary.py is a NetBSD kernel with an embedded md0
FFS RAM disk (the same filesystem that is mounted read-write-nothing as `/` on the running
device). This reader finds that UFS1 filesystem, walks it, and lists or extracts it -- no
root, loopback mount, or fsck tooling required.

Usage:
    ufs1.py IMG [tree]           # list every file/dir/symlink  (default)
    ufs1.py IMG cat  /path       # write one file's bytes to stdout
    ufs1.py IMG extract OUTDIR   # extract the whole tree to OUTDIR

The filesystem offset within IMG is auto-detected (first UFS1 superblock with sane
geometry); pass it explicitly as a trailing hex arg to override. Verified on an A1392:
the extracted /sbin/ACPd matches the binary dumped from the live device byte-for-byte.
"""
import struct, sys, os

UFS1_MAGIC = 0x11954
IFMT = 0o170000; IFDIR = 0o040000; IFLNK = 0o120000; IFREG = 0o100000


def find_fs_base(data):
    """Scan for a UFS1 superblock (magic at sb+0x55c, sb at fs_base+0x2000) with sane geometry."""
    needle = b"\x00\x01\x19\x54"
    i = data.find(needle)
    while i >= 0:
        sb = i - 0x55c
        if sb >= 0x2000:
            bsize = struct.unpack_from(">i", data, sb + 0x30)[0]
            fsize = struct.unpack_from(">i", data, sb + 0x34)[0]
            if bsize in (4096, 8192, 16384, 32768) and fsize in (512, 1024, 2048, 4096):
                return sb - 0x2000
        i = data.find(needle, i + 1)
    raise SystemExit("no UFS1 filesystem found in image")


class UFS1:
    def __init__(self, data, fs_base=None):
        self.d = data
        self.base = find_fs_base(data) if fs_base is None else fs_base
        sb = self.base + 0x2000
        g = lambda o: struct.unpack_from(">i", data, sb + o)[0]
        if struct.unpack_from(">I", data, sb + 0x55c)[0] != UFS1_MAGIC:
            raise SystemExit("bad UFS1 magic at computed superblock")
        self.bsize = g(0x30); self.fsize = g(0x34); self.frag = g(0x38)
        self.iblkno = g(0x10); self.inopb = g(0x78); self.nindir = g(0x74)
        self.ipg = g(0xb8); self.fpg = g(0xbc)
        self.cgoffset = g(0x18); self.cgmask = g(0x1c)
        self.DINODE = 128; self.NDADDR = 12

    def _byte(self, frag):
        return self.base + frag * self.fsize

    def _block(self, frag, n=None):
        if frag == 0:
            return b"\x00" * (n or self.bsize)          # sparse hole
        o = self._byte(frag)
        return self.d[o:o + (n or self.bsize)]

    def _ind(self, frag):
        return list(struct.unpack(">%di" % self.nindir, self._block(frag)))

    def inode(self, ino):
        cg = ino // self.ipg; inc = ino % self.ipg
        cgimin = self.fpg * cg + self.cgoffset * (cg & ~self.cgmask) + self.iblkno
        fsba = cgimin + (inc // self.inopb) * self.frag
        off = self._byte(fsba) + (ino % self.inopb) * self.DINODE
        di = self.d[off:off + self.DINODE]
        mode, nlink = struct.unpack_from(">Hh", di, 0)
        size, = struct.unpack_from(">Q", di, 0x08)
        db = struct.unpack_from(">12i", di, 0x28)
        ib = struct.unpack_from(">3i", di, 0x58)
        return dict(mode=mode, nlink=nlink, size=size, db=db, ib=ib, raw=di)

    def _blockaddr(self, node, bi):
        NIND = self.nindir
        if bi < self.NDADDR:
            return node["db"][bi]
        bi -= self.NDADDR
        if bi < NIND:
            return self._ind(node["ib"][0])[bi]
        bi -= NIND
        if bi < NIND * NIND:
            l1 = self._ind(node["ib"][1])
            return self._ind(l1[bi // NIND])[bi % NIND]
        bi -= NIND * NIND
        l1 = self._ind(node["ib"][2])
        l2 = self._ind(l1[bi // (NIND * NIND)])
        return self._ind(l2[(bi // NIND) % NIND])[bi % NIND]

    def read_file(self, ino):
        node = self.inode(ino); size = node["size"]; out = bytearray()
        for bi in range((size + self.bsize - 1) // self.bsize):
            out += self._block(self._blockaddr(node, bi), min(self.bsize, size - bi * self.bsize))
        return bytes(out[:size])

    def readlink(self, ino):
        node = self.inode(ino)
        if node["size"] <= 60:                          # UFS1 fast symlink: inline at di_db
            return node["raw"][0x28:0x28 + node["size"]].decode("latin1")
        return self.read_file(ino).decode("latin1")

    def read_dir(self, ino):
        raw = self.read_file(ino); ents = []; o = 0
        while o < len(raw):
            d_ino, d_reclen = struct.unpack_from(">IH", raw, o)
            d_type, d_namlen = raw[o + 6], raw[o + 7]
            if d_reclen == 0:
                break
            if d_ino != 0:
                ents.append((raw[o + 8:o + 8 + d_namlen].decode("latin1"), d_ino, d_type))
            o += d_reclen
        return ents

    def walk(self, ino=2, path=""):
        for name, cino, _ in self.read_dir(ino):
            if name in (".", ".."):
                continue
            cn = self.inode(cino); p = path + "/" + name
            yield (p, cino, cn["mode"], cn["size"])
            if (cn["mode"] & IFMT) == IFDIR:
                yield from self.walk(cino, p)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    img = sys.argv[1]; cmd = sys.argv[2] if len(sys.argv) > 2 else "tree"
    fs_base = int(sys.argv[-1], 16) if sys.argv[-1].lower().startswith("0x") else None
    fs = UFS1(open(img, "rb").read(), fs_base)
    if cmd == "tree":
        n = 0
        for p, ino, mode, size in fs.walk():
            t = "d" if (mode & IFMT) == IFDIR else ("l" if (mode & IFMT) == IFLNK else "-")
            extra = " -> " + fs.readlink(ino) if (mode & IFMT) == IFLNK else ""
            print(f"{t}{oct(mode & 0o7777)[2:]:>4} {size:>9} {p}{extra}")
            n += 1
        print(f"# {n} entries; fs at 0x{fs.base:x}", file=sys.stderr)
    elif cmd == "cat":
        target = sys.argv[3]
        for p, ino, mode, size in fs.walk():
            if p == target:
                os.write(1, fs.read_file(ino)); return
        raise SystemExit(f"not found: {target}")
    elif cmd == "extract":
        outdir = sys.argv[3]; nf = nl = nd = err = 0
        for p, ino, mode, size in fs.walk():
            dst = outdir + p
            try:
                if (mode & IFMT) == IFDIR:
                    os.makedirs(dst, exist_ok=True); nd += 1
                elif (mode & IFMT) == IFLNK:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if os.path.lexists(dst):
                        os.remove(dst)
                    os.symlink(fs.readlink(ino) or ".", dst); nl += 1
                elif (mode & IFMT) == IFREG:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    open(dst, "wb").write(fs.read_file(ino)); nf += 1
            except Exception as e:
                err += 1; print(f"  skip {p}: {e}", file=sys.stderr)
        print(f"extracted to {outdir}: {nf} files, {nl} symlinks, {nd} dirs, {err} errors",
              file=sys.stderr)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:        # e.g. piped into `head`
        try:
            sys.stdout.close()
        except Exception:
            pass
