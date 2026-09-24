# The ACP property dictionary (firmware 7.8.1)

`ACPd` exposes a flat namespace of **520 properties**, each a four-character code
(fourcc) with a type and a flags byte. This is the `getprop`/`setprop` layer of ACP
(TCP 5009, commands `0x14`/`0x15`) — distinct from the RPC layer (`0x19`, see
[rpc-surface.md](rpc-surface.md)). AirPort Utility is built on exactly these two
layers. This page is the dictionary: every fourcc, its type/flags from the binary,
and what a **read-only** sweep of a live A1392 returned for it.

The table itself (fourcc, type, flags) comes from `tools/proptab.py` reading the
property table in `ACPd` (VMA `0xc5af38`, 12-byte records, zero-terminated). The
live disposition column comes from a `getprop` sweep on **2026-09-24** of an A1392
(7.8.1) in its normal AP role. Related decoded structures live in
[wifi-blob.md](wifi-blob.md) (the `WiFi` blob) and [dbug.md](dbug.md) (the `dbug`
bitfield).

## How reads work

* **`getprop` is authenticated.** Every read carries the admin password in the ACP
  header key; a wrong password is rejected with `0xfffffff0` before any property is
  returned (confirmed live). There is **no unauthenticated read** — the "auth-required
  per property" idea doesn't apply: auth is at the connection, not per property.
* **Two ways to read.** A *named* get resolves each fourcc through
  `ACPGetPropertyDirect(fourcc, 0x20000, …)` (`FUN_00678890` case `0x14`, line 424),
  which may call that property's handler. A get for the wildcard fourcc `0xffffffff`
  instead enumerates ACPd's **materialized** value list directly (same function, the
  `local_268 == -1` branch) and calls **no** per-property handler — this is the
  airpyrt "dump all props" path, and 80 properties come back this way.
* **Reads used in this sweep:** the wildcard dump, plus one named `getprop` per
  non-action property. The 31 **action** properties (type 10) were **not**
  named-swept, because a named get would dispatch to their handler and some are
  destructive verbs (`acRB` reboot, `acFN`, `FLSH`, `fust`/`fuca` firmware update,
  `invr`, `ddEn`). No `setprop` was ever sent.

## Type codes

`ACPd` tags each property with a type. proptab.py already knew most; the sweep pinned
down the three that were unlabelled (3, 4, 11) from their live widths:

| code | name | notes |
|---|---|---|
| 1 | `byte` | 8-bit; also used for opaque byte buffers (`logm`, `auHK`) |
| 2 | `string` | NUL-terminated text |
| 3 | `int` | small integer (1 byte seen: `bjSd`) |
| 4 | `int16` | 16-bit integer (`tmpC` temperature, `raLC`, `auRR`) |
| 5 | `uint32` | 32-bit; the most common type (144 props) |
| 6 | `bool` | 1 byte, 0/1 |
| 7 | `ipv4` | 4-byte address |
| 8 | `mac` | 6-byte hardware address |
| 9 | `phys` | fixed binary struct (PHY/port info) |
| 10 | `action` | a verb, not a value — triggered by `setprop`, not read here |
| 11 | `fcc[]` | packed array of fourccs (`feat`, `prop`) |
| 12 | `ipv6` | 16-byte address |
| 13 | `data` | opaque blob; usually a `CFB0…` binary plist |

## Flags byte

The flags gate **writes**, not reads (from `ACPGetPropertyDirect` /
`ACPSetPropertyDirectEx`):

| bit | meaning |
|---|---|
| `0x04` | set needs privilege (`priv`) |
| `0x08` | set needs auth (`auth`) |
| `0x10` | set forces internal flag 0x10 |
| `0x20` | set refused (read-only) |
| `0x40` | value comes from a handler (`h40`) |
| `0x80` | handler-only, **indexed** (`h80`) — needs an interface/radio index |

## What the sweep found

520 properties, one live disposition each:

| disposition | count | meaning |
|---|---:|---|
| **readable** | 147 | 80 via the wildcard dump + 67 computed by a handler on named get |
| **absent** (`-10`, `0xfffffff6`) | 269 | no stored value in this configuration |
| **indexed** (`-6772`, `0xffffe58c`) | 65 | needs a radio/interface index — all are `ra**`/`rCh2` (flag `0x80`) |
| **action** (not swept) | 31 | type-10 verbs; read deliberately skipped |
| **no-data** (`-18`, `0xffffffee`) | 3 | `drTY`, `acEf`, `fuup` — handler had nothing to return |
| **n/a interface** (`-6711`) | 2 | `raM2`, `iMTU` |
| **n/a** (`-6720`) | 1 | `fugp` (no firmware update in progress) |
| **error** (`-5`) | 1 | `minV` |
| **readable, slow** | 1 | `FlSu` returns `0x01` but the handler takes ~13 s (a flash summary) |

The big takeaways:

* **The 65 `indexed` properties are the whole per-radio Wi-Fi set** (`raNm`, `raWM`,
  `raWE`, `raSt`, `raCh`, …). A bare `getprop` can't fetch them; they're read through
  the indexed `wifi.*` RPCs with a radio index (see [rpc-surface.md](rpc-surface.md)).
  This — not "auth" — is what makes them look unreadable.
* **`getprop` reads secrets back in cleartext.** `syPW` (admin password), `syPR` and
  `syGP` (guest-network password) are all in the materialized dump. Anyone who can
  authenticate once (or who reaches a base station still on the factory `public`) can
  read the admin password straight back out. Same for the Wi-Fi PMK inside the `WiFi`
  blob. (R6 security note.)
* **`prop` and `feat` are self-describing.** `prop` (type `fcc[]`) returns all 520
  property fourccs — an on-device copy of this table, and a clean cross-check that the
  static table matches the running firmware exactly. `feat` returns 89 capability
  fourccs the firmware advertises (below).
* **`syBL` exposes the bootloader:** `Apple CFE (bcm: 1.4.2 ath: 2012-1-15 apple: a4)
  Apr 23 2012` — the first concrete lead for the boot-chain road (R4).
* **`logm`** hands back the ~24 KB syslog ring buffer over ACP (may contain SSIDs and
  client IPs — kept out of this repo).
* **`drTY`** (the dry-run/dirty-plist property, R1) is present but returns `-18` (no
  data) unless a change set is staged.

### The 89 advertised capabilities (`feat`)

