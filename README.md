# airport-express-tools

Configure a **2nd-generation AirPort Express (A1392)** from Linux — rename it, set WPA2, hide the
SSID, drive the front LED, and back up / restore its Wi-Fi config — plus a documented account of
which AirPort Utility features can and cannot be reproduced on this firmware: why the built-in
"join a wireless network" client mode cannot work, and a replacement supplicant that makes it work.

Apple discontinued the AirPort line in 2018. AirPort Utility still exists for macOS and iOS but no
longer gets updates (the iOS app's last release was in 2019), and there has never been a Linux
version. The protocol libraries that exist are listed under [Prior art](#prior-art-and-credits).

```sh
python3 -m airportctl wifi show                 # what the radios are doing
python3 -m airportctl wifi secure wpa2 @~/.pw   # set WPA2 properly (the blob, not the legacy props)
python3 -m airportctl mode show                 # why client mode is or isn't allowed
python3 -m airportctl led amber                 # the front LED, live
python3 -m airportctl info                      # model, firmware, and whether that combination is tested
```

## Compatibility

| Model | `syAP` | Firmware | Status |
|---|---|---|---|
| AirPort Express 2nd gen (A1392) | 115 | 7.8.1 | **Tested**: everything in this README |
| AirPort Express 802.11n (A1264), AirPort Extreme, Time Capsule | | | Untested. They speak the same ACP protocol, so reads will probably work; the `WiFi` blob layout and every firmware address in `docs/` may differ |

`airportctl info` prints your model and firmware. On an untested combination, airportctl prints a
warning before every write (it doesn't refuse). If you try it on anything else, please file a
[device report](https://github.com/TDSOJohn/airport-express-tools/issues/new?template=device-report.yml),
even when everything worked.

## If something goes wrong

Every Wi-Fi write first saves the current config to a backup file (`backups/` in a checkout; see
[Install](#install--run) for the other locations), so most mistakes are one command away from
undone.

| What happened | Fix |
|---|---|
| Clients can't connect after a Wi-Fi change | `python3 -m airportctl wifi restore backups/WiFi-pre-write-<timestamp>.cfb --reboot` |
| After `wifi join` it broadcasts the *target* network's name as an access point | The same restore. `wifi join` refuses this case unless forced with `--force`; see [below](#the-interesting-bit-join-a-wireless-network) |
| You ran `crossdev/wpa-build/join-test.sh` | `tools/essh.sh /sbin/reboot`, or unplug it. It changes nothing that is stored |
| It's unreachable at 10.0.1.1 after `mode sharing bridge` or `dhcp` | It no longer runs DHCP on the cable. Run `python3 tools/find_express.py`, or a DHCP server on that interface |
| You forgot the admin password | Soft reset (below) |
| Nothing above works | Hard reset, then factory reset |

Apple's [reset procedures](https://support.apple.com/102330), using the recessed button next to the
ports:

* **Soft reset:** with the Express powered on, hold the button for **1 second**; the light flashes
  amber. For 5 minutes it accepts configuration without the admin password (and with Access
  Control off); if nothing is changed in that time, it goes back to its old settings. This is
  AirPort Utility's recovery path; it hasn't been tried with airportctl.
* **Hard reset:** with the Express powered on, hold the button for **about 5 seconds**, until the
  light flashes amber rapidly. It restarts unconfigured but keeps the last saved configuration.
* **Factory reset:** unplug it, hold the button, plug it back in and keep holding for **about
  6 seconds**, until the light flashes amber rapidly. This erases every saved configuration. It
  comes back as an open `Apple Network xxxxxx` with the admin password `public`.

Wait about a minute after a hard or factory reset for it to finish restarting.

## The interesting bit: "join a wireless network"

AirPort Utility lists "join an existing wireless network" as a client mode for the A1392, but on
firmware 7.8.1 the built-in version cannot be made to work. Establishing that took getting through
two layers of the firmware, both confirmed on hardware — and getting past them took a third.

**1. A configuration gate hides `raSt`.** Writing `raSt=1` ("join a network") into the base
station's `WiFi` blob by itself does nothing — the unit comes back up as an access point
broadcasting the *target* network's name (an accidental evil twin). ACPd's VAP loader gates it:

```c
/* FUN_00689ab8 */
if (device_role == 6 || ctim == 0) { raSt = 0; radio->flags |= 1; /* forced AP */ }
else                               { raSt = blob["raSt"]; if (raSt == 1) flags |= 2; /* STA */ }
```

`ctim` is the stored **configuration timestamp**. Every real AirPort Utility "apply" writes it; a
unit configured only over ACP by hand never gets one, so it counts as never-configured and client
mode stays off. `mode ctim now` sets it and the gate opens — after a reboot the radio genuinely
comes up as a station targeting the SSID, with no evil-twin AP. **This part works.**

```sh
python3 -m airportctl mode show      # -> BLOCKED: ctim is unset/0 ...
python3 -m airportctl mode ctim now  # -> OK: raSt is now honoured
python3 -m airportctl wifi join YOUR-SSID --wifi-password @~/.wifipw --band 2.4 --reboot
```

**2. The bundled supplicant then crashes.** With the gate open, ACPd spawns `/sbin/wpa_supplicant`
(v0.6.5, static) — and it **segfaults at startup, every time**, before any scan or association.
Disassembly pins it to the `net80211` driver's "add interface" step *failing*, after which an
error-cleanup path dereferences a pointer it never initialised. Plain-STA and proxy-STA (`--psta`)
hit the identical crash. So the firmware's own Wi-Fi client stack cannot bring up a station
interface on this build, and no configuration gets past it.

**3. So bring your own supplicant.** The kernel and radio are fine, so stock **wpa_supplicant 0.7.3**,
cross-compiled for the Express, does the job on a station interface created by hand. It turned out
that Apple's NetBSD 4.0 kernel carries **FreeBSD 8's** 802.11 stack, so the build needs a handful of
header shims (ioctl numbers, struct layouts, a soft-float `setjmp`) but no source patches. The
Express then joins a normal WPA2 router on 2.4 GHz and plays **AirPlay on your home network**, with
its 5 GHz AP still up. It lasts until the next reboot:

```sh
cd crossdev && ./setup.sh && wpa-build/build-wpa.sh
wpa-build/join-test.sh HomeWiFi NM-PROFILE-UUID 192.168.1.250 192.168.1.1
```

The full derivation — the device-role formula, the `waCV` WAN-uplink bits, the supplicant config
generator, the exact crash chain and the replacement — is in [docs/join-mode.md](docs/join-mode.md);
the build and the kernel ABI table are in [crossdev/wpa-build/](crossdev/wpa-build/README.md).

> **Status (verified on an A1392, firmware 7.8.1):** WPA2, SSID, hidden, LED, name, mode
> inspection and backup/restore all work. The client-mode **gate** opens as described (the radio
> enters station mode), but the **built-in join is not fixable from configuration** — the
> firmware's `wpa_supplicant` crashes at launch. The **replacement supplicant works** (WPA2-PSK,
> AirPlay on the joined network), but it lives in RAM: every reboot needs `join-test.sh` again over
> SSH. For a set-and-forget setup, feed the Express's WAN/LAN port from a small Wi-Fi→Ethernet
> bridge instead.

## Contents

| path | what |
|---|---|
| `airportctl/` | the CLI: `wifi show/ssid/secure/hidden/join/backup/restore`, `mode`, `rpc`, `led`, `name`, `info`, `reboot`. Python 3 stdlib only. See its [README](airportctl/README.md). |
| `docs/` | what the firmware actually does: [join-mode](docs/join-mode.md), [rpc-surface](docs/rpc-surface.md) (all 56 RPCs), [wifi-blob](docs/wifi-blob.md), [hostapd-config](docs/hostapd-config.md), [extracting-acpd](docs/extracting-acpd.md) |
| `ghidra_scripts/` | headless Ghidra scripts that produced those docs, incl. `NameFuncs.java` which recovers ~2310 function names ([README](ghidra_scripts/README.md)) |
| `tools/` | `find_express.py`, `proptab.py` (dump the 520-entry ACP property table), `essh.sh` (debug shell), `mdns_probe.py`, `wait_for_reboot.py`, `pcap_summary.py` |
| `crossdev/` | cross-compile and run your own C on the device (NetBSD 4.0, mipseb) — see its [README](crossdev/README.md) |
| `crossdev/wpa-build/` | the replacement `wpa_supplicant`: build script, kernel-ABI shims, and `join-test.sh` — see its [README](crossdev/wpa-build/README.md) |

## Install / run

Python 3.8 or newer, no other dependencies; Linux, macOS or Windows. Install the `airportctl`
command with [pipx](https://pipx.pypa.io/):

```sh
pipx install git+https://github.com/TDSOJohn/airport-express-tools.git
airportctl --help
```

Or run it from a checkout without installing anything, which is what you want for `docs/`,
`tools/` and `crossdev/` anyway:

```sh
git clone https://github.com/TDSOJohn/airport-express-tools.git && cd airport-express-tools
python3 -m airportctl --help     # the examples in this README use this form
pipx install -e .                # optional: `airportctl` on PATH, running this checkout's code
```

Wi-Fi backups go to `backups/` in a checkout (including `pipx install -e`), and to
`~/.local/state/airportctl/backups` for an installed copy (`%LOCALAPPDATA%\airportctl\backups`
on Windows, `~/Library/Application Support/airportctl/backups` on macOS).
`airportctl wifi -h` prints the path, and `AIRPORTCTL_BACKUP_DIR` overrides it.

Connect your machine to the Express's **LAN** port (`‹•••›`), not the WAN port, with a profile
that never takes the default route — see [docs/extracting-acpd.md](docs/extracting-acpd.md) §1
for the `nmcli` recipe. Defaults are host `10.0.1.1`, admin password `public`.

## Safety

* **Use this over a direct cable.** ACP only lightly obfuscates the admin password on the wire.
* Every write backs the `WiFi` blob up first, refuses to proceed if the live blob
  does not re-encode byte-identically, and reads back to confirm. `wifi restore FILE` puts any
  backup back.
* `wifi join` refuses to write while the gate is closed, because that is exactly the case that
  produces an evil-twin AP carrying your real SSID and PMK.
* `crossdev/wpa-build/join-test.sh` changes only the running system: it briefly freezes ACPd and
  replaces the 2.4 GHz AP with a client interface. `tools/essh.sh /sbin/reboot` (or a power cycle)
  restores the stored setup. It copies only the derived PMK to the Express, never the passphrase.
* Wi-Fi changes only apply on **reboot** — the device regenerates `/etc/hostap_*.conf` at boot.
* If you enable the debug SSH shell (`dbug=0x3000`), remember that it is a root shell with the
  admin password, reachable from every network the Express is on (including one it joined with
  `join-test.sh`). Change the password from `public` first — `airportctl -p public admin-password`
  (ACP switches immediately, SSH after a reboot); `airportctl` and `tools/essh.sh` then read it from
  `~/.config/airport-express/admin-pw` (or `$AIRPORT_PW`). Turn the shell off when you are done.
* Recovery from a bad config is over the cable; the button resets are the backstop. See
  [If something goes wrong](#if-something-goes-wrong).

## Scope and provenance

Written for an A1392 on firmware **7.8.1** (see [Compatibility](#compatibility)). Firmware
addresses in `docs/` are specific to that build.

This is **interoperability research on hardware I own**: the ACP daemon was extracted from my own
base station and analysed statically to find out how to make the device do a thing its own
configuration app offers. In the EU that is the case Art. 6 of Directive 2009/24/EC (in Italy,
art. 64-*quater* L. 633/1941) explicitly permits; in the US, *Sega v. Accolade* and
*Sony v. Connectix* are the corresponding precedents, plus the DMCA §1201(f) interoperability
exemption. Nothing here circumvents a protection measure — the debug shell is enabled through a
documented property using the owner's own admin password.

Accordingly, **no Apple code is redistributed here**: no firmware image, no `ACPd` binary, no
strings dump, no decompiler output. The documents describe behaviour, addresses and data
layouts, and tell you how to regenerate all of it from your own device. `.gitignore` is set up to
keep it that way.

## Prior art and credits

Other ways to talk to an AirPort without AirPort Utility:

* [airpyrt-tools](https://github.com/x56/airpyrt-tools) (Python 2): the original ACP
  implementation. Its newer SRP login calls macOS's private `AppleSRP.framework`, so on Linux only
  the old login works.
* [node-acp](https://github.com/samuelthomas2774/node-acp) (Node.js): implements SRP login and
  session encryption, so the admin password never crosses the wire in the weak old format that
  airportctl uses. Prefer it if you can't use a direct cable.

What this repo adds: how the `WiFi` blob's security fields actually work (setting WPA2 correctly
means writing an SSID-salted PMK, not the legacy properties), the client-mode gate and the
firmware supplicant crash behind "join a wireless network", a working replacement supplicant, a
cross-compiling setup for the device's NetBSD 4.0/MIPS userland, the front LED, and a map of all
56 ACP RPCs.

Built on:

* [airpyrt-tools](https://github.com/x56/airpyrt-tools) (MIT) — the ACP protocol implementation
  `airportctl/acp.py` is a port of it.
* [node-acp](https://github.com/samuelthomas2774/node-acp) — ACP client/server, TypeScript types
  for the `WiFi` blob.
* [wpa_supplicant](https://w1.fi/wpa_supplicant/) 0.7.3 (BSD) — fetched and built unmodified by
  `crossdev/wpa-build/`; the shim headers carry definitions from FreeBSD's `net80211` (BSD), and
  NetBSD's `getifaddrs.c`/`setjmp.S` (BSD) are rebuilt for this kernel.
* [The AirPort wiki](https://github.com/samuelthomas2774/airport/wiki) — ACP properties, status
  codes, the `setDirtyPlist` apply flow, and the `dbug` SSH shell.

Everything about the `WiFi` blob's security fields, the hostapd/supplicant config generators and
the client-mode gate was worked out here; the rest builds on the projects above.

## Licence

MIT — see [LICENSE](LICENSE).
