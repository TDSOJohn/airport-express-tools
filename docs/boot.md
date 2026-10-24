# Boot and flash

Flash layout, boot chain and firmware update paths. Per-model sizes, bootloaders and bank
formats: [models.md § Flash and boot](models.md#flash-and-boot). Image format and
encryption: [firmware.md](firmware.md).

## Flash partitions

NetBSD exposes the flash as five disks plus the RAM-disk root:
`hw.disknames = flash0 flash1 flash2 flash3 flash4 md0` (L, all measured models).

| Device | CFE name (A1392, E) | Role |
|---|---|---|
| `flash0` | `primary` | firmware bank A |
| `flash1` | `secondary` | firmware bank B (fallback) |
| `flash2` | `dcfg` | `/mnt/Flash`: FFS on `/dev/flash2a`, `rw,noatime,sync`; the only persistent writable filesystem |
| `flash3` | `scfg` | bootloader nvram / factory data ([below](#factory-nvram-flash3)) |
| `flash4` | `boot` | bootloader |
| `md0` | | `/`: FFS RAM disk unpacked from the active bank; changes are lost at reboot |

| | |
|---|---|
| Erase block | A1392: 64 KB. A1254, A1301: 128 KB |
| Raw nodes | `/dev/rflashN.raw` for each disk. The driver gives every disk a placeholder full-device disklabel (`a`–`p` all at offset 0), so `disklabel` warns "partitions overlap"; harmless |
| `/mnt/Flash` contents | `ACPData.bin` (ACPd settings), sshd host keys; also `server.p12`, `ca.*`, DHCP leases when those features are used. Behaviour under writes and power cuts: [crossdev § Storage](../crossdev/README.md#storage-usb-and-persistence) |
| `/mnt/Memory` | `mfs` RAM scratch, wiped at reboot |
| Geometry | `flashctl /dev/flashNc info` |
| Dump | `tools/essh.sh 'cat /dev/rflashN.raw' > flashN.bin` (all five partitions ≈ 25 s on the A1392) |

## Boot chain

```
bootloader (flash4) → check bank A (flash0), else bank B (flash1)
  → jump into the bank's gzboot loader → loader copies itself to RAM, inflates the kernel from flash
  → NetBSD kernel + md0 root image in RAM
  → mount md0 as /, flash2a as /mnt/Flash → /etc/rc → ACPd, airtunesd, hostapd, mDNSResponder …
```

| | A1392 | A1254, A1301 |
|---|---|---|
| Bootloader | Apple CFE (Broadcom CFE), board `k31`; banner `Apple CFE (bcm: 1.4.2 ath: 2012-1-15 apple: a4) Apr 23 2012 17:40:05`; build path `AirPortFW-76200.16` (7.6.2); not rewritten by OS updates. Runs from flash at `0x9fc00000` (reset vector), PIC | apple microboot 3.0.0b1 |
| Autoboot (F) | if the environment has `BOOTCMD`, run it (the stock nvram has none, and CFE never sets it). Else: Adler-check `0xbf200000`, OK → `airboot primary`; else Adler-check `0xbf900000` (result only printed) → `airboot secondary`. Code at `0x9fc03478` | |
| `airboot` (F) | `primary` → `go -noclose 0xbf200000`, `secondary` → `go -noclose 0xbf900000`: a jump into uncached memory-mapped flash, no copy to RAM (code at `0x9fc02ea8`). Bank A = flash offset `0x200000`, bank B = `0x900000` | |
| Bank as stored (L) | the decrypted inner payload: gzboot loader (plaintext MIPS, 22,432 bytes in 7.8.1) + gzip(kernel + md0) + zero padding; no `APPLE-FIRMWARE` header. ACPd decrypts at update; the AES key is not in CFE | gzboot (ARM stub + gzip), decrypted |
| Boot check | Adler-32 bank trailer ([below](#bank-trailer-a1392)) | none found |
| Fallback | to B only when A fails its checksum; B is then booted even if its own checksum fails; an A that passes but doesn't boot does not fall back | |
| Console | `CFE>` on the UART, ~1 s `BOOTDELAY` ([below](#cfe-console)) | |

### gzboot loader (A1392, F)

"NetBSD/MIPS Gzip Boot", built `Fri May 24 19:48:37 PDT 2019` (7.8.1 bank), zlib
`inflate 1.2.3`.

| Step | Where it runs | What |
|---|---|---|
| 1 | in place, flash (`0xbf200000`) | `t5 = t9` (own address); if ≠ link address `0x83000000`: copy the loader (to `0x830057a0`) into RAM at `0x83000000`, jump to `0x83000080` |
| 2 | RAM | clear BSS `0x82f10000`–`0x82f108b0`, `sp = 0x82f10830` |
| 3 | RAM | `a0` = gzip stream address rebased to the original location (`0xbf2057a0`): the compressed kernel is read in place from flash, not copied |
| 4 | RAM | call `main` at `0x83000aa0`: inflate (gzip header and CRC checked: `FATAL: CRC checksum mismatch`), start the kernel |

The inflated image is a raw kernel binary (not ELF), 16,240,576 bytes for 7.8.1, with md0
embedded.

### Bank trailer (A1392)

| Bank offset | Content |
|---|---|
| `0` … `len` | image: the decrypted inner payload (gzboot loader, gzip stream from `0x57a0` in 7.8.1, zero padding) |
| `len` … `0x6FFFE0` | not checked (stale data from earlier, larger writes may remain) |
| `0x6FFFE0` | Adler-32, big-endian, over `image[0:len]` |
| `0x6FFFE4` | `len`, big-endian |
| `0x6FFFE8` … end | `0xFF` |

| Image | `len` | Adler-32 | gzboot loader | gzip inflates to |
|---|---:|---|---:|---:|
| 7.8.1 | `0x5d0d34` | `ab7a9b4c` | 22,432 bytes | 16,240,576 bytes |
| 7.6.2 | `0x55ddbc` | `7c793aa9` | 22,144 bytes | 16,229,088 bytes |

## Verification

| Layer | Checks | Signature |
|---|---|---|
| CFE (A1392) | Adler-32 bank trailer; CRC on boot blocks | none: no `rsa`/`sha`/`sign`/`pubkey`/`certificate`/`secure boot` strings, no key modulus in the 512 KB image (F) |
| microboot (A1254, A1301) | none found | none found (A1301: no rsa/sha strings, partition 97 % erased) |
| ACPd update writer | `APPLE-FIRMWARE` magic, model ID, container Adler-32, bank size 3–7 MB, version ≥ `minS` | none; the only signature code in ACPd is HomeKit pairing (F) |
| Apple's update catalog | RSA signature over `version.xml`, chained to a bundled Apple Root CA | the `.basebinary` downloads themselves are plain HTTP ([security.md](security.md#trust-boundaries)) |

`minS` (anti-rollback floor) comes from the nvram key `apple-minver`: `76200.16` on the A1392;
the A1254 and A1301 have none (models.md). A correctly formed image with a valid checksum and
a version ≥ `minS` is accepted and booted; no key is needed (the encryption flag is optional,
[firmware.md](firmware.md#encryption)).

## Update paths (ACPd)

All gated by the admin password and the `updateROM` permission.

| ACP request | Effect |
|---|---|
| command 3 | synchronous "flash primary": `FUN_00699e90` → bank A (airpyrt-tools uses this) |
| command 4 | stub, returns -1 |
| commands 5 / 6 | bank B / bootloader, only if the `diag` property is set (`FUN_0067f05c`, also the `acp.setStaticConfig` gate) |
| `setprop` (0x15) streaming, pseudo-property `fupp` | upload: basic checks, image kept in RAM (AirPort Utility uses this) |
| same, `fust` | write the kept image to bank A in a thread (`FUN_00675504`); no reboot |
| same, `fuca` / `fugp` | always return an error |

| Writer `FUN_00699a84` | |
|---|---|
| Steps | peel the containers, decrypt flagged payloads (`FUN_00699324`), check model `0x73`, bank size 3–7 MB, version ≥ `minS`, write the bank with its checksum trailer, read bank A back (-6 on mismatch) |
| Targets | 1 → `flash0` (bank A), 2 → `flash1` (bank B), 3 → `flash4` (bootloader, ≤ 512 KB) |
| `fupp` check | target `0x80000001`, stops before writing. Not a usable dry run: it returns 0 for an image with one byte flipped (L) |
| Flash ioctls | `0x401c4665` geometry (total size + erase block), `0x80044664` erase one block; then read/write per 64 KB block |
| A → B copy | `FUN_00698ae8`, compiled out on the A1392 (gate `FUN_00649e48` returns 0): bank B keeps the previous image (reference unit: A = 7.8.1, B = 7.6.2) |
| Boot-time repair | ACPd checks bank A (`FUN_00698dac`: length + trailer); if A is bad and B good, copies B over A (`FUN_0069908c`) |
| On-device tools | `flashctl` (`probe`, `info`, `verify`, `dump`, `erase`, `format`, `lock`, `unlock`), `/sbin/eraseflash` |

## CFE console

A1392, from the help strings in the `flash4` image (F; not yet run on hardware). Stock
Broadcom CFE plus Apple's `airboot`, `checkimages`, `memchk`, `debugpll`.

| Command | Use | Writes |
|---|---|---|
| `help [command]` | usage | |
| `show devices` | device list (`flash0.primary`, `flash0.scfg` in the binary; the others presumably `flash0.<name>`) | |
| `show flash [-sectors]` | flash base address (memory-mapped), size, sectors | |
| `show memory`, `show heap`, `show time` | | |
| `printenv` | environment (`BOOTCMD`, `BOOTDELAY`, `ETH0_HWADDR`, …) | |
| `checkimages` | Adler-32 check of both banks | |
| `d [-b\|-h\|-w\|-q] [-p\|-v] addr len` | hex dump (`d 0x18040000 0x6F` = GPIO registers) | |
| `u addr len` | disassemble | |
| `ifconfig eth0 -addr=… -mask=…` | Ethernet up for TFTP | |
| `save host:file startaddr length` | TFTP-upload a memory region (with the flash address from `show flash`: a full dump) | |
| `load [-raw] [-tftp] [-addr=…] [-max=…] host:file` | fetch into RAM | |
| `boot [-raw\|-elf] [-z] [-tftp] host:file` | fetch and run. A bank image loaded raw into RAM should run: the [gzboot loader](#gzboot-loader-a1392-f) relocates itself, given `t9` = its address and a load range clear of `0x82f10000`–`0x830057a4` (untested) | |
| `memchk` | RAM test (destructive to RAM only) | RAM |
| `flash [-noheader] [-noerase] [-offset=…] [-size=…] source flashdevice` | program a partition from TFTP, FAT or another partition (`flash -noheader flash0.secondary flash0.primary` would copy bank B over A); `-noheader` skips CFE's header check | flash |
| `setenv -p` | refused: "persistant modification currently not allowed" | |

Dump speed: `d` over the serial line prints ~4.75 characters per byte, so at 115200 baud
768 KB takes ~5 min and 16 MB ~2 h; `save` over Ethernet is the practical path.

## Factory nvram (`flash3`)

`key=value\0` records (A1392: ~87 % erased). Read with the RPC
[`acp.getStaticConfig`](rpc-surface.md#read-all-called-on-the-a1392); rewritten by
`acp.setStaticConfig`, which can corrupt identity and radio calibration: never call it.

| Key | Meaning | Present on (L) |
|---|---|---|
| `apple-minver` | minimum firmware version → `minS` | A1392 |
| `apple-sn` | serial number | A1392, A1254, A1301 |
| `ethaddr` | Ethernet MAC | A1392, A1254, A1301 |
| `apple-sku` | regulatory region (`ETSI` on the reference unit; = `ssSK`) | A1392, A1254 |
| `radio-cal-ath0`, `radio-cal-ath1` | per-radio calibration (embeds the radio MACs) | A1392 |

## `syBL`

The bootloader version over ACP. Getter `FUN_0064a120` → `FUN_00691eb0`: reads 512 KB of
`/dev/rflash4.raw`, returns the text after `"APPLE BOOTLOADER INFO: "`, else `"UNKNOWN"`.
Read-only (set returns -11). Values per model: [models.md](models.md#flash-and-boot).
