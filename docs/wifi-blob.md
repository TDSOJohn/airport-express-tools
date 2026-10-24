# The `WiFi` property

The live Wi-Fi configuration is the `WiFi` property: a CFL blob
`{'radios': [ {<fourcc>: value, …}, … ]}`, one dict per radio. Radio order per model:
[models.md](models.md#platform) (A1392: 0 = 2.4 GHz, 1 = 5 GHz; A1301: 0 = 5 GHz, 1 = 2.4 GHz).
Written by `airportctl wifi …` ([airportctl](../airportctl/README.md)).

| | |
|---|---|
| Authoritative | the blob. The flat `ra**` properties are legacy: `FUN_0068c098` migrates them into a new `WiFi` blob only when none exists, then deletes them. With a blob present, flat `setprop raWM=…` is ignored; a flat get returns -6772 ([properties.md](properties.md#read-results-a1392)) |
| Applied | at boot only: `/etc/hostap_wlanN.conf` is regenerated from the blob, so Wi-Fi changes need a reboot |
| Readers | `FUN_00686384` (set VAP security, persists `WiFi`), `FUN_006896a0` (VAP bring-up), `FUN_00689ab8` (full loader); migrator called from `FUN_0068b0c8`, `FUN_00692a2c` |

## Per-radio keys

| Key | Type | Default | Meaning | Struct offset (`local_4c`) |
|---|---|---|---|---|
| `raNm` | string | | SSID, 1–32 bytes | `+0x00`, length `+0x24` |
| `raMd` | u16 | 5 / 6 | radio / PHY mode | |
| `raWM` | int | 0 | security mode ([below](#security-modes-rawm)) | `+0x2c` |
| `raWE` | data ≤ 0x3f | | key material, stored and used verbatim: WPA → the 32-byte PMK, WEP → raw key bytes | `+0x30`, length `+0x70` (must be non-zero for the PSK/WEP path) |
| `raCr` | data or utf8 ≤ 0x3f | | passphrase; not used for PSK (secondary WEP key in the hidden + WPA case) | `+0x74`, length `+0xb4` |
| `raEA` | bool | 0 | 802.1X / EAP (0 = PSK) | `+0x28` |
| `raSk` | bool | 0 | "secure key set" flag | |
| `raKT` | int | 3600 | key rotation time (s) | |
| `raCl` | bool | 0 | hidden network | `hide_ssid` `+0xb8` |
| `raCh` | int | 10 / 0x24 | channel | |
| `raCA` | bool | | (auto channel?) | |
| `raMu` | int | 2 / 6 | multicast rate | |
| `raWC` | bool | | (WMM?) | |
| `raSt` | int | 0 | 0 = create (AP), 1 = join (STA), 3 = off; honoured only behind the [client-mode gate](join-mode.md#the-gate) | |
| `dWDS`, `pSTA` | | | dynamic WDS / proxy STA (extend mode) | |
| `raGK raNN raHW raRo raDe ra1C raPo raDt raEV rTSN dwFl wdFl raCi acEn raFl raI1 raTm raAu raAc raSe raRe raF2 raI2 raT2 raU2 raC2 raS2 raR2` | | | `ra*2` = 5 GHz variants; WDS, timed access, … | |

Other generator fields: `eapol_version` selector `+0xc4` (i16), WDS/rekey flag `+0xc6`,
`wpa_group_rekey` `+0xbc`.

**WPA key:** `raWE = PBKDF2-HMAC-SHA1(passphrase, SSID, 4096, 32)`. No KDF runs on the device;
the bytes are written out as the PMK. Renaming a WPA network therefore needs a new `raWE`.

## Security modes (`raWM`)

From the hostapd config generator `FUN_00682190`:

| `raWM` | `wpa=` | `wpa_pairwise` | `rsn_pairwise` | Mode |
|---:|:---:|---|---|---|
| 0 / other | 0 | | | open |
| 1, 2 | | | | WEP (`wep_key0`) |
| 3 | 1 | TKIP | | WPA (TKIP) |
| 4 | 3 | TKIP | CCMP TKIP | WPA + WPA2 |
| **5** | **2** | | **CCMP** | **WPA2 (CCMP)** |
| 6 | 3 | TKIP | CCMP | WPA + WPA2 |
| 7 | 3 | CCMP TKIP | CCMP TKIP | WPA + WPA2, both ciphers |
| 8 | 1 | TKIP CCMP | | WPA (TKIP + CCMP) |
| 9–12 | | | | WEP variants (`wep_key0`) |

## Generated hostapd config

`raWM = 5`, `raWE` = PMK, `raEA = False` gives (L):

```
# /etc/hostap_wlan0.conf
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_psk_file=/etc/hostap_wlan0.wpa_psk
# /etc/hostap_wlan0.wpa_psk
00:00:00:00:00:00 <PMK, 64 hex>
```

WPS lines (`ieee8021x=1`, `eap_server=1`, `wps_*`) are added automatically for WPA2-PSK.

| Generator `FUN_00682190` | |
|---|---|
| Arguments | `param_1` global device config; `param_2` per-interface config, `local_4c = param_2 + 0x1f8` bytes = the Wi-Fi struct above |
| Interface role `param_2[3]` | 2 main AP, 3 WDS link, 4 dynamic-WDS STA uplink, 5 unknown, 6 guest network |
| Enterprise mode | if `/mnt/Flash/server.p12` is missing, generates a CA + server cert with `openssl`: passphrase `appleinc`, subject `Apple Inc.` / `Apple Wireless Devices` / `apple@mac.com` |
| Legacy key list | packed fourccs at `0x7efc98`: `raNm raCl raSk raWM raEA raWE raCr raKT raNN raGK raHW raRo raCA raCh raWC raDe raMu ra1C raMd raPo raDt raSt raEV rTSN acEn dWDS dwFl wdFl raFl raI1 raTm raAu raAc raSe raRe raF2 raI2 raT2 raU2 raC2 raS2 raR2 raCi eaRA` |
