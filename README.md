# airport-express-tools

Linux tools and reference data for Apple AirPort base stations and Time Capsules (NetBSD-based
7.x firmware): `airportctl`, a CLI and local web UI for configuring them over ACP; a
replacement Wi-Fi client for the A1392; a cross-compiler setup for the device; and data tables
on the hardware, firmware and admin protocol ([docs/](docs/README.md)).

AirPort Utility exists only for macOS and iOS and is no longer developed (iOS app last updated
in 2019); there is no Linux version. Other libraries: [Prior art](#prior-art-and-credits).

```sh
python3 -m airportctl info                      # model, firmware, whether the combination is tested
python3 -m airportctl wifi show                 # what the radios are doing
python3 -m airportctl wifi secure wpa2 @~/.pw   # WPA2 (writes the PMK into the WiFi blob)
python3 -m airportctl mode show                 # client-mode gate
python3 -m airportctl led amber                 # front LED, live
```

## Compatibility

<!-- models:begin (generated: python3 -m airportctl.models --update README.md) -->
| Model | A-number | `syAP` | Codename | CPU | Wi-Fi | Status |
|---|---|---|---|---|---|---|
| AirPort (Snow) |  | 1 | P19 |  |  | untested |
| AirPort Extreme (802.11g) | A1034 | 3 | P81 |  |  | untested |
| AirPort Express (802.11g) | A1084/A1088 | 102 | Q61 |  |  | untested |
| AirPort Extreme (802.11n) | A1143 | 104 | M28 |  |  | untested |
| AirPort Extreme (802.11n, Gigabit Ethernet) | A1143 | 105 | M91 |  |  | untested |
| Time Capsule | A1254 | 106 | M52 | armeb | Marvell | ACP reads and the debug SSH login seen live; writes untested |
| AirPort Express (802.11n) | A1264 | 107 | M48 |  |  | untested |
| AirPort Extreme (Simultaneous Dual-Band) | A1301 | 108 | K10 | armeb | Atheros | ACP reads seen live (7.6.9); writes untested |
| Time Capsule (Simultaneous Dual-Band) | A1302 | 109 | K30 |  |  | untested |
| Time Capsule (Simultaneous Dual-Band, Gen2) | A1355 | 113 | K30A |  |  | untested |
| AirPort Extreme (Simultaneous Dual-Band, Gen2) | A1354 | 114 | K10A |  |  | untested |
| AirPort Express (Simultaneous Dual-Band) | A1392 | 115 | K31 | mipseb | Atheros | **Tested** on 7.8.1: everything in this README |
| Time Capsule (Simultaneous Dual-Band, Gen3) | A1409 | 116 | K30B |  |  | untested |
| AirPort Extreme (Simultaneous Dual-Band, Gen3) | A1408 | 117 | K10B |  |  | untested |
| AirPort Time Capsule (802.11ac) | A1470 | 119 | J28 |  |  | untested |
| AirPort Extreme (802.11ac) | A1521 | 120 | J28E |  |  | untested |
<!-- models:end -->

Names, IDs and codenames come from the model table in ACPd; CPU and Wi-Fi are filled in once
checked. Measured data per model: [docs/models.md](docs/models.md). The 802.11n models share
the A1392's 7.8.1 firmware source, but the `WiFi` blob layout, RPC surface, radio order and
firmware addresses can differ.

| On an untested model / firmware | |
|---|---|
| Reads | work |
| Writes | refused unless `--untested` is added (e.g. `airportctl led amber --untested`); the web UI only reads |
| `airportctl rpc` | needs `--force` for every RPC |
| `join` | `airportctl info` says whether it can run |

Please file a [device report](https://github.com/TDSOJohn/airport-express-tools/issues/new?template=device-report.yml)
for any model you try, even when everything worked.

## Features (A1392, 7.8.1)

| Feature | Command | Status |
|---|---|---|
| SSID, WPA2 / WPA / mixed / WEP / open, hidden | `wifi ssid`, `wifi secure`, `wifi hidden` | works; applies at reboot |
| Wi-Fi backup / restore | `wifi backup`, `wifi restore` | works; automatic backup before every write |
| Base station name, admin password | `name`, `admin-password` | works |
| Front LED | `led` | works, live |
| Connection sharing (NAT / DHCP / bridge) | `mode sharing` | works |
| ACP RPCs | `rpc` | 88 mapped; read-only ones verified |
| Join a Wi-Fi network (our supplicant) | `join install` / `start` | works: WPA2-PSK on 2.4 GHz, DHCP or fixed address, AirPlay on the joined network; 5 GHz AP stays up. Redo `join start` after each reboot on stock firmware ([autorun](docs/autorun.md) image: built, not flashed) |
| Join a Wi-Fi network (firmware's own) | `mode ctim now` + `wifi join` | gate opens, then the firmware's wpa_supplicant 0.6.5 crashes at startup; does not connect ([join-mode](docs/join-mode.md)) |
| Web UI | `ui` | the everyday commands above |

`join` needs the debug SSH login, turned on by hand ([dbug](docs/dbug.md)). Building the
supplicant yourself: `cd crossdev && ./setup.sh && wpa-build/build-wpa.sh`
([wpa-build](crossdev/wpa-build/README.md)).

## If something goes wrong

Every Wi-Fi write first saves the current config to a backup file ([Install](#install--run)
lists the locations).

| What happened | Fix |
|---|---|
| Clients can't connect after a Wi-Fi change | `python3 -m airportctl wifi restore backups/WiFi-pre-write-<timestamp>.cfb --reboot` |
| After `wifi join` it broadcasts the *target* network's name as an AP | the same restore (`wifi join` refuses this case unless `--force`) |
| You ran `crossdev/wpa-build/join-test.sh` | `tools/essh.sh /sbin/reboot`, or unplug it; nothing stored was changed |
| You want `airportctl join` gone | `airportctl join remove`, then reboot; it changes only files on `/mnt/Flash` |
| Unreachable at 10.0.1.1 after `mode sharing bridge` or `dhcp` | it takes its address from the WAN side and no longer serves DHCP on the cable. Leave out `--host`: airportctl finds it over IPv6 link-local (UI: **Find it**). `mode show` warns if the WAN port has no link; plug it in, or `mode sharing nat` and reboot. After `join`, on your Wi-Fi: `python3 tools/find_express.py` |
| Forgot the admin password | soft reset |
| Nothing above works | hard reset, then factory reset |

Resets ([Apple](https://support.apple.com/102330)), recessed button next to the ports:

| Reset | How | Effect |
|---|---|---|
| Soft | powered on, hold **1 s** (light flashes amber) | for 5 minutes, configuration without the admin password: the literal `public` is accepted in place of `syPW` (`python3 -m airportctl -p public admin-password …`); reverts if nothing is changed. Only on a network you control |
| Hard | powered on, hold **~5 s** until the light flashes amber rapidly | restarts unconfigured, keeps the last saved configuration |
| Factory | unplug, hold, plug in, keep holding **~6 s** until it flashes amber rapidly | erases all configuration: open `Apple Network xxxxxx`, admin password `public` |

Allow about a minute after a hard or factory reset.

## Contents

| Path | What |
|---|---|
| `airportctl/` | the CLI and web UI, Python 3 stdlib only; prebuilt device payload in `payload/` ([README](airportctl/README.md)) |
| `docs/` | data tables: models, hardware, boot, firmware, ACP properties and RPCs, `WiFi` blob, client mode, `dbug`, autorun, security ([index](docs/README.md)) |
| `tools/` | `find_express.py`, `proptab.py` (dump the ACP property table), `essh.sh` (debug shell), `mdns_probe.py`, `wait_for_reboot.py`, `pcap_summary.py`, `decrypt_basebinary.py` + `ufs1.py` (unpack a `.basebinary`), `repack_basebinary.py` (rebuild one with a replaced ramdisk file) |
| `crossdev/` | cross-compile and run C on the A1392 (NetBSD 4.0, mipseb) ([README](crossdev/README.md)) |
| `crossdev/wpa-build/` | the replacement `wpa_supplicant` ([README](crossdev/wpa-build/README.md)) |
| `autorun/` | the `/etc/rc` with the autorun hook ([autorun](docs/autorun.md)) |
| `ghidra_scripts/` | headless Ghidra scripts behind the docs ([README](ghidra_scripts/README.md)) |

## Install / run

Python 3.8 or newer, no other dependencies; Linux, macOS or Windows.

```sh
pipx install git+https://github.com/TDSOJohn/airport-express-tools.git
airportctl --help
```

From a checkout (needed for `docs/`, `tools/`, `crossdev/`):

```sh
git clone https://github.com/TDSOJohn/airport-express-tools.git && cd airport-express-tools
python3 -m airportctl --help
pipx install -e .                # optional: `airportctl` on PATH, running this checkout
```

| Wi-Fi backups | |
|---|---|
| Checkout (incl. `pipx install -e`) | `backups/` |
| Installed, Linux | `~/.local/state/airportctl/backups` |
| Installed, macOS | `~/Library/Application Support/airportctl/backups` |
| Installed, Windows | `%LOCALAPPDATA%\airportctl\backups` |
| Override | `AIRPORTCTL_BACKUP_DIR`; `airportctl wifi -h` prints the path |

Connect to the base station's **LAN** port (`‹•••›`) with a profile that never takes the
default route:

```sh
nmcli connection add type ethernet con-name airport-probe ifname <your-iface> \
  connection.autoconnect no \
  ipv4.method auto ipv4.never-default yes ipv4.ignore-auto-dns yes \
  ipv4.ignore-auto-routes yes ipv4.route-metric 2000 ipv6.method ignore
nmcli connection up airport-probe
```

Defaults: host `10.0.1.1`, admin password `public`. Without `--host`, if 10.0.1.1 doesn't
answer, airportctl looks for `_airport._tcp` over IPv6 link-local mDNS on each interface (no
root needed) and prints the address it used; this works even when the unit has no IPv4
address.

## Web UI

```sh
airportctl ui                    # or: python3 -m airportctl ui
airportctl ui --no-browser       # print the link instead of opening it
airportctl ui --port 8765
```

A local bridge (a browser can't speak ACP) for network name, security, visibility,
base-station name, LED, joining a Wi-Fi network, backups and reboot. Each change runs as the
equivalent `airportctl` command, with the same checks and backups; writes show a review step,
and the log shows each command.

| | |
|---|---|
| Access | listens on `127.0.0.1`, accepts only that host name, needs the one-time token in the link it opens; the admin password stays in the bridge process |
| Can't reach it | **Find it** searches over IPv6 link-local. A **No uplink** banner appears when sharing isn't NAT and the WAN port has no link, with a button back to NAT |
| Wi-Fi changes | apply after a reboot (Reboot button); the LED changes at once |
| Join a Wi-Fi network | runs `airportctl join`; needs the debug SSH login (the card says so) |
| Built-in client mode | under "Experimental"; doesn't connect on 7.8.1 and switches the other radio off, so the page offers **Undo** (restores the backup taken just before) |

## Safety

* **Use a direct cable.** The legacy ACP login only obfuscates the admin password on the wire.
* Every write backs up the `WiFi` blob, refuses if the live blob doesn't re-encode
  byte-identically, and reads back. `wifi restore FILE` puts any backup back.
* `wifi join` refuses to write while the gate is closed (that case gives an evil-twin AP with
  your SSID and PMK).
* `join-test.sh` changes only the running system and copies only the PMK, never the passphrase.
* The debug SSH login (`dbug=0x3000`) is a root shell with the admin password, reachable from
  every network the unit is on. Change the password from `public` first
  (`airportctl -p public admin-password`; airportctl and `tools/essh.sh` then read it from
  `~/.config/airport-express/admin-pw` or `$AIRPORT_PW`), and turn the shell off when done.

## Scope and provenance

Firmware addresses in `docs/` are for the A1392 on 7.8.1 ([conventions](docs/README.md#conventions)).

This is interoperability research on hardware I own: ACPd was extracted from my own base
station and analysed statically to make the device do what its own configuration app offers.
In the EU that is the case Art. 6 of Directive 2009/24/EC (in Italy, art. 64-*quater*
L. 633/1941) permits; in the US, *Sega v. Accolade* and *Sony v. Connectix* are the
corresponding precedents, plus the DMCA §1201(f) interoperability exemption. Nothing here
circumvents a protection measure: the debug shell is enabled through a documented property with
the owner's admin password.

**No Apple code is redistributed:** no firmware image, no `ACPd` binary, no strings dump, no
decompiler output. The docs describe behaviour, addresses and data layouts, and how to
regenerate everything from your own device or Apple's public downloads. `.gitignore` keeps it
that way.

## Prior art and credits

| Project | Notes |
|---|---|
| [airpyrt-tools](https://github.com/x56/airpyrt-tools) (Python 2, MIT), by x56 of Embedded Ideation | the original ACP implementation. `airportctl/acp.py` is a port of it, including the `cflbinary` codec (`airportctl/cfl.py`) and the `.basebinary` key scheme. Its SRP login needs macOS's private `AppleSRP.framework` |
| Embedded Ideation: [*Dissecting the AirPort Express*](https://www.embeddedideation.com/2014/03/dissecting-the-airport-express/) (2014), [*AirPort Hacking Update*](https://www.embeddedideation.com/2016/04/24/airport-hacking-update/) (2016) | serial/JTAG header, SPI flash and partitions; `cflbinary`, `.basebinary` decryption, SRP and session encryption, NetBSD toolchain recipe |
| [node-acp](https://github.com/samuelthomas2774/node-acp) (Node.js) | SRP login and session encryption (the password never crosses the wire); TypeScript types for the `WiFi` blob. Prefer it when a direct cable isn't possible |
| [The AirPort wiki](https://github.com/samuelthomas2774/airport/wiki) | ACP properties, status codes, the `setDirtyPlist` apply flow, the `dbug` SSH shell |
| [wpa_supplicant](https://w1.fi/wpa_supplicant/) 0.7.3 (BSD) | fetched and built unmodified by `crossdev/wpa-build/`; shims carry FreeBSD `net80211` definitions (BSD); NetBSD's `getifaddrs.c` / `setjmp.S` (BSD) rebuilt for this kernel |

New here: the `WiFi` blob's security fields (WPA2 = an SSID-salted PMK, not the legacy
properties), the hostapd/supplicant config generators, the client-mode gate and the firmware
supplicant crash, a working replacement supplicant, the cross-compiling setup, the front LED,
and the classified map of all 88 ACP RPCs.

## Licence

MIT — see [LICENSE](LICENSE).
