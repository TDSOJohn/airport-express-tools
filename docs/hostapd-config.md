# ACPd — hostapd config generator (`FUN_00682190`)

Binary: `/sbin/ACPd` from firmware 7.8.1 (ELF32 BE MIPS-I, static, stripped), image base
`0x00400000`; not shipped here — see [extracting-acpd.md](extracting-acpd.md).
Function entry `0x00682190`, size 8932 bytes.

This is the function that writes the `hostapd_<iface>.conf` used to bring up the AP.
It fully determines whether the radio comes up as **Open / WEP / WPA / WPA2 / WPA-Enterprise**.

## Signature / arguments
```
int FUN_00682190(uint *param_1, int *param_2)
```
- `param_1` = global device config (radio, radius iface, IP, etc.)
- `param_2` = per-interface config. `param_2[3]` = interface role:
  `2` = main AP, `3` = WDS link, `4` = dwds STA uplink, `5` = ?, `6` = guest network.
- `local_4c = param_2 + 0x7e` (i.e. `param_2 + 0x1f8` bytes) = **the WiFi/SSID config struct**.

## The security mode switch — `raWM` (WiFi Mode)
`raWM` == `local_4c[0xb]` == **byte offset +0x2c** in the WiFi struct. It selects the cipher config:

| raWM | `wpa=` (local_40) | wpa_pairwise | rsn_pairwise | Meaning |
|-----:|:-----------------:|:-------------|:-------------|:--------|
| 1, 2 | — (WEP path)      | —            | —            | **WEP** (open/shared) → emits `wep_key0` |
| 3    | 1                 | TKIP         | —            | WPA (TKIP) |
| 4    | 3                 | TKIP         | CCMP TKIP    | WPA+WPA2 mixed |
| **5**| **2**             | —            | **CCMP**     | **WPA2 only (AES/CCMP)** |
| 6    | 3                 | TKIP         | CCMP         | WPA+WPA2 mixed |
| 7    | 3                 | CCMP TKIP    | CCMP TKIP    | WPA+WPA2 mixed (both ciphers) |
| 8    | 1                 | TKIP CCMP    | —            | WPA (TKIP+CCMP) |
| 9–12 | — (WEP path)      | —            | —            | WEP variants (also emit `wep_key0`) |
| else | 0                 | —            | —            | Open (no encryption) |

So **for pure WPA2 set `raWM = 5`**; 4/6/7 give WPA/WPA2 mixed. `wpa=%d` is emitted at
`FUN_00682190.c:562`; `wpa_pairwise`/`rsn_pairwise` at `:650`/`:653`; `wpa_key_mgmt` at `:648`.

## Key material layout (WiFi struct, relative to `local_4c`)
| Field | Offset | Type | Used as |
|:------|:------:|:-----|:--------|
| ssid | +0x00 | str | `ssid=` (`:239`) |
| EAP/802.1X flag | +0x28 (`*(char*)(local_4c+10)`) | u8 | 0 = PSK, !=0 = WPA-EAP (`:164,:166`) |
| **raWM (mode)** | **+0x2c** (`local_4c[0xb]`) | int | security mode switch above |
| **key material** | **+0x30** (`local_4c+0xc`) | 32 bytes | WEP key **or** 32-byte WPA PMK |
| **key length** | **+0x70** (`local_4c[0x1c]`) | int | length of the key at +0x30 (gate for PSK/WEP) |
| hide_ssid | +0xb8 (`*(char*)(local_4c+0x2e)`) | u8 | `hide_ssid=` (`:240`) |
| eapol_version sel | +0xc4 (`*(short*)(local_4c+0x31)`) | i16 | (`:449`) |
| WDS/rekey flag | +0xc6 | u8 | gates `wpa=` in WDS (`:162,:561,:656`) |
| wpa_group_rekey | +0xbc (`local_4c[0x2f]`) | int | (`:662,:664`) |

**Same buffer `+0x30` is reused**: as raw `wep_key0` hex when raWM∈{1,2,9–12}
(`:421-425`), or as the 64-hex WPA **PMK** when raWM∈{3–8} (`:166-175` → written to
`wpa_psk=` at `:645` / `wpa_psk_file` at `:566-573`). Length comes from **+0x70** and
must be non-zero for the PSK path to trigger.

## Why raw `setprop raWM=7` produced WEP (`wep_key0=aabbccddee`)
The generator has no separate "auth type" field — it derives everything from `raWM` +
the key buffer. So if the output was still `wep_key0=...`, then **at generation time
`raWM` was effectively 1/2 (WEP), not 7** — i.e. the value we wrote never reached the
struct the generator reads. That struct is not the flash blob directly; it is built by a
**property-table parser**.

Evidence: a packed 4-char property-key table lives at **`0x7efc98`**:
`raNm raCl raSk raWM raEA raWE raCr raKT raNN raGK raHW raRo raCA raCh raWC raDe raMu ra1C
raMd raPo raDt raSt raEV rTSN acEn dWDS dwFl wdFl raFl raI1 raTm raAu raAc raSe raRe raF2
raI2 raT2 raU2 raC2 raS2 raR2 raCi eaRA`. **SOLVED — see `ANALYSIS_wifi_blob.md`.** The flat `ra**` props are legacy. `FUN_0068c098`
migrates them into a structured **`WiFi`** blob **only when that blob is absent**, then
**deletes** the flat props. On any unit that already has a `WiFi` blob, `setprop raWM=7`
was ignored — the device kept the factory WEP key (`aabbccddee` = the 5-byte/40-bit factory
default). The real config to edit is the `WiFi` blob (array of per-radio dicts keyed by the
same fourccs; `raWM`=mode int, `raWE`=key data, `raCr`=passphrase, `raEA`=EAP flag).
Correction: `raSk` is a **1-byte boolean**, not the key buffer. See the other doc for the
key dictionary and the WPA2 recipe.

## Bonus: WPA-Enterprise cert autogen (`:81-124`)
If enterprise mode is active and `/mnt/Flash/server.p12` is missing, ACPd shells out to
`openssl` to self-generate a CA + server cert. Hardcoded: passphrase `appleinc`, subject
`Apple Inc.` / `Apple Wireless Devices` / `apple@mac.com`. Not needed for PSK WPA2.