```
SAcC DMes NAOL NoMW AChS SDuW MCRt AltD AltI WPA- AES- SysL NTP- Prof BSTA
RaMS USB- TxPw WDS- NPrA NDeH NPMP RePr MuPr DisE DisW OMAC WPAW dh95 64RS
802a 802n afup ip6N ip6G i6G2 i6NR 6fkd 6dhc 6dhs aTns AP20 LEDI LEDC RsIN
RTCl UsDb FrWl DRes bpli EnSt AMon WSC- WdCh SySt DWDS snCS prni tACL wBNJ
TSN- ChUp dwNC liIP ip6F 6trd 6sec pSTA WPAu SCoW wiPL GstN DHRn drTY GNAs
grWD sbDB rsPr iEAP minR minr !mta bsps ptxt rbjr aclo GNEx IGCR iCLD
```

Recognisable ones: `WPA-`/`AES-`/`WPAu`/`WPAW` (Wi-Fi security), `802a`/`802n`
(radio modes), `USB-`/`prni` (USB printer sharing), `ip6*`/`6dhc`/`6sec` (IPv6),
`WSC-` (WPS), `GstN`/`GNEx` (guest network), `LEDI`/`LEDC` (LED), `UsDb` (the `dbug`
switch), `RTCl` (clock), `WDS-`/`DWDS` (WDS bridging), `drTY` (dry-run), `NTP-`.

### Example readable values (one stock A1392, identifiers and secrets withheld)

| fourcc | value |
|---|---|
| `syVs` / `syVr` | `7.8.1` / `f0` |
| `syAM` / `syAP` | `AirPort10,115` / `115` |
| `syDs` | `Apple Base Station V7.8.1` |
| `syBL` | `Apple CFE (bcm: 1.4.2 ath: 2012-1-15 apple: a4) Apr 23 2012` |
| `card` | `Atheros 802.11; driver 4.0.27.6; mac 768.3; phy 2457.9` |
| `ssSK` / `sySK` / `syRe` | `ETSI` / `3` / `8` |
| `dbug` | `0x3000` (SSH on; see dbug.md) |
| `LEDc` / `isAC` | `0` (auto) / `true` (on AC power) |
| `tmpC` | `0x018a` (≈ 39.4 °C board temperature) |
| `maAl` / `maPr` | `500` / `5` |
| `ntSV` | `time.apple.com` |
| `laIP` / `laSM` | `10.0.1.1` / `255.255.255.0` (factory default) |
| `dhBg`–`dhEn` / `dhLe` | `10.0.1.2`–`10.0.1.200` / `86400 s` (default DHCP scope) |
| `gnBg` | `172.16.42.2` (default guest scope) |
| `syFl` / `seFl` / `nvVs` | `0x80ac` / `0x10000` / `0x20001` |

Withheld from the repo (present but device-identifying or secret): `syNm` (default
name embeds the MAC), `sySN` (serial), `raMA`/`waMA`/`laMA` (MACs), `6Wad` (IPv6
embedding the MAC), `WiFi`/`raWE` (SSID + PMK), `raSR` (neighbour SSIDs), `logm`
(syslog), `auHK` (AirPlay host key), `syPW`/`syPR`/`syGP` (passwords). The full
unsanitised sweep is kept outside the repo (`rpc_live/2026-09-24-props/`).

## The full dictionary

Order matches the on-device table. `disposition` is what a read returned on
2026-09-24; `note` is the meaning where confirmed from the value or inferred from the
fourcc family (radio `ra**`, WAN `wa**`, LAN `la**`, DHCP `dh**`, guest `gn**`, IPv6
`6***`, AirPlay `au**`, USB/printer `USB*`/`prn*`, action `ac**`). Blank means
undetermined.

