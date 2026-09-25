# The boot chain and flash layout of the A1392

Everyone who has hacked an AirPort Express knows two facts: setting `dbug` gets you a
root shell (see [dbug.md](dbug.md)), and the firmware is a "`.basebinary`" you can
sometimes unpack. Almost nobody documents what sits *under* that: how the box actually
boots, how flash is partitioned, and — the question that decides whether you can run
custom code permanently — **whether anything cryptographically verifies the firmware.**

This page answers that. It was built two ways and they agree: static analysis of
`ACPd` (reached through the `syBL` property, which turned out to be *ACPd reading the
raw bootloader partition*), and a **read-only** dump of the live flash on an A1392
(7.8.1) on 2026-09-24. The headline: **the A1392 has no secure boot.** Neither the
bootloader nor ACPd checks a signature — both gate firmware on a magic string, an
Adler-32/CRC checksum, and a minimum-version number.

> Everything here is read-only. Reading flash needs a root shell, which needs `dbug`
> bit `0x200` clear (SSH on); no writes were made to the device. Device-identifying
> contents of the factory partition (serial, MAC addresses, radio calibration) are
> deliberately **not** reproduced here.

## Flash map

The kernel reports `hw.machine = ar7240`, but the silicon is actually an **Atheros
AR9344 "Wasp"** — a **MIPS 74Kc** big-endian core with the 2.4 GHz radio on-die (the
AR934x family reuses NetBSD's `ar7240` platform/ethernet code, and CFE's
`WASP_BOOTSTRAP_REG` gives it away) — paired with an **AR9582** for the 5 GHz radio, and
64 MB of DDR2 RAM. Flash is a single **Winbond W25Q128 (128 Mbit = 16 MB) SPI-NOR** chip
that the NetBSD driver exposes as five "disks" plus the RAM-disk root. (Chip identities
are from the teardowns cited in [hardware.md](hardware.md); the sizes and partitioning
below are read live.)

```
hw.machine = ar7240      hw.machine_arch = mipseb      hw.physmem = 67108864 (64 MB)
hw.disknames = flash0 flash1 flash2 flash3 flash4 md0
```

| device | size | erase | role |
|---|---:|---:|---|
| `flash0` | 7 MB | 64 KB | firmware **bank A** (primary) |
| `flash1` | 7 MB | 64 KB | firmware **bank B** (secondary/failover) |
| `flash2` | 1.25 MB | 64 KB | **`/mnt/Flash`** — the only writable, persistent filesystem |
| `flash3` | 256 KB | 64 KB | **CFE nvram / factory data** |
| `flash4` | 512 KB | 64 KB | **Apple CFE bootloader** |

Sizes are from `flashctl /dev/flashNc info` (authoritative). They sum to exactly
16 MB. Each disk also has raw character nodes `/dev/rflashN.raw`; the NetBSD flash
driver hands every disk a placeholder full-device disklabel (partitions `a`–`p` all at
offset 0, so `disklabel` prints harmless "partitions overlap" warnings).

Two consequences worth internalising:

