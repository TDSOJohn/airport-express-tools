# airportctl

A small, safety-first CLI to configure a 2nd-gen **AirPort Express (A1392)** over Apple's
ACP admin protocol (TCP 5009) — built on the reverse-engineering in [`../docs/`](../docs/).

> Use over a **trusted direct cable** only. The admin password is only lightly obfuscated on
> the wire. Default host `10.0.1.1`, default admin password `public`.

## Run
```sh
airportctl [--host H] [-p ADMINPW|@FILE] <command>     # installed with pipx (see ../README.md)
python3 -m airportctl <command>                        # from the repo root, nothing installed
../airportctl-run <command>                            # launcher for a checkout, from any dir
```

## Commands
```
wifi show                                  decode the WiFi blob per radio
wifi ssid   NAME [--wifi-password PW|@FILE] set network name (raNm); pass the Wi-Fi
                                           password too when WPA is set, so the PMK is
                                           re-derived for the new SSID (else clients fail)
wifi secure open                [flags]    no encryption
wifi secure wpa2 PW|@FILE       [flags]    WPA2/CCMP  (recommended)   raWM=5
wifi secure wpa  PW|@FILE       [flags]    WPA/TKIP (legacy)          raWM=3
wifi secure mixed PW|@FILE      [flags]    WPA+WPA2 mixed             raWM=7
wifi secure wep  HEXKEY         [flags]    WEP (insecure)  10/26 hex  raWM=1
wifi hidden on|off              [flags]    hide/show SSID (raCl)
wifi backup [--note LABEL]                 save the live WiFi blob (path: `wifi -h`)
wifi restore FILE [--reboot]               write a saved blob back (recovery path)
wifi join SSID --wifi-password PW|@FILE    become a client of an existing network (raSt=1)
            [--band 2.4|5] [--security wpa2|mixed|wpa|open] [--psta]
mode show                                  the join gate: ctim, waCV, sharing props, role
mode ctim [now|N]                          store the configuration timestamp (opens the gate)
mode sharing nat|dhcp|bridge               connection sharing (raNA/raDS/raWB)
mode wan wired|wireless|show               waCV WAN-uplink bit (only if role 6 shows up)
rpc --list                                 the 56 mapped ACP RPCs and their signatures
rpc NAME [--json '{..}'] [--force]         call one (see ../docs/rpc-surface.md)
led  [show|auto|amber|green|N]             front status LED (LEDc): live, no reboot
name  BASE-STATION-NAME                    set base station name (syNm)
admin-password [PW|@FILE]                  change the admin password (syPW); prompts if omitted.
                                           ACP switches at once, the debug SSH login at next reboot
info                                       model (syAP), firmware (syVs), uptime; tested or not
reboot                                     reboot (needed to apply Wi-Fi changes)

flags:  --radio N   only that radio (default: both)
        --dry-run   show the change, write nothing
        --reboot    reboot right after writing
        --no-backup skip the pre-write blob backup
```

## Examples
```sh
python3 -m airportctl wifi show
python3 -m airportctl wifi ssid "Living Room" --reboot
printf %s 'my-wifi-pass' > ~/.wifipw && chmod 600 ~/.wifipw
python3 -m airportctl wifi secure wpa2 @~/.wifipw --reboot     # set password, apply
python3 -m airportctl wifi secure open --reboot                # back to open
airportctl wifi ssid "LivingRoom" --wifi-password @~/.wifipw --reboot   # rename + keep WPA2
```
The WPA PMK is derived from the SSID, so renaming an encrypted network needs the PMK
re-derived — pass `--wifi-password` to `wifi ssid`, or run `wifi secure ...` afterwards.

```sh
airportctl led               # show current LED state
airportctl led amber         # force solid amber (live, no reboot)
airportctl led green         # force solid green
airportctl led auto          # back to the default status behaviour
```
The `led` command sets the `LEDc` property. It takes effect immediately (unlike Wi-Fi
changes), and only values `0`–`3` are honoured: `0` auto, `1` amber, `2`/`3` green — the
device silently ignores anything higher. Verified on-device 2026-09-15. Because it is
scriptable and instant, the LED can double as a status indicator (see the note below).

