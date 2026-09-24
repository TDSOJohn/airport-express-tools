# Unpacking the firmware on Linux — and what changed in 7.8.1

The other RE pages in this repo start from a base station you can reach: `ACPd` pulled off
the device (see [extracting-acpd.md](extracting-acpd.md)), the live flash dump behind
[boot.md](boot.md). This page needs **no device at all**. Apple still hosts the
`.basebinary` firmware images, and it turns out you can take one apart end to end on a PC:
peel its containers, decrypt it, decompress it, and read the root filesystem straight out
of it.

Two payoffs. First, the whole pipeline is **verifiable**: the `/sbin/ACPd` extracted from
Apple's 7.8.1 download is **byte-for-byte identical** (same SHA-256) to the `ACPd.bin` we
dumped from the live device over SSH — so everything in the address-specific pages can be
reproduced without ever touching hardware. Second, having two versions side by side
answers *what Apple actually changed*: **7.8.1 (2018) added the entire AirPlay 2 receiver
stack to this 2012 hardware — while leaving the TLS/crypto stack frozen at 2007.**

> The `.basebinary` files, and everything unpacked from them, are Apple-copyright firmware
> and are **not** in this repo (`.gitignore` blocks `*.basebinary` and `*.img`). The two
> small tools that do the work are; the firmware you fetch yourself.

## Where the images live

Apple's firmware catalog is a plist still served in the clear:

```
http://apsu.apple.com/version.xml
```

Its `firmwareUpdates` array keys each image by a **productID**. The A1392 dual-band
AirPort Express is **productID 115** — the only product listing both **7.8.1 / 78100.3**
(the OS this unit runs) and **7.6.2 / 76200.16** (the version its CFE was built from, and
its `apple-minver`/`minS` floor — see [boot.md](boot.md)). The two images used here:

| version | source | size | sha256 (first 16) |
|---|---|---:|---|
| 7.8.1 | `apsu.apple.com/data/115/041-48470-20190619-…/7.8.1.basebinary` | 6,098,300 | `56707780d126396e` |
| 7.6.2 | `apsu.apple.com/data/115/041-0311.20130207.aaWs/7.6.2.basebinary` | 5,627,396 | `995c630b774c0d2f` |

## The `.basebinary` format

A `.basebinary` is **two nested `APPLE-FIRMWARE` containers**. Each has the same 32-byte
header that `ACPd` validates in `FUN_00807cec` (the same struct airpyrt-tools calls
`Basebinary`), all fields big-endian:

| offset | size | field | note |
|---|---|---|---|
| `0x00` | 15 | magic `APPLE-FIRMWARE\0` | else rejected (`-20`) |
| `0x0f` | 1 | `byte_0x0F` | also the low byte of the AES IV |
| `0x10` | 4 | **model** | `0x73` = **115** = A1392 — the header identifies the target model |
| `0x14` | 4 | version | `0x07818000` (7.8.1) / `0x07628000` (7.6.2); checked against `minS` |
| `0x18` | 3 | `b18 b19 b1A` | build fields |
| `0x1b` | 1 | **flags** | bit `0x2` = payload encrypted; bit `0x4` = targets the bootloader |
| `0x1c` | 4 | reserved | |
| `0x20` | … | payload | the next container, or (innermost) the encrypted gzimg |
| end −4 | 4 | **Adler-32** | over `header + payload`; **the only integrity check** |

The outer container's payload (`flags=0x00`) is just the inner container. The inner
container (`flags=0x02`) has an **encrypted** payload; decrypt it and you get a gzip stream
that inflates to the **bank image** — a NetBSD kernel with the md0 FFS RAM disk embedded.
`ACPd`'s writer (`FUN_00699a84` → `FUN_0069942c`) peels these headers in a loop and writes
the **innermost payload verbatim** to `flash0`/`flash1`; it never decrypts or decompresses.
So the encrypted bank is what physically sits on flash, and **CFE decrypts + gunzips it at
boot**. This refines the image-format table in [boot.md](boot.md) (which noted the parser
but not the encryption).

## The encryption

The payload is **AES-128-CBC**, applied in independent **0x8000-byte chunks** (the IV
resets each chunk; a sub-16-byte tail of a chunk is left in the clear). The key is
**per-model**:

- **IV** = the first 16 header bytes = `"APPLE-FIRMWARE\0"` + `byte_0x0F`.
- **key** = `model_key[i] ^ (i + 0x19)` for each of the 16 bytes (a trivial obfuscation).