* **The root filesystem is a RAM disk.** `/` is `/dev/md0a` (a ~11.5 MB FFS image, 93 %
  full) unpacked into RAM at boot from the active bank. **Changes to `/` do not
  survive a reboot.** The *only* persistent store is `flash2` → `/mnt/Flash` (~1 MB
  usable), which holds the ACP property blob (`ACPData.bin`) and the persisted `sshd`
  host keys. ACPd also keeps TLS material (`server.p12`, `ca.*`) and DHCP leases there
  when those features are used; on our unit only the first two exist. Files you add
  there survive power cuts, even mid-write (tested; see
  [crossdev § Storage](../crossdev/README.md#storage-usb-and-persistence)). `/mnt/Memory`
  is an `mfs` scratch tmpfs.
* **There are two full copies of the firmware.** `flash0` and `flash1` are identical
  7 MB banks — this is what makes an interrupted update survivable (below).

## How it boots

`flash4` holds **Broadcom CFE** (Common Firmware Environment), customised by Apple for
the board codenamed **k31** (the A1392). Its banner — the string `syBL` returns — is:

```
Apple CFE (bcm: 1.4.2 ath: 2012-1-15 apple: a4) Apr 23 2012 17:40:05
```

and its build path names the firmware it shipped in: `AirPortFW-76200.16`, i.e.
**7.6.2** — the bootloader is *not* rewritten on every OS update, so it lags the 7.8.1
OS in the banks. CFE embeds zlib (`inflate 1.1.3`), so the bank image is gzip-compressed
and CFE inflates it into RAM.

The boot command lives in CFE's environment as `BOOTCMD = "airboot primary"`. `airboot`
is Apple's boot verb: **"boot from primary or secondary image."** It computes the
checksum of `flash0`, boots it if it matches, and **falls back to `flash1`** if it does
not:

```
checkimages: compute checksum on both primary and secondary images
image @ %p: adlers: computed=0x%08x, stored=0x%08x
primary image is OK.            primary image FAILED check/sum
secondary image is OK.          secondary image FAILED check/sum
```

Before autoboot, CFE prints *"Press any key to stop, OR autoboot will start in …"* and,
if interrupted, drops to a **`CFE>` console** over the serial UART. From there it can
program flash, run memory tests, and **netboot over TFTP** (`BOOT_SERVER` / `BOOT_FILE`,
the `-tftp` / `-z` load options). That console is the real recovery and unbrick path —
but it is only exposed on the board's UART pads, so reaching it needs the case opened
(the one part of this still to be done).

So the chain is:

```
CFE (flash4) → airboot: checksum flash0, else flash1
             → gunzip the 7 MB bank → NetBSD kernel + md0 root image into RAM
             → NetBSD 4.0 boots, mounts md0 as / (RAM), flash2a as /mnt/Flash
             → ACPd + airtunesd + hostapd + mDNSResponder …
```

## The verification model — there is no signature

This is the point of the whole page. **Nothing on the A1392 verifies a firmware
signature.** The integrity checks, at both layers, are non-cryptographic:

* **In CFE:** the only integrity strings in the 512 KB bootloader image are the
  Adler-32 image check and CRC boot-block checks shown above. A search of the entire
  image finds **no** `rsa`, `sha`, `sign`, `pubkey`, `certificate`, or `secure boot`
  strings, and no embedded public-key modulus.
* **In ACPd** (the over-the-air update path): the image parser `FUN_00807cec` requires
  the literal magic **`APPLE-FIRMWARE`** at offset 0, then a 36-byte header, then a
  **trailing 4-byte checksum** over the payload — and that is the entire integrity
  check. The only signature code anywhere in ACPd belongs to HomeKit pairing, not to
  firmware.

What *does* gate an update is a **minimum-version** number (anti-rollback). The writer
`FUN_00699a84` reads the property `minS` and rejects a bank-A image whose version is
below it. `minS` is not a constant — it comes from the CFE factory nvram key
**`apple-minver`** (see below). On this unit it is `76200.16` (7.6.2), so the box will
accept 7.6.2 or newer but refuse a downgrade past that floor.

Net effect: a correctly-formed `APPLE-FIRMWARE` image with a valid checksum and a
version ≥ `apple-minver` is accepted by ACPd, written to a bank, and booted by CFE — no
key required. That is the answer to "can it run custom code permanently?": **yes, there
is no cryptographic barrier**, only a format/checksum/version gate. (This is the
*local* flash/boot path; Apple's OTA update feed is separately signature-checked at the
catalog layer. Both, and how they fit the wider threat model, are in [security.md](security.md).)

## The firmware image format

From `FUN_00807cec` (the parser) and `FUN_00699a84` (the writer):

| offset | bytes | meaning |
|---|---|---|
| `0x00` | 14 | magic `APPLE-FIRMWARE` (else the update is rejected, `-20`) |
| `0x10` | 4 | model ID — `0x73` = **115** = A1392 (the image must match the device model) |
| `0x14` | 4 | version (compared against `minS`) |
| `0x18`,`0x0f` | — | build fields |
| `0x1b` | 1 | flag byte; bit `0x02` = payload **encrypted**, bit `0x04` = target the **bootloader** |
| `0x1c` | 4 | reserved |
| `0x20` | … | payload — the next container, or (innermost) an **AES-encrypted, gzip'd** bank, or a bootloader image |
| end −4 | 4 | Adler-32 over `header+payload` (verified → else `-6`) — the only integrity check |

A distributed `.basebinary` nests two of these containers, with the inner payload
AES-encrypted; how to peel and decrypt it on a PC is in **[firmware.md](firmware.md)**.

The writer's target selector chooses the destination: **1 → `flash0` (bank A)**,
**2 → `flash1` (bank B)**, **3 → `flash4` (the bootloader itself)**. A bank image must be
3–7 MB; a bootloader image ≤ 512 KB. Flash is driven as MTD-style character devices via
two ioctls — `0x401c4665` (get geometry: total size + erase-block size) and `0x80044664`
(erase one block) — then read/write per 64 KB block. The device also ships a `flashctl`
tool (`probe`, `info`, `verify`, `dump`, `erase`, `format`, `lock`/`unlock`) and
`/sbin/eraseflash`.

## The CFE factory partition (`flash3`)

`flash3` is CFE's own nvram: a small run of `key=value\0` records (≈ 87 % erased). It is
the box's persistent factory identity and the source of several values you see over ACP:

| key | meaning |
|---|---|
| `apple-minver` | firmware **minimum version** — the source of the `minS` anti-rollback floor |
| `apple-sn` | the unit's **serial number** |
| `ethaddr` | the Ethernet **MAC** |
| `radio-cal-ath0` / `radio-cal-ath1` | per-radio **calibration** blobs (embed the radio MACs) |
| `apple-sku` | regulatory region (`ETSI` on this unit; matches `ssSK`) |

This is exactly the block that `acp.setStaticConfig` rewrites — **do not touch it**; a
bad write here corrupts the radio calibration or identity of the unit. (The tools in
this repo never call that RPC.)

## `syBL`: how ACPd reads the bootloader version

The thread that unravelled all of the above is the innocuous `syBL` property. Its getter
(`FUN_0064a120`, under `ACPGetPropertyDirect`/`FUN_00675684`) calls `FUN_00691eb0`, which
does exactly:

```c
buf = malloc(0x80000);                       // 512 KB
fd  = open("/dev/rflash4.raw", O_RDONLY);    // the raw bootloader partition
read(fd, buf, 0x80000);                       // must read all 512 KB
p = memmem(buf, 0x80000, "APPLE BOOTLOADER INFO: ", 0x17);
return string_after(p);                       // else "UNKNOWN"
```

i.e. `syBL` is ACPd reading the raw `flash4` bootloader partition and scraping the banner
CFE writes into it. It is read-only (the set path returns `-11`). That one property is
why the bootloader version is visible over ACP at all — and it is what pointed at the
flash device names, the descriptor table, and ultimately the whole layout documented here.

## Reproducing this

Read the bootloader version over ACP (no shell needed):

```sh
python3 - <<'PY'
from airportctl import acp
pw = acp.read_password('@~/.config/airport-express/admin-pw')
print(acp.get_raw('10.0.1.1', pw, 'syBL').split(b'\x00')[0].decode())
PY
```

Inspect flash directly (needs `dbug` bit `0x200` clear so `sshd` is up — see
[dbug.md](dbug.md); the device runs OpenSSH 4.4, so a modern client needs legacy
algorithms):

```sh
ssh -o KexAlgorithms=+diffie-hellman-group14-sha1 \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o Ciphers=+aes128-cbc,3des-cbc -o MACs=+hmac-sha1 root@10.0.1.1
# on the device (read-only):
flashctl /dev/flash4c info      # geometry of the bootloader partition
sysctl hw.disknames             # the five flash disks + md0
mount ; df -k                   # md0 root (RAM) + flash2a /mnt/Flash
dd if=/dev/rflash4.raw bs=64k | strings | head   # the CFE banner + boot logic
```

The root password equals the admin (`syPW`) password once `dbug` is set — the same
mechanism documented in [dbug.md](dbug.md).

## Getting in physically

You don't actually need ACP or SSH: the board has an exposed **serial/JTAG debug header**
by the audio jack. Over its UART (115200 8N1) **a root shell is available with no
authentication**, and pressing a key during the ~1 s `BOOTDELAY` above drops you straight
to the **`CFE>` console** — so physical access is unauthenticated root plus full
bootloader control, independent of the `dbug`/SSH route. The header pinout, chip
identities, and the flash-chip part are in **[hardware.md](hardware.md)**.

Combined with the no-secure-boot finding, the documented way to run custom code is to
modify the RAM-disk contents and write a new gzip'd bank image to `flash0`/`flash1`, which
CFE will boot; with serial/JTAG (or an SPI programmer on the flash) and a backup of the
five partitions, the device is effectively unbrickable.

## What's still open

* The real early **boot log**: the `dmesg` ring buffer rolls over to Wi-Fi/DFS runtime
  messages within minutes, so the flash-probe and CFE hand-off lines are gone unless
  captured over the serial console or right after a reboot.
* ~~Diffing a 7.8.1 vs 7.6.2 `.basebinary` on a PC to see what Apple changed~~ — **done**,
  in [firmware.md](firmware.md) (7.8.1 added the AirPlay 2 receiver; the TLS stack stayed
  at 2007).

Hardware details and their sources (the two teardowns) are in [hardware.md](hardware.md).
The partition sizes, the boot/verification behaviour, the image format, the CFE nvram
keys, and `syBL` on this page were derived first-hand from the firmware and a read-only
flash dump of an A1392 on 7.8.1.