| # | fourcc | type | flags | disposition | note |
|---:|--------|------|-------|-------------|------|
| 1 | `buil` | string | 0x00 | readable (handler) | firmware build hash |
| 2 | `DynS` | data | 0x00 | readable (dumped) |  |
| 3 | `cfpf` | data | 0x00 | absent (-10) |  |
| 4 | `cloC` | data | 0x00 | absent (-10) |  |
| 5 | `cloD` | data | 0x00 | absent (-10) |  |
| 6 | `conf` | data | 0x00 | absent (-10) |  |
| 7 | `fire` | data | 0x00 | absent (-10) |  |
| 8 | `prob` | string | 0x04 priv | absent (-10) |  |
| 9 | `srcv` | string | 0x04 priv | readable (handler) | source/build revision |
| 10 | `syNm` | string | 0x00 | readable (dumped) | base-station name (user-set) |
| 11 | `syDN` | string | 0x00 | absent (-10) | system / base-station config |
| 12 | `syPI` | data | 0x00 | absent (-10) | system / base-station config |
| 13 | `syPW` | string | 0x00 | readable (dumped) | admin password (secret) |
| 14 | `syPR` | string | 0x00 | readable (dumped) | admin realm/second secret |
| 15 | `syGP` | string | 0x00 | readable (dumped) | guest-network password (secret) |
| 16 | `syCt` | string | 0x00 | absent (-10) | system / base-station config |
| 17 | `syLo` | string | 0x00 | absent (-10) | system / base-station config |
| 18 | `syDs` | string | 0x04 priv | readable (handler) | model description string |
| 19 | `syVs` | string | 0x04 priv | readable (handler) | firmware version (7.8.1) |
| 20 | `syVr` | string | 0x04 priv | readable (handler) | firmware variant |
| 21 | `syIn` | phys | 0x04 priv | readable (handler) | system / base-station config |
| 22 | `syFl` | uint32 | 0x00 | readable (handler) | system flags bitfield |
| 23 | `syAM` | string | 0x04 priv | readable (handler) | model id (AirPort10,115) |
| 24 | `syAP` | uint32 | 0x04 priv | readable (handler) | product id (115 = A1392) |
| 25 | `sySN` | string | 0x08 auth | readable (handler) | serial number (identifier) |
| 26 | `ssSN` | action | 0x08 auth | action (not read-swept) | system/security |
| 27 | `sySK` | uint32 | 0x00 | readable (dumped) | regulatory region index |
| 28 | `ssSK` | string | 0x08 auth | readable (handler) | regulatory domain (e.g. ETSI) |
| 29 | `syRe` | uint32 | 0x00 | readable (dumped) | region code |
| 30 | `syLR` | data | 0x44 priv,h40 | readable (handler) | system / base-station config |
| 31 | `syAR` | data | 0x44 priv,h40 | readable (handler) | system / base-station config |
| 32 | `syUT` | uint32 | 0x00 | readable (handler) | uptime/counter |
| 33 | `minV` | uint32 | 0x00 | error (-5) | minimum firmware version |
| 34 | `minS` | string | 0x00 | readable (handler) | minimum firmware string |
| 35 | `chip` | string | 0x00 | readable (handler) |  |
| 36 | `card` | string | 0x00 | readable (dumped) | WLAN chipset+driver string |
| 37 | `memF` | uint32 | 0x00 | absent (-10) | memory |
| 38 | `pool` | phys | 0x00 | absent (-10) |  |
| 39 | `tmpC` | int16 | 0x04 priv | readable (handler) | board temperature (0.1 C) |
| 40 | `RPMs` | uint32 | 0x00 | absent (-10) |  |
| 41 | `sySI` | data | 0x00 | readable (handler) | system / base-station config |
| 42 | `fDCY` | uint32 | 0x00 | absent (-10) |  |
| 43 | `TMEn` | uint32 | 0x00 | readable (handler) |  |
| 44 | `CLTM` | data | 0x00 | readable (handler) |  |
| 45 | `sPLL` | data | 0x00 | readable (handler) |  |
| 46 | `syTL` | string | 0x00 | absent (-10) | system / base-station config |
| 47 | `syST` | string | 0x00 | absent (-10) | system / base-station config |
| 48 | `sySt` | data | 0x04 priv | readable (handler) | system / base-station config |
| 49 | `syIg` | data | 0x00 | absent (-10) | system / base-station config |
| 50 | `syBL` | string | 0x00 | readable (handler) | bootloader/CFE version string |
| 51 | `time` | uint32 | 0x00 | readable (handler) |  |
| 52 | `timz` | data | 0x00 | absent (-10) |  |
| 53 | `usrd` | data | 0x00 | absent (-10) |  |
| 54 | `uuid` | byte | 0x04 priv | readable (handler) | device UUID (identifier) |
| 55 | `drTY` | data | 0x00 | no-data (-18) | dirty-plist / dry-run (see R1) |
| 56 | `sttE` | bool | 0x00 | absent (-10) |  |
| 57 | `sttF` | uint32 | 0x00 | absent (-10) |  |
| 58 | `stat` | data | 0x00 | absent (-10) |  |
| 59 | `diag` | bool | 0x04 priv | readable (dumped) | diagnostics flag |
| 60 | `paFR` | bool | 0x00 | absent (-10) |  |
| 61 | `raNm` | string | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 62 | `raCl` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 63 | `raSk` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 64 | `raWM` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 65 | `raEA` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 66 | `raWE` | byte | 0x80 h80 | indexed (-6772) | Wi-Fi key/PMK (secret) |
| 67 | `raCr` | byte | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 68 | `raKT` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 69 | `raNN` | byte | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 70 | `raGK` | byte | 0x80 h80 | indexed (-6772) | group key (secret) |
| 71 | `raHW` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 72 | `raCM` | bool | 0x00 | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 73 | `raRo` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 74 | `raCA` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 75 | `raCh` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 76 | `rCh2` | uint32 | 0x80 h80 | indexed (-6772) | radio channel (secondary) |
| 77 | `raWC` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 78 | `raDe` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 79 | `raMu` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 80 | `raLC` | int16 | 0x44 priv,h40 | readable (handler) | radio, per-interface (indexed - read via wifi.* RPC) |
| 81 | `raLF` | uint32 | 0x44 priv,h40 | readable (handler) | radio, per-interface (indexed - read via wifi.* RPC) |
| 82 | `ra1C` | bool | 0x84 priv,h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 83 | `raVs` | string | 0x04 priv | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 84 | `raMA` | mac | 0x48 auth,h40 | readable (handler) | radio MAC (identifier) |
| 85 | `raM2` | mac | 0x48 auth,h40 | n/a iface (-6711) | second radio MAC (identifier) |
| 86 | `raMO` | mac | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 87 | `raLO` | uint32 | 0x08 auth | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 88 | `raDS` | bool | 0x00 | readable (dumped) | radio, per-interface (indexed - read via wifi.* RPC) |
| 89 | `raNA` | bool | 0x00 | readable (dumped) | radio, per-interface (indexed - read via wifi.* RPC) |
| 90 | `raWB` | bool | 0x00 | readable (dumped) | radio, per-interface (indexed - read via wifi.* RPC) |
| 91 | `raIS` | uint32 | 0x04 priv | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 92 | `raMd` | int16 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 93 | `raPo` | int16 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 94 | `raPx` | int16 | 0x00 | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 95 | `raTr` | uint32 | 0x00 | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 96 | `raDt` | int16 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 97 | `raFC` | uint32 | 0x00 | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 98 | `raEC` | bool | 0x00 | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 99 | `raMX` | uint32 | 0x00 | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 100 | `raIE` | bool | 0x40 h40 | readable (handler) | radio, per-interface (indexed - read via wifi.* RPC) |
| 101 | `raII` | uint32 | 0x40 h40 | readable (handler) | radio, per-interface (indexed - read via wifi.* RPC) |
| 102 | `raB0` | int16 | 0x08 auth | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 103 | `raB1` | int16 | 0x08 auth | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 104 | `raB2` | int16 | 0x08 auth | absent (-10) | radio, per-interface (indexed - read via wifi.* RPC) |
| 105 | `raSt` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 106 | `APSR` | byte | 0x00 | absent (-10) |  |
| 107 | `raTX` | int | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 108 | `raRX` | int | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 109 | `raAC` | phys | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 110 | `raSL` | data | 0x40 h40 | readable (handler) | radio interface list |
| 111 | `raMI` | int16 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 112 | `raST` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 113 | `raDy` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 114 | `raEV` | int16 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 115 | `rTSN` | bool | 0x80 h80 | indexed (-6772) |  |
| 116 | `raSR` | data | 0x40 h40 | readable (handler) | Wi-Fi scan results (neighbour SSIDs) |
| 117 | `eaRA` | uint32 | 0x80 h80 | indexed (-6772) |  |
| 118 | `WiFi` | data | 0x00 | readable (dumped) | packed Wi-Fi security blob (SSID+PMK; see wifi-blob.md) |
| 119 | `rCAL` | data | 0x40 h40 | readable (handler) |  |
| 120 | `moPN` | string | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 121 | `moAP` | string | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 122 | `moUN` | string | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 123 | `moPW` | string | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 124 | `moIS` | string | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 125 | `moLS` | string | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 126 | `moLI` | uint32 | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 127 | `moID` | uint32 | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 128 | `moDT` | bool | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 129 | `moPD` | bool | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 130 | `moAD` | bool | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 131 | `moCC` | uint32 | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 132 | `moCR` | uint32 | 0x04 priv | absent (-10) | legacy modem/PPP dial config |
| 133 | `moCI` | uint32 | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 134 | ` moM` | uint32 | 0x00 | absent (-10) |  |
| 135 | `moVs` | string | 0x04 priv | absent (-10) | legacy modem/PPP dial config |
| 136 | `moMP` | uint32 | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 137 | `moMF` | uint32 | 0x00 | absent (-10) | legacy modem/PPP dial config |
| 138 | `moFV` | string | 0x04 priv | absent (-10) | legacy modem/PPP dial config |
| 139 | `pdFl` | uint32 | 0x00 | absent (-10) | PPPoE dial config |
| 140 | `pdUN` | string | 0x00 | absent (-10) | PPPoE dial config |
| 141 | `pdPW` | string | 0x00 | absent (-10) | PPPoE dial config |
| 142 | `pdAR` | uint32 | 0x00 | absent (-10) | PPPoE dial config |
| 143 | `pdID` | uint32 | 0x00 | absent (-10) | PPPoE dial config |
| 144 | `pdMC` | uint32 | 0x00 | absent (-10) | PPPoE dial config |
| 145 | `peSN` | string | 0x00 | absent (-10) | PPPoE config |
| 146 | `peUN` | string | 0x00 | absent (-10) | PPPoE config |
| 147 | `pePW` | string | 0x00 | absent (-10) | PPPoE config |
| 148 | `peSC` | bool | 0x00 | absent (-10) | PPPoE config |
| 149 | `peAC` | bool | 0x00 | absent (-10) | PPPoE config |
| 150 | `peID` | uint32 | 0x00 | absent (-10) | PPPoE config |
| 151 | `peAO` | bool | 0x00 | absent (-10) | PPPoE config |
| 152 | `waCV` | uint32 | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 153 | `waIn` | uint32 | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 154 | `waD1` | ipv4 | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 155 | `waD2` | ipv4 | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 156 | `waD3` | ipv4 | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 157 | `waC1` | ipv4 | 0x04 priv | readable (dumped) | WAN interface (IPv4) |
| 158 | `waC2` | ipv4 | 0x04 priv | readable (dumped) | WAN interface (IPv4) |
| 159 | `waC3` | ipv4 | 0x04 priv | readable (dumped) | WAN interface (IPv4) |
| 160 | `waIP` | ipv4 | 0x00 | readable (dumped) | WAN IPv4 |
| 161 | `waSM` | ipv4 | 0x00 | readable (dumped) | WAN netmask |
| 162 | `waRA` | ipv4 | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 163 | `waDC` | string | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 164 | `waDS` | bool | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 165 | `waMA` | mac | 0x08 auth | readable (handler) | WAN MAC (identifier) |
| 166 | `waMO` | mac | 0x00 | absent (-10) | WAN interface (IPv4) |
| 167 | `waDN` | string | 0x00 | absent (-10) | WAN interface (IPv4) |
| 168 | `waCD` | string | 0x00 | absent (-10) | WAN interface (IPv4) |
| 169 | `waIS` | uint32 | 0x04 priv | readable (handler) | WAN interface (IPv4) |
| 170 | `waNM` | bool | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 171 | `waSD` | uint32 | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 172 | `waFF` | bool | 0x00 | absent (-10) | WAN interface (IPv4) |
| 173 | `waRO` | bool | 0x40 h40 | readable (handler) | WAN interface (IPv4) |
| 174 | `waW1` | ipv4 | 0x00 | absent (-10) | WAN interface (IPv4) |
| 175 | `waW2` | ipv4 | 0x00 | absent (-10) | WAN interface (IPv4) |
| 176 | `waW3` | ipv4 | 0x00 | absent (-10) | WAN interface (IPv4) |
| 177 | `waLL` | ipv4 | 0x00 | readable (dumped) | WAN interface (IPv4) |
| 178 | `waUB` | bool | 0x00 | absent (-10) | WAN interface (IPv4) |
| 179 | `waDI` | data | 0x00 | readable (handler) | WAN interface (IPv4) |
| 180 | `laCV` | uint32 | 0x00 | readable (dumped) | LAN interface (IPv4) |
| 181 | `laIP` | ipv4 | 0x00 | readable (dumped) | LAN IPv4 |
| 182 | `laSM` | ipv4 | 0x00 | readable (dumped) | LAN netmask |
| 183 | `laRA` | ipv4 | 0x00 | absent (-10) | LAN interface (IPv4) |
| 184 | `laDC` | string | 0x00 | absent (-10) | LAN interface (IPv4) |
| 185 | `laDS` | bool | 0x00 | readable (dumped) | LAN interface (IPv4) |
| 186 | `laNA` | bool | 0x00 | readable (dumped) | LAN interface (IPv4) |
| 187 | `laMA` | mac | 0x04 priv | readable (handler) | LAN MAC (identifier) |
| 188 | `laIS` | uint32 | 0x04 priv | readable (handler) | LAN interface (IPv4) |
| 189 | `laSD` | uint32 | 0x00 | readable (dumped) | LAN interface (IPv4) |
| 190 | `laIA` | uint32 | 0x00 | absent (-10) | LAN interface (IPv4) |
| 191 | `gn6?` | bool | 0x00 | readable (dumped) | guest-network DHCP scope |
| 192 | `gn6A` | ipv6 | 0x00 | absent (-10) | guest-network DHCP scope |
| 193 | `gn6P` | uint32 | 0x00 | absent (-10) | guest-network DHCP scope |
| 194 | `dhFl` | uint32 | 0x00 | readable (dumped) | DHCP server (LAN scope) |
| 195 | `dhBg` | ipv4 | 0x00 | readable (dumped) | DHCP server (LAN scope) |
| 196 | `dhEn` | ipv4 | 0x00 | readable (dumped) | DHCP server (LAN scope) |
| 197 | `dhSN` | ipv4 | 0x00 | readable (dumped) | DHCP server (LAN scope) |
| 198 | `dhRo` | ipv4 | 0x00 | readable (dumped) | DHCP server (LAN scope) |
| 199 | `dhLe` | uint32 | 0x00 | readable (dumped) | DHCP server (LAN scope) |
| 200 | `dhMg` | string | 0x00 | absent (-10) | DHCP server (LAN scope) |
| 201 | `dh95` | string | 0x00 | absent (-10) | DHCP server (LAN scope) |
| 202 | `DRes` | data | 0x00 | absent (-10) |  |
| 203 | `dhWA` | bool | 0x00 | absent (-10) | DHCP server (LAN scope) |
| 204 | `dhDS` | ipv4 | 0x00 | readable (dumped) | DHCP server (secondary scope) |
| 205 | `dhDB` | ipv4 | 0x00 | readable (dumped) | DHCP server (secondary scope) |
| 206 | `dhDE` | ipv4 | 0x00 | readable (dumped) | DHCP server (secondary scope) |
| 207 | `dhDL` | uint32 | 0x00 | readable (dumped) | DHCP server (secondary scope) |
| 208 | `dhSL` | data | 0x40 h40 | readable (handler) | DHCP server (LAN scope) |
| 209 | `gnFl` | uint32 | 0x00 | readable (dumped) | guest-network DHCP scope |
| 210 | `gnBg` | ipv4 | 0x00 | readable (dumped) | guest-network DHCP scope |
| 211 | `gnEn` | ipv4 | 0x00 | readable (dumped) | guest-network DHCP scope |
| 212 | `gnSN` | ipv4 | 0x00 | readable (dumped) | guest-network DHCP scope |
| 213 | `gnRo` | ipv4 | 0x00 | readable (dumped) | guest-network DHCP scope |
| 214 | `gnLe` | uint32 | 0x00 | readable (dumped) | guest-network DHCP scope |
| 215 | `gnMg` | string | 0x00 | absent (-10) | guest-network DHCP scope |
| 216 | `gn95` | string | 0x00 | absent (-10) | guest-network DHCP scope |
| 217 | `gnDi` | bool | 0x00 | absent (-10) | guest-network DHCP scope |
| 218 | `naFl` | uint32 | 0x00 | readable (dumped) | NAT config |
| 219 | `naBg` | ipv4 | 0x00 | absent (-10) | NAT config |
| 220 | `naEn` | ipv4 | 0x00 | absent (-10) | NAT config |
| 221 | `naSN` | ipv4 | 0x00 | absent (-10) | NAT config |
| 222 | `naRo` | ipv4 | 0x00 | absent (-10) | NAT config |
| 223 | `naAF` | uint32 | 0x00 | absent (-10) | NAT config |
| 224 | `nDMZ` | ipv4 | 0x00 | absent (-10) |  |
| 225 | `pmPI` | ipv4 | 0x00 | absent (-10) |  |
| 226 | `pmPS` | ipv4 | 0x00 | absent (-10) |  |
| 227 | `pmPR` | ipv4 | 0x00 | absent (-10) |  |
| 228 | `pmTa` | phys | 0x00 | absent (-10) |  |
| 229 | `acEn` | bool | 0x80 h80 | indexed (-6772) | action verb |
| 230 | `acTa` | phys | 0x80 h80 | indexed (-6772) | action verb |
| 231 | `tACL` | data | 0x00 | absent (-10) |  |
| 232 | `wdFl` | uint32 | 0x80 h80 | indexed (-6772) |  |
| 233 | `wdLs` | phys | 0x80 h80 | indexed (-6772) |  |
| 234 | `dWDS` | bool | 0x80 h80 | indexed (-6772) | dynamic WDS |
| 235 | `cWDS` | bool | 0x80 h80 | indexed (-6772) |  |
| 236 | `dwFl` | uint32 | 0x80 h80 | indexed (-6772) |  |
| 237 | `raFl` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 238 | `raI1` | ipv4 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 239 | `raTm` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 240 | `raAu` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 241 | `raAc` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 242 | `raSe` | string | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 243 | `raRe` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 244 | `raF2` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 245 | `raI2` | ipv4 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 246 | `raT2` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 247 | `raU2` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 248 | `raC2` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 249 | `raS2` | string | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 250 | `raR2` | uint32 | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 251 | `raCi` | bool | 0x80 h80 | indexed (-6772) | radio, per-interface (indexed - read via wifi.* RPC) |
| 252 | `ntSV` | string | 0x00 | readable (dumped) | NTP server host |
| 253 | `ntpC` | string | 0x00 | absent (-10) | NTP config |
| 254 | `smtp` | string | 0x00 | absent (-10) |  |
| 255 | `slog` | string | 0x00 | absent (-10) | syslog config |
| 256 | `slgC` | string | 0x00 | absent (-10) | syslog config |
| 257 | `slCl` | ipv4 | 0x00 | absent (-10) | syslog config |
| 258 | `slvl` | uint32 | 0x00 | readable (dumped) | syslog config |
| 259 | `slfl` | uint32 | 0x00 | readable (dumped) | syslog config |
| 260 | `logm` | byte | 0x00 | readable (handler) | syslog ring buffer (~24 KB; may contain SSIDs/IPs) |
| 261 | `snAF` | uint32 | 0x00 | readable (dumped) | SNMP/notify config |
| 262 | `snLW` | phys | 0x00 | absent (-10) | SNMP/notify config |
| 263 | `snLL` | phys | 0x00 | absent (-10) | SNMP/notify config |
| 264 | `snRW` | string | 0x00 | absent (-10) | SNMP/notify config |
| 265 | `snWW` | string | 0x00 | absent (-10) | SNMP/notify config |
| 266 | `snRL` | string | 0x00 | absent (-10) | SNMP/notify config |
| 267 | `snWL` | string | 0x00 | absent (-10) | SNMP/notify config |
| 268 | `snCS` | string | 0x00 | absent (-10) | SNMP/notify config |
| 269 | `srtA` | uint32 | 0x00 | absent (-10) |  |
| 270 | `srtF` | uint32 | 0x00 | absent (-10) |  |
| 271 | `upsF` | uint32 | 0x00 | absent (-10) |  |
| 272 | `usbF` | uint32 | 0x00 | absent (-10) |  |
| 273 | `USBi` | data | 0x00 | readable (handler) | USB / printer sharing |
| 274 | `USBL` | int16 | 0x00 | absent (-10) | USB / printer sharing |
| 275 | `USBR` | int16 | 0x00 | absent (-10) | USB / printer sharing |
| 276 | `USBO` | int16 | 0x00 | absent (-10) | USB / printer sharing |
| 277 | `USBs` | int | 0x00 | absent (-10) | USB / printer sharing |
| 278 | `USBo` | uint32 | 0x00 | absent (-10) | USB / printer sharing |
| 279 | `USBh` | int | 0x00 | absent (-10) | USB / printer sharing |
| 280 | `USBb` | uint32 | 0x00 | absent (-10) | USB / printer sharing |
| 281 | `USBn` | int | 0x00 | absent (-10) | USB / printer sharing |
| 282 | `prni` | data | 0x00 | readable (handler) | printer sharing |
| 283 | `prnM` | bool | 0x00 | absent (-10) | printer sharing |
| 284 | `prnI` | string | 0x00 | readable (handler) | printer sharing |
| 285 | `prnR` | phys | 0x00 | readable (handler) | printer sharing |
| 286 | `RUdv` | data | 0x00 | absent (-10) | recovery update |
| 287 | `RUfl` | uint32 | 0x00 | absent (-10) | recovery update |
| 288 | `MaSt` | data | 0x00 | absent (-10) |  |
| 289 | `SMBw` | string | 0x00 | absent (-10) |  |
| 290 | `SMBs` | string | 0x00 | absent (-10) |  |
| 291 | `fssp` | string | 0x00 | absent (-10) |  |
| 292 | `diSD` | uint32 | 0x00 | absent (-10) |  |
| 293 | `diCS` | uint32 | 0x00 | absent (-10) |  |
| 294 | `deSt` | data | 0x10 flag10 | absent (-10) |  |
| 295 | `daSt` | data | 0x10 flag10 | absent (-10) |  |
| 296 | `dmSt` | data | 0x10 flag10 | absent (-10) |  |
| 297 | `adNm` | string | 0x00 | absent (-10) |  |
| 298 | `adBD` | bool | 0x00 | absent (-10) |  |
| 299 | `adAD` | bool | 0x00 | absent (-10) |  |
| 300 | `adHU` | byte | 0x04 priv | absent (-10) |  |
| 301 | `IDNm` | string | 0x00 | absent (-10) |  |
| 302 | `seFl` | uint32 | 0x04 priv | readable (handler) | feature-list selector |
| 303 | `nvVs` | uint32 | 0x00 | readable (dumped) | NVRAM layout version |
| 304 | `dbRC` | uint32 | 0x00 | absent (-10) | debug |
| 305 | `dbug` | uint32 | 0x00 | readable (dumped) | debug bitfield (see dbug.md) |
| 306 | `dlvl` | uint32 | 0x00 | absent (-10) |  |
| 307 | `dcmd` | action | 0x00 | action (not read-swept) |  |
| 308 | `dsps` | uint32 | 0x00 | absent (-10) |  |
| 309 | `logC` | string | 0x00 | absent (-10) |  |
| 310 | `cver` | uint32 | 0x00 | absent (-10) |  |
| 311 | `ctim` | uint32 | 0x00 | readable (dumped) | join/config gate token |
| 312 | `svMd` | uint32 | 0x00 | absent (-10) |  |
| 313 | `serM` | uint32 | 0x00 | absent (-10) |  |
| 314 | `serT` | uint32 | 0x00 | absent (-10) |  |
| 315 | `emNo` | string | 0x00 | absent (-10) |  |
| 316 | `effF` | uint32 | 0x00 | absent (-10) |  |
| 317 | `LLnk` | uint32 | 0x04 priv | readable (handler) |  |
| 318 | `WLnk` | uint32 | 0x04 priv | readable (handler) |  |
| 319 | `PHYS` | phys | 0x00 | readable (handler) |  |
| 320 | `Rnfo` | uint32 | 0x04 priv | absent (-10) |  |
| 321 | `evtL` | byte | 0x00 | absent (-10) |  |
| 322 | `isAC` | bool | 0x00 | readable (handler) | on AC power |
| 323 | `Adet` | uint32 | 0x04 priv | absent (-10) |  |
| 324 | `Prof` | byte | 0x00 | absent (-10) |  |
| 325 | `maAl` | uint32 | 0x00 | readable (handler) | max clients / assoc limit |
| 326 | `maPr` | uint32 | 0x00 | readable (handler) |  |
| 327 | `leAc` | uint32 | 0x00 | readable (dumped) |  |
| 328 | `APID` | uint32 | 0x04 priv | readable (handler) | product id (mirror of syAP) |
| 329 | `AAU ` | bool | 0x00 | absent (-10) |  |
| 330 | `lcVs` | string | 0x00 | absent (-10) |  |
| 331 | `iMTU` | uint32 | 0x40 h40 | n/a iface (-6711) |  |
| 332 | `wsci` | data | 0x00 | readable (handler) |  |
| 333 | `FlSu` | bool | 0x00 | readable (slow ~13s) | flash summary (slow read ~13s) |
| 334 | `acRB` | action | 0x00 | action (not read-swept) | action: reset/restart verb |
| 335 | `acRI` | action | 0x00 | action (not read-swept) | action: reset/restart verb |
| 336 | `acPC` | action | 0x00 | action (not read-swept) | action: power/config verb |
| 337 | `acDD` | action | 0x00 | action (not read-swept) | action: config verb |
| 338 | `acPD` | action | 0x00 | action (not read-swept) | action: power/config verb |
| 339 | `acPG` | action | 0x04 priv | action (not read-swept) | action: power/config verb |
| 340 | `acDS` | action | 0x04 priv | action (not read-swept) | action: config verb |
| 341 | `acFN` | action | 0x00 | action (not read-swept) | action: factory verb |
| 342 | `acRP` | action | 0x00 | action (not read-swept) | action: reset/restart verb |
| 343 | `acRN` | action | 0x00 | action (not read-swept) | action: reset/restart verb |
| 344 | `acRF` | action | 0x00 | action (not read-swept) | action: reset/restart verb |
| 345 | `MdmH` | action | 0x04 priv | action (not read-swept) |  |
| 346 | `dirf` | action | 0x00 | action (not read-swept) |  |
| 347 | `Afrc` | uint32 | 0x00 | absent (-10) |  |
| 348 | `lebl` | action | 0x00 | action (not read-swept) |  |
| 349 | `lebs` | action | 0x00 | action (not read-swept) |  |
| 350 | `LEDc` | uint32 | 0x00 | readable (handler) | front LED control (see props.py) |
| 351 | `acEf` | string | 0x00 | no-data (-18) | action verb |
| 352 | `invr` | action | 0x00 | action (not read-swept) |  |
| 353 | `FLSH` | action | 0x00 | action (not read-swept) |  |
| 354 | `acPL` | action | 0x00 | action (not read-swept) | action: power/config verb |
| 355 | `rReg` | action | 0x00 | action (not read-swept) |  |
| 356 | `dReg` | action | 0x00 | action (not read-swept) |  |
| 357 | `play` | action | 0x00 | action (not read-swept) |  |
| 358 | `paus` | action | 0x00 | action (not read-swept) |  |
| 359 | `ffwd` | action | 0x00 | action (not read-swept) |  |
| 360 | `rwnd` | action | 0x00 | action (not read-swept) |  |
| 361 | `itun` | string | 0x00 | absent (-10) |  |
| 362 | `plls` | string | 0x00 | absent (-10) |  |
| 363 | `User` | string | 0x00 | absent (-10) |  |
| 364 | `Pass` | string | 0x00 | absent (-10) |  |
| 365 | `itIP` | uint32 | 0x00 | absent (-10) |  |
| 366 | `itpt` | int16 | 0x00 | absent (-10) |  |
| 367 | `daap` | uint32 | 0x00 | absent (-10) |  |
| 368 | `song` | string | 0x00 | absent (-10) |  |
| 369 | `arti` | string | 0x00 | absent (-10) |  |
| 370 | `albm` | string | 0x00 | absent (-10) |  |
| 371 | `volm` | uint32 | 0x00 | absent (-10) |  |
| 372 | `rvol` | uint32 | 0x00 | absent (-10) |  |
| 373 | `Tcnt` | uint32 | 0x00 | absent (-10) |  |
| 374 | `Bcnt` | uint32 | 0x00 | absent (-10) |  |
| 375 | `shfl` | int | 0x00 | absent (-10) |  |
| 376 | `rept` | int | 0x00 | absent (-10) |  |
| 377 | `auPr` | bool | 0x04 priv | readable (handler) | AirPlay / audio |
| 378 | `auJD` | uint32 | 0x00 | readable (handler) | AirPlay / audio |
| 379 | `auNN` | string | 0x00 | absent (-10) | AirPlay / audio |
| 380 | `auNP` | string | 0x00 | absent (-10) | AirPlay / audio |
| 381 | `aFrq` | uint32 | 0x00 | absent (-10) |  |
| 382 | `aChn` | int | 0x00 | absent (-10) |  |
| 383 | `aLvl` | uint32 | 0x00 | absent (-10) |  |
| 384 | `aPat` | bool | 0x00 | absent (-10) |  |
| 385 | `aSta` | action | 0x00 | action (not read-swept) |  |
| 386 | `aStp` | action | 0x00 | action (not read-swept) |  |
| 387 | `auCC` | uint32 | 0x00 | readable (handler) | AirPlay / audio |
| 388 | `acmp` | bool | 0x00 | absent (-10) | action verb |
| 389 | `aenc` | bool | 0x00 | absent (-10) |  |
| 390 | `anBf` | uint32 | 0x00 | absent (-10) |  |
| 391 | `aWan` | bool | 0x00 | absent (-10) |  |
| 392 | `auRR` | int16 | 0x00 | readable (dumped) | AirPlay / audio |
| 393 | `auMt` | bool | 0x00 | absent (-10) | AirPlay / audio |
| 394 | `aDCP` | string | 0x00 | absent (-10) |  |
| 395 | `DCPc` | string | 0x00 | absent (-10) |  |
| 396 | `DACP` | bool | 0x00 | absent (-10) |  |
| 397 | `DCPi` | bool | 0x00 | absent (-10) |  |
| 398 | `auSl` | uint32 | 0x00 | absent (-10) | AirPlay / audio |
| 399 | `auFl` | uint32 | 0x00 | absent (-10) | AirPlay / audio |
| 400 | `auHK` | byte | 0x00 | readable (dumped) | AirPlay host key (secret) |
| 401 | `auHE` | bool | 0x00 | readable (dumped) | AirPlay / audio |
| 402 | `fe01` | uint32 | 0x04 priv | readable (handler) | feature/flag |
| 403 | `feat` | fcc[] | 0x00 | readable (handler) | capability list (89 fourccs) |
| 404 | `prop` | fcc[] | 0x00 | readable (handler) | all property fourccs (=520) |
| 405 | `hw01` | uint32 | 0x04 priv | readable (handler) | hardware revision |
| 406 | `fltr` | string | 0x00 | absent (-10) |  |
| 407 | `wdel` | uint32 | 0x00 | absent (-10) |  |
| 408 | `plEB` | bool | 0x00 | absent (-10) |  |
| 409 | `rWSC` | bool | 0x00 | absent (-10) |  |
| 410 | `uDFS` | bool | 0x00 | absent (-10) |  |
| 411 | `dWPA` | int | 0x40 h40 | absent (-10) |  |
| 412 | `dpFF` | uint32 | 0x00 | absent (-10) |  |
| 413 | `duLF` | uint32 | 0x00 | absent (-10) |  |
| 414 | `ieHT` | int | 0x00 | absent (-10) |  |
| 415 | `dwlX` | uint32 | 0x00 | absent (-10) |  |
| 416 | `dd11` | uint32 | 0x00 | absent (-10) | debug/diag |
| 417 | `dRdr` | bool | 0x00 | absent (-10) |  |
| 418 | `dotD` | bool | 0x00 | absent (-10) |  |
| 419 | `dotH` | bool | 0x00 | absent (-10) |  |
| 420 | `dPwr` | uint32 | 0x00 | absent (-10) |  |
| 421 | `wlBR` | bool | 0x00 | absent (-10) |  |
| 422 | `iTIM` | bool | 0x00 | absent (-10) |  |
| 423 | `idAG` | uint32 | 0x00 | absent (-10) |  |
| 424 | `mvFL` | string | 0x00 | absent (-10) |  |
| 425 | `mvFM` | string | 0x00 | absent (-10) |  |
| 426 | `dPPP` | bool | 0x00 | absent (-10) |  |
| 427 | `!mta` | bool | 0x00 | absent (-10) |  |
| 428 | `minR` | bool | 0x00 | absent (-10) |  |
| 429 | `SpTr` | bool | 0x00 | absent (-10) |  |
| 430 | `dRBT` | uint32 | 0x00 | absent (-10) |  |
| 431 | `dRIR` | data | 0x00 | absent (-10) |  |
| 432 | `fxEB` | byte | 0x30 flag10,ro | absent (-10) |  |
| 433 | `fxID` | uint32 | 0x30 flag10,ro | absent (-10) |  |
| 434 | `fuup` | byte | 0x00 | no-data (-18) | firmware-update upload state |
| 435 | `fust` | action | 0x00 | action (not read-swept) | firmware update |
| 436 | `fuca` | action | 0x00 | action (not read-swept) | firmware update |
| 437 | `fugp` | string | 0x04 priv | n/a (-6720) | firmware-update progress |
| 438 | `cks1` | uint32 | 0x14 priv,flag10 | readable (handler) | firmware image checksum |
| 439 | `cks2` | uint32 | 0x14 priv,flag10 | readable (handler) | firmware image checksum |
| 440 | `ddBg` | data | 0x00 | absent (-10) | debug/diag |
| 441 | `ddEn` | action | 0x00 | action (not read-swept) | debug/diag |
| 442 | `ddIn` | data | 0x04 priv | absent (-10) | debug/diag |
| 443 | `ddSm` | data | 0x04 priv | absent (-10) | debug/diag |
| 444 | `6cfg` | uint32 | 0x00 | readable (dumped) | IPv6 config |
| 445 | `6aut` | bool | 0x00 | readable (dumped) | IPv6 config |
| 446 | `6Qpd` | bool | 0x00 | absent (-10) | IPv6 config |
| 447 | `6Wad` | ipv6 | 0x00 | readable (handler) | WAN IPv6 (embeds MAC) |
| 448 | `6Wfx` | uint32 | 0x00 | absent (-10) | IPv6 config |
| 449 | `6Wgw` | ipv6 | 0x00 | readable (handler) | IPv6 config |
| 450 | `6Wte` | ipv4 | 0x00 | absent (-10) | IPv6 config |
| 451 | `6Lfw` | bool | 0x00 | readable (dumped) | IPv6 config |
| 452 | `6Lad` | ipv6 | 0x00 | absent (-10) | IPv6 config |
| 453 | `6Lfx` | uint32 | 0x00 | absent (-10) | IPv6 config |
| 454 | `6sfw` | bool | 0x00 | absent (-10) | IPv6 config |
| 455 | `6pmp` | bool | 0x00 | absent (-10) | IPv6 config |
| 456 | `6trd` | bool | 0x00 | absent (-10) | IPv6 config |
| 457 | `6sec` | bool | 0x00 | absent (-10) | IPv6 config |
| 458 | `6fwl` | data | 0x00 | absent (-10) | IPv6 config |
| 459 | `6NS1` | ipv6 | 0x00 | absent (-10) | IPv6 config |
| 460 | `6NS2` | ipv6 | 0x00 | absent (-10) | IPv6 config |
| 461 | `6NS3` | ipv6 | 0x00 | absent (-10) | IPv6 config |
| 462 | `6ahr` | bool | 0x00 | absent (-10) | IPv6 config |
| 463 | `6dhs` | bool | 0x00 | absent (-10) | IPv6 config |
| 464 | `6dso` | uint32 | 0x00 | absent (-10) | IPv6 config |
| 465 | `6PDa` | ipv6 | 0x00 | absent (-10) | IPv6 config |
| 466 | `6PDl` | uint32 | 0x00 | absent (-10) | IPv6 config |
| 467 | `6vlt` | uint32 | 0x00 | absent (-10) | IPv6 config |
| 468 | `6plt` | uint32 | 0x00 | absent (-10) | IPv6 config |
| 469 | `6CWa` | ipv6 | 0x04 priv | readable (dumped) | IPv6 config |
| 470 | `6CWp` | uint32 | 0x04 priv | readable (dumped) | IPv6 config |
| 471 | `6CWg` | ipv6 | 0x04 priv | readable (dumped) | IPv6 config |
| 472 | `6CLa` | ipv6 | 0x04 priv | readable (dumped) | IPv6 config |
| 473 | `6NSa` | ipv6 | 0x04 priv | readable (dumped) | IPv6 config |
| 474 | `6NSb` | ipv6 | 0x04 priv | readable (dumped) | IPv6 config |
| 475 | `6NSc` | ipv6 | 0x04 priv | readable (dumped) | IPv6 config |
| 476 | `6CPa` | ipv6 | 0x04 priv | readable (dumped) | IPv6 config |
| 477 | `6CPl` | uint32 | 0x04 priv | readable (dumped) | IPv6 config |
| 478 | `6!at` | bool | 0x00 | readable (dumped) | IPv6 config |
| 479 | `rteI` | data | 0x04 priv | readable (handler) |  |
| 480 | `PCLI` | string | 0x00 | absent (-10) |  |
| 481 | `dxEM` | uint32 | 0x80 h80 | indexed (-6772) |  |
| 482 | `dxID` | string | 0x80 h80 | indexed (-6772) |  |
| 483 | `dxAI` | string | 0x80 h80 | indexed (-6772) |  |
| 484 | `dxIP` | string | 0x80 h80 | indexed (-6772) |  |
| 485 | `dxOA` | uint32 | 0x80 h80 | indexed (-6772) |  |
| 486 | `dxIA` | uint32 | 0x80 h80 | indexed (-6772) |  |
| 487 | `dxC1` | byte | 0x80 h80 | indexed (-6772) |  |
| 488 | `dxP1` | string | 0x80 h80 | indexed (-6772) |  |
| 489 | `dxC2` | byte | 0x80 h80 | indexed (-6772) |  |
| 490 | `dxP2` | string | 0x80 h80 | indexed (-6772) |  |
| 491 | `bjFl` | uint32 | 0x00 | absent (-10) |  |
| 492 | `bjSd` | int | 0x00 | readable (dumped) |  |
| 493 | `bjSM` | int | 0x00 | absent (-10) |  |
| 494 | `wbEn` | bool | 0x00 | absent (-10) |  |
| 495 | `wbHN` | string | 0x00 | absent (-10) |  |
| 496 | `wbHU` | string | 0x00 | absent (-10) |  |
| 497 | `wbHP` | string | 0x00 | absent (-10) |  |
| 498 | `wbRD` | string | 0x00 | absent (-10) |  |
| 499 | `wbRU` | string | 0x00 | absent (-10) |  |
| 500 | `wbRP` | string | 0x00 | absent (-10) |  |
| 501 | `wbAC` | bool | 0x00 | absent (-10) |  |
| 502 | `dMac` | data | 0x00 | absent (-10) |  |
| 503 | `iCld` | data | 0x00 | absent (-10) |  |
| 504 | `iCLH` | data | 0x00 | absent (-10) |  |
| 505 | `iCLB` | int | 0x00 | absent (-10) |  |
| 506 | `SUEn` | bool | 0x00 | readable (dumped) |  |
| 507 | `SUAI` | bool | 0x00 | absent (-10) |  |
| 508 | `SUFq` | uint32 | 0x00 | readable (dumped) |  |
| 509 | `SUSv` | string | 0x00 | absent (-10) |  |
| 510 | `suPR` | data | 0x00 | absent (-10) |  |
| 511 | `msEn` | bool | 0x00 | absent (-10) |  |
| 512 | `trCo` | data | 0x00 | absent (-10) |  |
| 513 | `EZCF` | uint32 | 0x00 | absent (-10) |  |
| 514 | `ezcf` | data | 0x00 | absent (-10) |  |
| 515 | `gVID` | int16 | 0x00 | absent (-10) |  |
| 516 | `wcfg` | data | 0x00 | absent (-10) |  |
| 517 | `awce` | bool | 0x00 | absent (-10) |  |
| 518 | `wcgu` | byte | 0x04 priv | absent (-10) |  |
| 519 | `wcgs` | byte | 0x04 priv | absent (-10) |  |
| 520 | `awcc` | data | 0x04 priv | absent (-10) |  |