## Client / "join a wireless network" mode

**This mode cannot be made to work on firmware 7.8.1.** `wifi join` and `mode` are provided for
inspection and for the research write-up, not because a join succeeds. Two firmware layers block
it (full detail in [`../docs/join-mode.md`](../docs/join-mode.md)):

1. **A gate** in `FUN_00689ab8` ignores `raSt` unless the stored configuration timestamp `ctim`
   is set (and the device role isn't 6):

   ```c
   if (device_role == 6 || ctim == 0) { raSt = 0; /* forced create/AP */ }
   ```

   A base station only ever written by hand over ACP has no `ctim`, so it silently stays an AP —
   and, with a join blob applied, an evil-twin AP carrying the target SSID. `mode show` reports
   this; `mode ctim now` opens the gate, and the radio then genuinely enters station mode.

2. **The supplicant crash.** Once the gate is open, the firmware's `wpa_supplicant` (v0.6.5)
   segfaults at startup — its `net80211` driver fails to add the station interface, before any
   scan or association. `--psta` (proxy-STA) crashes identically. This is a firmware bug with no
   configuration workaround.

```sh
airportctl mode show            # gate state: ctim, role, per-radio raSt
airportctl mode ctim now        # opens the gate (persists; read-back verified)
airportctl wifi join YOUR-SSID --wifi-password @~/.wifipw --band 2.4 --reboot
```

`mode sharing` is AirPort Utility's "Connection Sharing": `nat` (factory: NAT + DHCP at
10.0.1.1), `dhcp` (hand out leases, no NAT) or `bridge` (off — what you want for AirPlay on the
house LAN). In bridge mode the Express stops serving DHCP on the cable, so find it again with
`python3 ../tools/find_express.py`.

## How it works (verified on-device 2026-09-14)
The live config is the `WiFi` property — a CFL blob `{'radios': [ {<fourcc>: value}, ... ]}`.
Per-radio keys this tool sets:

| key  | meaning | notes |
|------|---------|-------|
| `raNm` | SSID | 1–32 bytes |
| `raWM` | security mode | 0 open · 1/2 WEP · 3 WPA · 5 **WPA2** · 4/6/7 WPA+WPA2 mixed |
| `raWE` | key material | WPA: the 32-byte PMK `PBKDF2-HMAC-SHA1(pw, ssid, 4096, 32)`; WEP: raw key bytes |
| `raEA` | 802.1X/EAP | forced `False` (PSK) |
| `raCl` | hidden network | bool |

Wi-Fi changes only take effect after a **reboot** (the device regenerates
`/etc/hostap_wlanN.conf` at boot, not on write). WPS auto-enables for WPA2-PSK — normal.

## Safety
Every write: parses the live blob and refuses if it doesn't re-encode byte-identically,
auto-backs-up to `WiFi-pre-write-<ts>.cfb` in the backup directory, writes, then reads back and
confirms. That directory is `../backups/` in a checkout (and an editable install), otherwise a
per-user state directory such as `~/.local/state/airportctl/backups`; `wifi -h` prints it.

The backups hold **your base station's real configuration**, including the 32-byte WPA PMK
derived from your Wi-Fi passphrase. In a checkout, `backups/` is in `.gitignore` but still inside
the working tree, so don't copy or archive the tree wholesale, or set `AIRPORTCTL_BACKUP_DIR` to
somewhere outside it, e.g. `export AIRPORTCTL_BACKUP_DIR=~/.local/state/airportctl/backups`.
Recover from any of those backups:
```sh
python3 -m airportctl wifi restore ../backups/WiFi-pre-write-<ts>.cfb --reboot
```
`wifi restore` re-parses the file before sending it, and backs up the config it is about to
replace.
