# Hardware

Board-level data. SoC, RAM, radios and Ethernet for every measured model:
[models.md § Platform](models.md#platform). Flash contents and boot: [boot.md](boot.md).

## A1392 (AirPort Express 2012, board k31)

| Function | Part | Notes | Src |
|---|---|---|---|
| SoC + 2.4 GHz radio | Atheros AR9344 "Wasp", MIPS 74Kc, big-endian | NetBSD reports `hw.machine = ar7240` (AR934x reuses that platform code); CFE contains `WASP_BOOTSTRAP_REG` | E, F |
| 5 GHz radio | Atheros AR9582, 2×2 | `ath1` / `wlan1`; does DFS | E, L |
| RAM | 64 MB DDR2 | Hynix H5PS5162GFR (Rogue Amoeba) or Nanya NT5TU32M16DG-AC (Embedded Ideation); `hw.physmem = 67108864` | E, L |
| Flash | Winbond W25Q128BV SPI-NOR, 128 Mbit = 16 MB | under an EMI-shield anchor; Embedded Ideation's caption reads "25Q129BVEG", likely a typo | E |
| Audio DAC | AKM AK4430ET, 24-bit / 192 kHz | analog + optical (TOSLINK) out; optical jack-detect = ACP `auJD` | E, L |
| Power | Delta 3.3 V DC / 2 A module, internal | board power via the two screw holes over the PSU, silkscreen `V0` / `GND` | E |

### Case

| | |
|---|---|
| Opening | from the bottom: pry off the white bottom panel (plastic tabs, fragile; use a spudger) |
| Clip order | the two tabs on the rear-port side first, then the seven clips around the edge |
| Screws | logic board: Torx T8; power-cord connector: 2 × Torx T6 |
| Debug header | reachable with the board in place |

### Debug header

Unpopulated pad cluster in the corner next to the audio jack, ~10 usable pads. Layout close
to the TI 20-pin ARM JTAG connector, but the two pad columns are offset.

| Signal | Detail | Src |
|---|---|---|
| UART | 115200 8N1, no flow control, 3.3 V; TX/RX pad order not published | E |
| UART console | root shell with no authentication; a key during the ~1 s `BOOTDELAY` gives the [`CFE>` console](boot.md#cfe-console) | E |
| EJTAG | `TDI`, `TDO`, `TCK`, `TMS`, `nTRST`, `nSRST`; `TDO` identified, the two resets not told apart | E |
| Power | `VCC`, `GND` | E |

### Recovery paths

| Path | Needs |
|---|---|
| CFE console over the UART | header wiring; TFTP load and flash programming ([boot.md](boot.md#cfe-console)) |
| EJTAG | header wiring and an EJTAG probe |
| SPI programmer | the chip freed from the shield anchor, a clip (SOIC-8 assumed, unconfirmed), a `flashrom`-capable programmer at 3.3 V |

No path is blocked by a signature check ([boot.md § Verification](boot.md#verification)).

## Other models

No board-level data yet. Platform data from the running system: [models.md](models.md#platform).

## Sources

- Embedded Ideation, *Dissecting the AirPort Express* (2014): debug header, UART, EJTAG, chip
  IDs, the SPI flash and its partition names.
  <https://www.embeddedideation.com/2014/03/dissecting-the-airport-express/>
- Rogue Amoeba, *AirPort Express (Dual-Band) Disassembly* (2012): case, photos, component list.
  <https://weblog.rogueamoeba.com/2012/06/19/airport-express-disassembly/>
