# The A1392 hardware

A component-level reference for the 2012 dual-band AirPort Express (model **A1392**,
Apple board codename **k31**). Most of the chip identification here comes from two
published teardowns (credited at the end); the part this repo adds first-hand is the
**flash chip's contents** — the live partition map — which the teardowns don't cover, and
a correction to one of them (there *is* a discrete flash chip). The board photos in this
page are our own macro shots (see [Photos](#photos)).

For what the flash *does* at boot — the A/B firmware banks, CFE, the RAM-disk root, and
the "no secure boot" finding — see [boot.md](boot.md). This page is the physical side.

## Case access

The unit opens from the **bottom**: pry the white bottom panel off with a thin, flat tool
worked around the seam. It's held by plastic tabs that snap and tend to break — a plastic
spudger or putty knife spreads the load better than a screwdriver. The logic board lifts
out once the panel and the power-supply module are clear; power reaches the board through
the two screw-mount holes that overlap the PSU (silkscreened `V0` and `GND`).

<!-- ![A1392 with the bottom panel removed](images/case-open.jpg) -->
*Photo to add — `images/case-open.jpg`: the unit with the bottom panel off.*

## Components

| function | part | notes |
|---|---|---|
| **SoC / AP + 2.4 GHz radio** | Atheros **AR9344** ("Wasp") | MIPS **74Kc**, big-endian. NetBSD labels the platform `ar7240` (the AR934x family reuses that code); CFE's `WASP_BOOTSTRAP_REG` string confirms Wasp. |
| **5 GHz radio** | Atheros **AR9582** | the second radio — `ath1`/`wlan1`; 2×2, does the DFS work seen in `dmesg`. |
| **RAM** | 64 MB **DDR2** | reported as Hynix `H5PS5162GFR` (Rogue Amoeba) and Nanya `NT5TU32M16DG-AC` (Embedded Ideation) — same 64 MB, a second-sourced / board-revision difference. Matches `hw.physmem = 67108864`. |
| **Flash** | **Winbond W25Q128** SPI-NOR, **128 Mbit = 16 MB** | see below. Confirm the exact silkscreen from the macro photo. |
| **Audio DAC** | AKM **AK4430ET** | 24-bit / 192 kHz stereo — the analog + optical (TOSLINK) output; the optical jack-detect shows up as `auJD` over ACP. |
| **Power** | Delta 3.3 VDC / 2 A module | internal PSU brick; earlier single-band units used a Samsung dual-output supply. |

<!-- ![Logic board, top, shields removed](images/board-top.jpg) -->
*Photo to add — `images/board-top.jpg`: logic board, top side, RF cans removed, chips legible.*

<!-- ![Logic board, bottom](images/board-bottom.jpg) -->
*Photo to add — `images/board-bottom.jpg`: board underside.*

## The flash chip (our finding)

One teardown concluded there was **no flash chip** and guessed the firmware was baked into
the CPUs. That's wrong: there is a discrete **Winbond W25Q128 128 Mbit (16 MB) SPI-NOR**
(a small 8-pin SOIC, easy to miss next to the shields). We confirmed the 16 MB capacity
and, more usefully, read out **how it's partitioned** — which no teardown documents.

Live, over a read-only root session, `flashctl` and `sysctl` report five flash "disks"
(`hw.disknames = flash0 flash1 flash2 flash3 flash4 md0`) that together sum to exactly
16 MB:

| device | size | role |
|---|---:|---|
| `flash0` | 7 MB | firmware **bank A** (primary) |
| `flash1` | 7 MB | firmware **bank B** (secondary / failover) |
| `flash2` | 1.25 MB | **`/mnt/Flash`** — the only persistent, writable filesystem |
| `flash3` | 256 KB | **CFE nvram / factory data** (serial, MACs, radio calibration, region, `apple-minver`) |
| `flash4` | 512 KB | **Apple CFE bootloader** |

The two 7 MB banks are why an interrupted firmware write is survivable — CFE checksums the
primary and falls back to the secondary. `/` itself is not on flash at all: it's a ~11.5 MB
FFS **RAM disk** (`md0`) unpacked from the active bank at boot, so only `flash2` persists.
Full detail — sizes from `flashctl info`, the boot/verification flow, and the image format
— is in [boot.md](boot.md).

The Winbond part is also relevant for **off-board recovery**: a W25Q128 can be read and
written in place with a clip and a `flashrom`-capable programmer (SPI, 3.3 V), which — with
the lack of secure boot — is a complete unbrick and custom-firmware path even without the
serial header.

<!-- ![Flash chip markings](images/flash-chip.jpg) -->
*Photo to add — `images/flash-chip.jpg`: macro of the SPI-NOR silkscreen, to lock down the exact W25Q128 variant.*

## The debug header: serial + JTAG

The board carries an **unpopulated debug header** in the corner **next to the audio jack**
— exposed as soon as the bottom panel is off. It combines the console UART and the CPU's
JTAG on one pad cluster (~10 usable pads: `VCC`, `GND`, UART ×2, EJTAG ×6). Its layout
nearly matches the compact **TI 20-pin ARM JTAG** connector, but the two columns of pads
are offset, so it isn't a drop-in fit.

**Serial (UART):** two of the pads are the low-speed console.

- **115200 baud, 8 data bits, no parity, 1 stop bit, no flow control** (8N1)
- 3.3 V logic — an FT232RL-class USB-TTL adapter works
- The published teardown doesn't label which pad is **TX** vs **RX**; probe with a scope or
  logic analyser (our macro photo of the header, below, is meant to help pin the order).
- **A root shell is available on the serial console immediately, with no authentication.**
  Pressing a key during the ~1-second boot window drops you to the **`CFE>` bootloader
  console** (see [boot.md](boot.md)). So *physical* access is unauthenticated root and full
  bootloader control — independent of the `dbug`/SSH route in [dbug.md](dbug.md).

**JTAG:** the other six pads are **MIPS EJTAG** — `TDI`, `TDO`, `TCK`, `TMS`, `nTRST`,
`nSRST`. `TDO` was identified by GPIO/logic analysis in the referenced work; the two
reset-type pads (`nTRST`/`nSRST`) weren't individually distinguished. EJTAG gives
low-level halt/flash access — the belt-and-braces recovery path alongside serial.

With serial + JTAG (or just an SPI programmer on the flash), and a backup of the five
partitions taken first, the A1392 is effectively unbrickable.

<!-- ![Debug header macro](images/debug-header.jpg) -->
*Photo to add — `images/debug-header.jpg`: macro of the debug header by the audio jack, with pad positions visible (the key shot for mapping TX/RX and the EJTAG order).*

## Photos

The images referenced above are commented out until the files exist — drop a photo into
`docs/images/` under the given name and uncomment the matching `<!-- ![…](…) -->` line.
Most valuable shots, roughly in order:

1. `debug-header.jpg` — the header, macro, pads sharp (for the pinout).
2. `flash-chip.jpg` — the SPI-NOR silkscreen (to fix the exact W25Q128 variant).
3. `board-top.jpg` — top side, RF cans off, all main chips legible.
4. `board-bottom.jpg`, `case-open.jpg` — context shots.
5. Optional macros of the AR9344, AR9582, and AK4430ET markings.

Keep each image to a sensible size (long edge ~2000 px, ≲2 MB) so the repo stays light.

## Sources

- Embedded Ideation, *Dissecting the AirPort Express* (2014) — the debug header, serial
  console, EJTAG mapping, and the chip identities including the flash part:
  <https://www.embeddedideation.com/2014/03/dissecting-the-airport-express/>
- Rogue Amoeba, *AirPort Express (Dual-Band) Disassembly* (2012) — case teardown, board
  photos, and most of the component list:
  <https://weblog.rogueamoeba.com/2012/06/19/airport-express-disassembly/>

The flash partition map, the confirmation that a discrete SPI-NOR exists, and the boot /
verification behaviour in [boot.md](boot.md) are first-hand from an A1392 on firmware
7.8.1.
