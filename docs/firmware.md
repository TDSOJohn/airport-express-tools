# Firmware images

Apple's `.basebinary` images: where they are, their format, how to unpack them on a PC
without a device. Newest version and AES key status per model:
[models.md § Firmware images](models.md#firmware-images). Flash and boot side:
[boot.md](boot.md).

## Catalog

`http://apsu.apple.com/version.xml` (plain HTTP; signed via `version.xml.signature`, see
[security.md](security.md#trust-boundaries)). Its `firmwareUpdates` array keys each image by
**productID** = `syAP`.

A1392 (`syAP` 115) images:

| Version | Path under `apsu.apple.com/data/115/` | Bytes | SHA-256 (first 16) |
|---|---|---:|---|
| 7.8.1 (78100.3) | `041-48470-20190619-…/7.8.1.basebinary` | 6,098,300 | `56707780d126396e` |
| 7.6.2 (76200.16) | `041-0311.20130207.aaWs/7.6.2.basebinary` | 5,627,396 | `995c630b774c0d2f` |

## `.basebinary` format

Two nested `APPLE-FIRMWARE` containers. Same 32-byte header on both, big-endian, validated by
ACPd's `FUN_00807cec` (airpyrt-tools: `Basebinary`):

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0x00` | 15 | magic `APPLE-FIRMWARE\0` | else rejected (-20) |
| `0x0f` | 1 | `byte_0x0F` | low byte of the AES IV |
| `0x10` | 4 | model | = `syAP` (`0x73` = 115); must match the device |
| `0x14` | 4 | version | `0x07818000` = 7.8.1, `0x07628000` = 7.6.2; checked against `minS` |
| `0x18` | 3 | build fields | |
| `0x1b` | 1 | flags | `0x2` payload encrypted; `0x4` targets the bootloader |
| `0x1c` | 4 | reserved | |
| `0x20` | … | payload | next container, or the innermost payload |
| end − 4 | 4 | Adler-32 | over header + payload; the only integrity check (-6 on mismatch) |

| Layer | Flags | Payload |
|---|---|---|
| outer | `0x00` | the inner container |
| inner | `0x02` | encrypted: gzboot loader (22,432 bytes in 7.8.1 / 115) + gzip(NetBSD kernel with the md0 FFS root embedded) + zero padding to 4 bytes |

zlib level 9, window 15, memLevel 8 reproduces Apple's deflate stream byte for byte. What
ends up on flash per model: [boot.md § Boot chain](boot.md#boot-chain).

## Encryption

| | |
|---|---|
| Cipher | AES-128-CBC in independent 0x8000-byte chunks (IV reset per chunk; a tail under 16 bytes stays in the clear) |
| IV | header bytes 0–15: `"APPLE-FIRMWARE\0"` + `byte_0x0F` |
| Key | `model_key[i] ^ (i + 0x19)`, i = 0…15 |
| `model_key` | per model, stored as raw bytes in that model's ACPd (checked on 106, 108, 115; not in the A1392's CFE, which boots the already decrypted bank). Published ones: [airpyrt-tools](https://github.com/x56/airpyrt-tools) `acp/basebinary.py` |
| Integrity | none; the encryption is flag-gated, and an unencrypted payload (flag `0x2` clear) with a valid Adler-32 is accepted too |

## Tools

| Command | Does |
|---|---|
| `tools/decrypt_basebinary.py IN.basebinary OUT.img` | peel both containers, check each Adler-32, decrypt, inflate → bank image (kernel + md0) |
| `tools/ufs1.py IMG tree` | list the root filesystem (big-endian NetBSD FFS/UFS1, offset auto-detected; no root or mount needed) |
| `tools/ufs1.py IMG extract DIR` | extract the whole tree |
| `tools/ufs1.py IMG cat PATH` | one file to stdout, e.g. `/sbin/ACPd` |
| `tools/repack_basebinary.py roundtrip IN` | repack unmodified; must print `IDENTICAL` |
| `tools/repack_basebinary.py replace IN PATH NEWFILE OUT` | replace one ramdisk file in place (must fit the fragments already allocated to it) and rebuild both containers |

Offline extraction matches the live unit byte for byte (ACPd on 115 / 7.8.1 and 108 / 7.6.9,
bank A on 106; [models.md](models.md#firmware-images)).

## Contents (7.8.1, `syAP` 115)

| | |
|---|---|
| Kernel | NetBSD 4.0 |
| Root | ~12 MB UFS1 (md0): `bin dev etc lib libexec sbin usr var`, 55 directories |
| Userland | one statically linked crunchgen binary (10.29 MB), hardlinked ~133 ways: `/sbin/ACPd`, `/bin/ls`, `/sbin/hostapd`, `/sbin/wpa_supplicant`, `/sbin/mDNSResponder`, `/sbin/airtunesd`, … |
| Crypto | OpenSSL 0.9.8e, libcurl 7.17.1, OpenSSH 4.4 with SSHv1 ([security.md](security.md#crypto-inventory)) |

## 7.6.2 → 7.8.1 (`syAP` 115)

| Change | Detail |
|---|---|
| AirPlay 2 added | 131 new AirPlay/HomeKit/pairing strings, none in 7.6.2: `AirPlay;2.0.2`, `AirPlay/366.0`, `AirPlayReceiverServer`, `AirPlayJitterBuffer`, `AirPlayClock`, HomeKit pairing (`…FindPeerHomeKit`, `AirPlay Pairing Identity`) |
| Crypto | unchanged: OpenSSL 0.9.8e, libcurl 7.17.1, SSHv1 in both. New `ChaCha20-Poly1305`, `RSA_SHA256` belong to AirPlay 2 / HAP pairing only |
| `mobilemed` removed | USB printer-sharing daemon (`RemoteIOUSBPrinterDeviceInfo`) |
| Kernel | +10,928 bytes |
| Megabinary | 9.25 MB → 10.29 MB (+1.04 MB, almost all AirPlay 2) |
| Cosmetic | `/etc/issue` → "2005-2018 Apple Inc."; `/etc/flash2.disktab` label "Darrin edited label" |

## Credits

Per-model AES keys and the container/IV/key scheme:
[airpyrt-tools](https://github.com/x56/airpyrt-tools) by x56 and
[Embedded Ideation (2016)](https://www.embeddedideation.com/2016/04/24/airport-hacking-update/).
The tools here are an independent reimplementation.
