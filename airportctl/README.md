# airportctl

A small, safety-first CLI to configure a 2nd-gen **AirPort Express (A1392)** over Apple's
ACP admin protocol (TCP 5009) — built on the reverse-engineering in [`../docs/`](../docs/).
On other models it reads, and writes only with `--untested`; what works where:
[`../docs/models.md`](../docs/models.md#airportctl-on-each-model).

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
wifi join SSID --wifi-password PW|@FILE    become a client of an existing network (raSt=1).
                                           NOTE: the firmware's own supplicant crashes on 7.8.1,
                                           so this doesn't connect (../docs/join-mode.md)
            [--band 2.4|5] [--security wpa2|mixed|wpa|open] [--psta]
join install SSID --wifi-password PW|@FILE join a WPA2 network with our own supplicant over the
            [--ip dhcp|IP --gateway GW]    debug SSH login (2.4 GHz; 5 GHz stays up); no reboot.
            [--fallback-ip IP --gateway GW] Address from DHCP unless --ip is given.
            [--name NAME]                  --name renames the base station: its name on the
                                           network (NAME.local, the router's device list)
                                           from the next reboot
join start | status | remove               rejoin (after each reboot on stock firmware) / show
                                           the last run / delete it from /mnt/Flash
mode show                                  the join gate: ctim, waCV, sharing props, role
mode ctim [now|N]                          store the configuration timestamp (opens the gate)
mode sharing nat|dhcp|bridge               connection sharing (raNA/raDS/raWB)
mode wan wired|wireless|show               waCV WAN-uplink bit (only if role 6 shows up)
rpc --list                                 the 88 mapped ACP RPCs; unmarked = verified read-only
rpc NAME [--json '{..}'] [--force]         call one; read-only ones need no inputs, and no --force
                                           on a tested model/firmware
led  [show|auto|amber|green|N]             front status LED (LEDc): live, no reboot
name  BASE-STATION-NAME                    set base station name (syNm)
admin-password [PW|@FILE]                  change the admin password (syPW); prompts if omitted.
                                           ACP switches at once, the debug SSH login at next reboot
ui [--port N] [--no-browser]               local web page for the everyday commands; writes are
                                           previewed first (see "Web UI" in ../README.md)
info                                       model (syAP), firmware (syVs), uptime, Wi-Fi chip, CPU;
                                           tested or not; whether `join` can run on it
reboot                                     reboot (needed to apply Wi-Fi changes)

flags:  --radio N   only that radio (default: both)
        --dry-run   show the change, write nothing
        --reboot    reboot right after writing
        --no-backup skip the pre-write blob backup
        --untested  write to a model/firmware not verified yet (refused otherwise)
```

## Examples
```sh
python3 -m airportctl wifi show
python3 -m airportctl wifi ssid "Living Room" --reboot
printf %s 'my-wifi-pass' > ~/.wifipw && chmod 600 ~/.wifipw
python3 -m airportctl wifi secure wpa2 @~/.wifipw --reboot     # set password, apply
python3 -m airportctl wifi secure open --reboot                # back to open
airportctl wifi ssid "LivingRoom" --wifi-password @~/.wifipw --reboot   # rename + keep WPA2
airportctl led amber         # live, no reboot; led auto = back to status behaviour
```

| Behaviour | |
|---|---|
| Wi-Fi changes | apply at the next **reboot** (`/etc/hostap_wlanN.conf` is regenerated at boot) |
| Renaming a WPA network | the PMK depends on the SSID: pass `--wifi-password` to `wifi ssid`, or run `wifi secure …` after |
| WPS | turns on by itself with WPA2-PSK |
| `led` | sets `LEDc` live: `0` auto, `1` amber, `2` / `3` green; higher values ignored |
| `name` | `syNm` is stored at once; hostname and `.local` follow at the next reboot |
| `admin-password` | ACP uses the new password at once, the debug SSH login after a reboot |

## `WiFi` keys written

The live config is the `WiFi` property, `{'radios': [ {<fourcc>: value}, ... ]}`
([wifi-blob.md](../docs/wifi-blob.md)).

| Key | Meaning | Value written |
|---|---|---|
| `raNm` | SSID | 1–32 bytes |
| `raWM` | security mode | 0 open · 1 WEP · 3 WPA · **5 WPA2** · 7 WPA + WPA2 |
| `raWE` | key material | WPA: PMK = `PBKDF2-HMAC-SHA1(pw, ssid, 4096, 32)`; WEP: raw key bytes |
| `raEA` | 802.1X / EAP | `False` (PSK) |
| `raCl` | hidden network | bool |
| `raSt` | radio role (`wifi join`) | 1 = join |

## Client mode

| Command | Path | A1392 / 7.8.1 |
|---|---|---|
| `join install` / `start` / `status` / `remove` | our wpa_supplicant 0.7.3 on `/mnt/Flash`, over the debug SSH login | works (WPA2-PSK, 2.4 GHz, DHCP or fixed address); redo `join start` after each reboot on stock firmware |
| `wifi join` | the firmware's own client mode (`raSt = 1`) | gate opens with `mode ctim now`, then the firmware supplicant crashes; does not connect |
| `mode show` | reads `ctim`, `waCV`, `raNA` / `raDS` / `raWB` / `waUB`, per-radio `raSt`; prints the role and whether the gate is open | |
| `mode ctim [now\|N]` | stores the configuration timestamp (read back) | |
| `mode sharing nat\|dhcp\|bridge` | AirPort Utility's Connection Sharing: `nat` = factory NAT + DHCP at 10.0.1.1; `dhcp` = leases, no NAT; `bridge` = off. Without NAT the Express no longer serves DHCP on the cable: find it with `python3 ../tools/find_express.py` or over IPv6 link-local | |
| `mode wan wired\|wireless\|show` | `waCV` uplink bit; only needed if role 6 shows up | |

`wifi join` refuses to write while the gate is closed: that case produces an AP carrying the
target SSID and PMK (an evil twin). Details: [join-mode.md](../docs/join-mode.md).

## Safety

| | |
|---|---|
| Before each write | parse the live blob, refuse if it doesn't re-encode byte-identically; back it up to `WiFi-pre-write-<ts>.cfb` |
| After each write | read back and confirm |
| Backup directory | `../backups/` in a checkout (and an editable install), else a per-user state directory (`~/.local/state/airportctl/backups`); `wifi -h` prints it; `AIRPORTCTL_BACKUP_DIR` overrides |
| Backup contents | the real configuration including the PMK. `backups/` is git-ignored but inside the tree: don't archive the tree wholesale, or point `AIRPORTCTL_BACKUP_DIR` outside it |
| Restore | `python3 -m airportctl wifi restore ../backups/WiFi-pre-write-<ts>.cfb --reboot` (re-parses the file, backs up the config it replaces) |
| `setprop` | one property per request ([security.md](../docs/security.md#known-bugs)) |
