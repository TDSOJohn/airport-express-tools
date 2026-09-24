# ACPd — WiFi config model & the `WiFi` blob (the real config)

This corrects/extends `ANALYSIS_hostapd_configgen.md`. Key discovery: the flat `ra**`
properties are **legacy**; the authoritative config is the structured **`WiFi`** blob.

## The migration/writer: `FUN_0068c098`
Runs at config load. Pseudocode:
```
if getprop('WiFi') == NOT_FOUND (-10):          # only when blob is absent
    for each radio index:
        build dict d:
            d['raMd'] = getprop('raMd')  (radio/PHY mode, default 5/6)
            d['raWM'] = getprop('raWM' 0x7261574d, int, default 0)   # SECURITY MODE
            d['raSk'] = getprop('raSk', 1 byte bool)
            d['raWE'] = getprop('raWE' 0x72615745, up to 0x7f bytes, %D)  # KEY DATA
            d['raCr'] = getprop('raCr' 0x72614372, up to 0x7f bytes, %s)  # credential str
            ... ~45 keys total ...
        append d to array
    setprop('WiFi', 0x8000, array)              # write the structured blob
    for fc in [raNm,raCl,raSk,raWM,raEA,raWE,...]: delprop(fc)   # DELETE flat props
```
So flat `setprop raWM=7` only ever matters **once**, during first-boot migration, and is
then deleted. If a `WiFi` blob already exists, flat writes are **ignored entirely** — this
is why our raw `setprop raWM=7` had no effect and the device stayed on the factory WEP key.

Callers of the migrator: `FUN_0068b0c8`, `FUN_00692a2c`.

## WiFi-dict key dictionary (fourcc → meaning, from `FUN_0068c098` defaults/types)
| key  | type (read)      | default | meaning (inferred) |
|:-----|:-----------------|:--------|:-------------------|
| raNm | string           | —       | SSID / network name |
| raMd | u16              | 5/6     | radio / PHY mode |
| **raWM** | **int (4B)** | **0**   | **security mode** (see map below) |
| raSk | bool (1B)        | 0       | "secure key set" flag |
| **raWE** | **data ≤0x7f (%D)** | — | **key material** (WEP key / WPA PMK bytes) |
| raCr | string ≤0x7f     | —       | credential / passphrase string |
| raEA | bool (1B)        | 0       | 802.1X / EAP enable |
| raKT | int              | 0xe10   | key rotation time (s) = 3600 |
| raCl | bool             | 0       | closed/hidden network |
| raCA | bool             | —       | (auto channel?) |
| raCh | int              | 10/0x24 | channel |
| raMu | int              | 2/6     | multicast rate |
| raWC | bool             | —       | WMM? |
| raGK,raNN,raHW,raRo,raDe,ra1C,raPo,raDt,raSt,raEV,rTSN,dWDS,dwFl,wdFl,raCi,acEn,raFl,raI1,raTm,raAu,raAc,raSe,raRe,raF2,raI2,raT2,raU2,raC2,raS2,raR2,raNm | various | 5 GHz variants (`ra*2`), WDS, timed-access, etc. |

## `raWM` security-mode map (from the hostapd generator `FUN_00682190`)
`1,2,9–12` = WEP · `3` = WPA/TKIP · `4,6,7` = WPA+WPA2 mixed · **`5` = WPA2-only (CCMP)** ·
else = Open. The generator reads `raWM` from struct **+0x2c** and the key bytes from
struct **+0x30** (32-byte PMK for WPA), length **+0x70**. Those struct offsets are filled
from the `WiFi` dict's `raWM` / `raWE` by the blob→struct consumer (not yet decompiled).

## The consumers — DEFINITIVE dict-key → struct-offset mapping
Three functions load a WiFi dict into the runtime VAP struct (`vap+0x1f8` = the generator's
`local_4c`). All read keys via `FUN_008265d4(dict, out, fmt, &keydesc)` (a plist extractor;
`%kO`/`%ks` + `:int`/`:bool`/`:CFString`/`:utf8`/data). Confirmed on 2 of them independently:

- `FUN_00686384` — "set VAP security" handler: dict → struct, then persists `WiFi` + notifies.
- `FUN_006896a0` — VAP bring-up from dict.
- `FUN_00689ab8` — full config loader (whole VAP, ~all keys).

| dict key | extractor type | → struct off (rel local_4c) | generator use |
|:---------|:---------------|:----------------------------|:--------------|
| raNm | `%kO:CFString`/`utf8` | +0x00 (SSID), len→+0x24 | `ssid=` |
| **raWM** | `%kO:int` | **+0x2c** | security-mode switch |
| **raWE** | data (≤0x3f) | **+0x30**, len→**+0x70** | `wpa_psk=`(hex of bytes) / `wep_key0=` |
| raCr | data or `%kO:utf8` (≤0x3f) | +0x74, len→+0xb4 | secondary WEP key (hidden+WPA case) |
| raEA/raSk-adj | bool/int | +0x28 | EAP/802.1X flag |

**`raWE` is stored VERBATIM — no PBKDF2/SHA anywhere in these paths.** The generator emits
the +0x30 bytes as `wpa_psk=<64-hex>`, which hostapd requires to be the raw 256-bit PMK.
⇒ **For WPA the client must supply `raWE` = the finished 32-byte PMK**, not a passphrase.
`raCr` (passphrase) is stored for display/secondary use only.

## Actionable path to WPA2  (VERIFIED against the code)
Edit the `WiFi` blob (array of per-radio dicts), not flat props. In the target dict set:
- `raNm` = SSID
- `raWM` = **5**  (WPA2-only / CCMP; use 4/6/7 for WPA+WPA2 mixed)
- `raWE` = **PBKDF2-HMAC-SHA1(passphrase, SSID, 4096, 32 bytes)** — the 32-byte PMK, as a
  data/blob value (Python: `hashlib.pbkdf2_hmac('sha1', pw.encode(), ssid.encode(), 4096, 32)`)
- EAP flag = 0
Then `setprop WiFi <blob>`, reboot, and confirm `/tmp/hostapd_<iface>.conf` (or `.dump`)
shows `wpa=2`, `rsn_pairwise=CCMP`, `wpa_key_mgmt=WPA-PSK`, `wpa_psk=<64 hex>`.
Tooling already present: `airport_express_debug/cfl_plist.py`, scratchpad `node-acp`,
factory sample `backup-WiFi-factory.cfb`.

## Verified on-device (A1392, firmware 7.8.1)
AirPort Utility never discovers this unit (Bonjour discovery is the broken piece), so we
verified directly over ACP/SSH instead:
1. Laptop `enp5s0` → Express **LAN** port; `nmcli c up airport-probe` (never-default DHCP,
   got 10.0.1.2, the laptop's own default route untouched). Reading the `WiFi` property
   showed both radios `raWM=0` (open); every flat `ra**` prop returned error `0xffffe58c`
   (deleted) — proving the blob is authoritative.
2. Applied the recipe (`raWM=5`, `raWE`=PMK for a test passphrase, `raEA=False`),
   **rebooted** (the conf regenerates on reboot, not on `setprop`), then `cat
   /etc/hostap_wlan0.conf` over SSH:
   ```
   wpa=2
   wpa_key_mgmt=WPA-PSK
   rsn_pairwise=CCMP
   wpa_psk_file=/etc/hostap_wlan0.wpa_psk
   ```
   and `/etc/hostap_wlan0.wpa_psk` = `00:00:00:00:00:00 <our exact PMK>`.
So: **`raWM=5` + `raWE`=`PBKDF2-HMAC-SHA1(pw, ssid, 4096, 32)` ⇒ WPA2-Personal/CCMP**, PMK
copied verbatim. `raCr` is not needed. WPS lines (`ieee8021x=1`/`eap_server=1`/`wps_*`) turn
on automatically — normal consumer WPA2-PSK, not enterprise. `airportctl wifi secure wpa2` implements
exactly this (was previously `raWM=2`+`raCr`, which is why WPA2 failed before).