The per-model `model_key` values are **public** — they were published in
[airpyrt-tools](https://github.com/x56/airpyrt-tools) (`acp/basebinary.py`), recovered
from Apple's `crunchprog`. `tools/decrypt_basebinary.py` is an independent, verified
Python-3 reimplementation.

Two things follow, both feeding the security write-up (R6):

1. This is **encryption without integrity**. Verification is Adler-32 only — there is no
   signature at either the `ACPd` or the CFE layer (see [boot.md](boot.md)). The AES key is
   **symmetric and lives in CFE**, which anyone with a unit can dump. So the encryption
   stops casual inspection but provides no real protection: with the key you can both read
   Apple's images and produce your own that the device will accept.
2. Encryption is **flag-gated** (`flags & 0x2`). The device happily accepts an
   *un*encrypted bank (flag clear) with a valid Adler-32 — so custom firmware doesn't even
   need the key, which matches the community's "modify the ramdisk, rebuild a gzip'd bank,
   reflash" method.

## Unpacking it — the tools

Two small readers in `tools/`, no root or loopback mount required:

```sh
# 1. .basebinary  ->  inflated bank image (NetBSD kernel + md0 FFS ramdisk)
python3 tools/decrypt_basebinary.py 7.8.1.basebinary 7.8.1.img

# 2. list the root filesystem inside the image (UFS1 offset auto-detected)
python3 tools/ufs1.py 7.8.1.img tree

# 3. or extract the whole tree / one file
python3 tools/ufs1.py 7.8.1.img extract fs781/
python3 tools/ufs1.py 7.8.1.img cat /sbin/ACPd > ACPd.bin
```

`decrypt_basebinary.py` peels both containers, checks each Adler-32, AES-decrypts the
inner payload, and inflates the gzip. `ufs1.py` is a from-scratch **big-endian NetBSD
FFS/UFS1** reader (superblock geometry, direct + indirect blocks, inline "fast" symlinks).

**Validation:** `tools/ufs1.py 7.8.1.img cat /sbin/ACPd` reproduces the exact SHA-256 of
the `ACPd.bin` obtained from the live device — the offline pipeline is provably faithful.

## What's inside

The image contains a NetBSD 4.0 kernel followed by a **~12 MB UFS1 filesystem** (the md0
root: `bin dev etc lib libexec sbin usr var`, 55 directories, ~231 file entries). Almost
every executable is a hardlink to **one crunchgen megabinary** — a single statically
linked blob (like `busybox`) that dispatches on `argv[0]`. `/sbin/ACPd`, `/bin/ls`,
`/sbin/hostapd`, `/sbin/wpa_supplicant`, `/sbin/mDNSResponder`, `/sbin/airtunesd`, … are
all the same file, hardlinked ~133 ways. That megabinary is where essentially all the code
— and all the version-to-version change — lives.

## 7.6.2 → 7.8.1: what Apple changed

Collapsing the hardlink noise (diffing by content hash, then string-diffing the
megabinary):

| change | detail |
|---|---|
| **AirPlay 2 added** | 131 new `AirPlay`/`HomeKit`/pairing strings, **none** present in 7.6.2: `AirPlay;2.0.2`, `AirPlay/366.0`, the `AirPlayReceiverServer` / `AirPlayJitterBuffer` / `AirPlayClock` multi-room-sync stack, and HomeKit pairing (`…FindPeerHomeKit`, `AirPlay Pairing Identity`). This is the 2018 update that back-ported AirPlay 2 to the 2012 hardware. |
| **crypto stack frozen** | Both versions ship **OpenSSL 0.9.8e (2007)** and **libcurl 7.17.1 (2007)**, with SSHv1 still compiled in — *unchanged*. The only new crypto (`ChaCha20-Poly1305`, `RSA_SHA256`) belongs to the AirPlay 2 / HAP pairing transport, **not** the system TLS used for management (ACP, HTTPS). A 2018 firmware still fronting 2007 TLS. |
| **`mobilemed` removed** | the USB printer-sharing daemon (`RemoteIOUSBPrinterDeviceInfo`) is gone in 7.8.1. |
| **kernel** | the pre-filesystem region changed (+10,928 bytes). |
| **cosmetic** | `/etc/issue` copyright → "2005-2018 Apple Inc."; `/etc/flash2.disktab` label reads "Darrin edited label" (an engineer's name shipped in the image). |

The megabinary grew **9.25 MB → 10.29 MB (+1.04 MB)**, essentially all of it the new
AirPlay 2 receiver.

## Why this matters for security

The headline security facts fall straight out of the diff. This box's last firmware is a
**2018 release** that carries a **2007 OpenSSL and a 2007 libcurl**, still offers **SSH
protocol 1**, and rides a **NetBSD 4.0 (2007)** kernel. The one big change Apple made in
those years was a *feature* (AirPlay 2), not a security refresh. Combined with "no secure
boot" ([boot.md](boot.md)) and secrets stored in cleartext ([properties.md](properties.md)),
the picture is that of any long-abandoned appliance.

The full write-up — the live attack surface, the frozen-vs-refreshed crypto inventory, the
firmware/control-plane/SSH/RF/physical trust boundaries, and a threat model — is in
**[security.md](security.md)**.

## Credits

The per-model AES keys and the container/IV/obfuscation scheme are from
**[airpyrt-tools](https://github.com/x56/airpyrt-tools)** by x56 (`acp/basebinary.py`) and
the write-ups at **[Embedded Ideation](https://www.embeddedideation.com/2016/04/24/airport-hacking-update/)**.
The tools here are an independent reimplementation, and the container format, the
verbatim-write behaviour, the crunchgen layout, and the version diff were derived
first-hand from `ACPd` and the two A1392 images.
