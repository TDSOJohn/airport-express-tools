# Models

Measured data for each base station checked so far. Sources: **L** = read from the unit,
**F** = Apple's firmware image, **E** = public teardown ([conventions](README.md#conventions)).
Topic detail: [boot](boot.md), [firmware](firmware.md), [properties](properties.md),
[rpc-surface](rpc-surface.md), [dbug](dbug.md). All product IDs and codenames:
[README § Compatibility](../README.md#compatibility), generated from
[`airportctl/models.py`](../airportctl/models.py).

## Platform

| | A1392 Express (2012) | A1254 Time Capsule (2008) | A1301 Extreme (2009) |
|---|---|---|---|
| `syAP` / `syAM` (L) | 115 / `AirPort10,115` | 106 / `TimeCapsule6,106` | 108 / `AirPort5,108` |
| Codename (F) | K31 | M52 | K10 |
| Firmware seen (L) | 7.8.1 (78100.3) | 7.8.1 (78100.3) | 7.6.9 (76900.11) |
| Newest from Apple | 7.8.1 | 7.8.1 | 7.8.1 |
| Kernel / `hw.machine_arch` (L) | NetBSD 4.0 evbmips / `mipseb` | NetBSD 4.0 evbarm / `armeb` | NetBSD 4.0 evbarm / `armeb` |
| SoC | Atheros AR9344, MIPS 74Kc (E; kernel says ar7240) | Marvell 88F5281 Orion rev 4 (L `chip`) | Marvell 88F5281 Orion rev 6 (L `chip`) |
| RAM (L) | 64 MB | 128 MB | 64 MB |
| Ethernet (L) | `ag7240` | `gec0` (Marvell GbE) | `gec0` (Marvell GbE) |
| Wi-Fi `card` (L) | Atheros, driver 4.0.27.6, mac 768.3 | Marvell, driver 0.8.7.0 | Atheros, driver 3.0.57, mac 128.2 |
| Radios | `ath0` 2.4 GHz AR9344, `ath1` 5 GHz AR9582 (E) | 1 × Marvell 88W8363 (E) | `ath0` **5 GHz**, `ath1` **2.4 GHz**; both PCI 0x0029, AR922x (L) |
| `WiFi` blob radio 0 / 1 (L) | 2.4 / 5 GHz | one radio | **5 / 2.4 GHz** |
| Other I/O | USB | USB 2.0, SATA 88SE6121 (L) | USB (disk sharing in `feat`) |

## Flash and boot

| | A1392 | A1254 | A1301 |
|---|---|---|---|
| Flash (L) | 16 MB SPI NOR, W25Q128BV (E) | 16 MB CFI parallel NOR, 128 KB sectors | 16 MB NOR, 128 KB sectors |
| flash0 / flash1: banks A / B | 7 MB / 7 MB | 7 MB / 7 MB | 7 MB / 7 MB |
| flash2: `/mnt/Flash` (translated) | 1.25 MB | 1.375 MB | 1.375 MB |
| flash3: nvram | 256 KB | 128 KB | 128 KB |
| flash4: bootloader | 512 KB | 512 KB | 512 KB |
| nvram keys (L) | `apple-minver`, `apple-sn`, `ethaddr`, `apple-sku`, `radio-cal-ath0/1` | `apple-sn`, `ethaddr`, `apple-sku` | `apple-sn`, `ethaddr` |
| Bootloader `syBL` (L) | Apple CFE (bcm 1.4.2, ath 2012-1-15, apple a4), Apr 2012 | apple microboot 3.0.0b1, Mar 2008 | apple microboot 3.0.0b1, Dec 2008 |
| Bank as stored (L) | gzboot (MIPS stub + gzip): the decrypted payload, so ACPd decrypts at update | gzboot (ARM stub + gzip): the decrypted payload, so ACPd decrypts at update | same as A1254 |
| Bank B as found (L) | 7.6.2 (76200.16) | factory, Mar 2008 | factory, NetBSD 4.0_BETA2, Dec 2008 |
| Anti-rollback `minS` (L) | 76200.16 (from `apple-minver`) | none | none |
| Signature check at boot | none: Adler-32/CRC only | none found | none found (no rsa/sha strings; 97 % erased) |
| Root (L) | md0 RAM disk, ~11.5 MB | md0, 15.5 MB | md0, 9.9 MB, 93 % full |

## ACP and access

| | A1392 | A1254 | A1301 |
|---|---|---|---|
| Readable properties, of 520 (L) | 147 | 190 | 132 |
| `feat` entries (L) | 89 | 90 | 92 |
| RPCs registered, as an AP (L) | 107 | not counted | 94 |
| SSH with `dbug` bit 0x200 clear + reboot (L) | `SSH-1.99 OpenSSH_4.4`, root = admin password | same | same; first banner after ~3–4 min (host-key generation) |
| After a factory reset (L) | | | NAT router at 10.0.1.1, open Wi-Fi `Apple Network xxxxxx`, password `public`; old `ACPData.bin.1-3` stay on `/mnt/Flash` |

Differences between models (L):

| | Only on | Missing on |
|---|---|---|
| Properties | A1392: `au*` (AirPlay), `CLTM`, `TMEn`, `laIS`, `laMA`, `sPLL`, `sySI`, `6!at`, `6CPa`, `6CPl`. A1254 + A1301: `MaSt`, `diSD`, `usbF` | |
| `feat` | A1301 vs A1392: `gigE` `DisB` `DisF` `MSto` `RTCp` `RaRo` `diSD`. A1254 vs A1301: `ArcI` `EraI` `IntD` `TimM` | A1301 vs A1392: `AP20` `aTns` `i6NR` `pSTA`. A1254 vs A1301: `GNAs` `GstN` `IGCR` `RaRo` `iEAP` `sbDB` |
| RPCs | A1301: `acpd.controlFileServers`, `acpd.processDiskChanges` | A1254 + A1301 (F): `wifi.proxy.sta.discovery`, `wifi.proxy.sta.idle`, `wifi.proxysta.status` |

## airportctl on each model

| Command | A1392 / 7.8.1 | A1254 / 7.8.1 | A1301 / 7.6.9 |
|---|---|---|---|
| `info`, `wifi show`, `mode show` | ✓ | not run (ACP reads ✓) | ✓ (the `WiFi` blob re-encodes byte-identically) |
| `rpc` (read-only ones) | ✓ | not run | ✓ with `--force` |
| `admin-password` | ✓ | ACP write ✓ | ✓ with `--untested` |
| Other writes | ✓ | untested | untested |
| `join` | ✓ | ✗: Marvell Wi-Fi | ✗: needs an armeb build, and the radio on `ath1` |

## Firmware images

Apple's catalog: `http://apsu.apple.com/version.xml`. Unpack with
[`tools/decrypt_basebinary.py`](../tools/decrypt_basebinary.py) + [`tools/ufs1.py`](../tools/ufs1.py)
([firmware.md](firmware.md)).

| `syAP` | Newest | AES key | Offline unpack == live unit |
|---|---|---|---|
| 106 | 7.8.1 | known (TimeCapsuleSMB) | bank A, byte-identical |
| 107 | 7.8.1 | public (airpyrt-tools) | |
| 108 | 7.8.1 | public (airpyrt-tools) | 7.6.9: bank A and ACPd, byte-identical |
| 115 | 7.8.1 | public (airpyrt-tools) | 7.8.1: ACPd, byte-identical |
| 120 | 7.9.1 | public (airpyrt-tools) | |
| 104, 105, 109, 113, 114, 116, 117 | 7.8.1 | not public | |
| 119 | 7.9.1 | not public | |

Each model's ACPd holds its own AES key as raw bytes (checked on 106, 108, 115), so a unit with
SSH gives up its model's key. 7.8.1 (n models) and 7.9.1 (ac models) are NetBSD 4.0 big-endian
and NetBSD 6.0 little-endian ARM respectively.
