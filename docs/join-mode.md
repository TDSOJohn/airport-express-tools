# AirPort Express A1392 — "airport mode" (create / join / extend): the gate, and how to open it

**Status:** the gate is identified, implemented in `airportctl`, and **confirmed on hardware
(2026-09-23)** — setting `ctim` does open it and the device comes up as an STA (`raSt=1`). **But the
firmware's own join fails one layer lower:** its bundled `wpa_supplicant` **segfaults at startup**
(its net80211 driver "add interface" step fails and the failure-cleanup path NULL-derefs), so native
client join is **non-viable on 7.8.1** from configuration alone. **A replacement supplicant built from
stock sources does work** (verified 2026-09-23): the Express joins a third-party WPA2 router as a
client on 2.4 GHz and serves AirPlay there, until the next reboot. See
["A replacement supplicant: works"](#a-replacement-supplicant-works) and
[`crossdev/wpa-build/`](../crossdev/wpa-build/README.md). Everything described about the firmware was
read out of the binary; everything described as observed was seen on an A1392 running 7.8.1.

## TL;DR

The per-radio `raSt` value in the `WiFi` blob (0 = create/AP, 1 = join/STA, 3 = off) is only read
by the VAP loader when **both** of these hold:

```c
/* ACPd FUN_00689ab8, ~0x689d18 */
if (ctx->role /* ctx+0x24 */ == 6 || ctim == 0) { raSt = 0; radio->flags |= 1 /* AP */; }
else                                            { raSt = blob["raSt"]; if (raSt == 1) radio->flags |= 2 /* STA */; }
```

* `ctim` is the ACP property **`ctim` = configuration timestamp**. On a unit that has only ever
  been written over ACP by hand it has *no stored value* (`getprop ctim` → `0xfffffff6`), so it
  reads back as 0. **This is why a `raSt=1` join attempt silently comes up as an AP instead.**
* `role` is computed at daemon init from five stored properties; with the factory values it is
  **1**, not 6, so it is *not* a blocker for us — but it becomes one if `waCV` bit `0x10000` is
  ever stored.

So the recipe is: **`airportctl mode ctim now`**, then the existing `airportctl wifi join …`,
then reboot.

## The gate, in detail

### `ctim` — configuration timestamp (the live blocker)

`ctim` (`0x6374696d`) is an ordinary stored ACP property: property-table entry at VMA `0xc5bdc0`,
type 5 (uint32), flags word 0 → freely readable *and settable* over ACP (`ACPSetPropertyDirectEx`
rejects only entries with flag bits 0x04/0x08/0x20/0x40/0x80). It has no handler, so
`ACPGetPropertyDirect` falls through to the generic config store and returns `-10` when the key
is absent — which is what a hand-configured unit returns.

What sets it in Apple's world:

* `FUN_00659910` (called from the init path) does `if (ctim == 0) ACPPostProblemDirect('ctim')` —
  i.e. an unset `ctim` is one of the device's *problems*, right next to `'pubP'` which is posted
  when the admin password is still `public`. So `ctim` is a user-visible "this base station has
  never been configured / its clock is not set" condition.
* `FUN_00686384` (the `wifi.wps.credentials` handler) builds a config dict
  `{ ctim: <now, %kC=%i>, WiFi: <blob, %kC=%O> }` and applies it — i.e. **every real
  configuration apply carries `ctim`**. AirPort Utility does the same; a plain `setprop` of the
  Wi-Fi settings does not, which is why a factory-reset unit configured by hand stays
  "unconfigured" as far as the loader is concerned.
* Nothing in ACPd ever writes or clears `ctim` on its own, so once stored it persists in the
  config store across reboots.

Other consumers confirm the meaning: `FUN_0067f010` ("is `ctim` invalid?") gates the
`ACPCloud_*` / certificate paths, and `FUN_00686698` (`wifi.scan.request`) refuses to scan while
`ctim == 0`.

### `role` = ctx+0x24 — the device role (not a blocker at factory values)

`ctx` is the daemon-global `DAT_00e46ec0` (0x230 bytes, zeroed and filled by `FUN_0065746c`).
`ctx+0x24` is set once at init from five stored properties:

| prop | type | meaning (from the factory-default writer `FUN_0066dd88` + the sanitiser `FUN_00672c30`) |
|---|---|---|
| `raNA` | bool | connection sharing: **NAT** ("share a public IP address") |
| `raDS` | bool | connection sharing: **hand out DHCP leases** |
| `raWB` | bool | connection sharing: **off / bridge mode** |
| `waUB` | bool | WAN-port-used-as-bridge |
| `waCV` | int  | WAN config bitfield; `0x8000` = wired WAN uplink, `0x10000` = **wireless** WAN uplink, `0x800` = a third uplink flavour |

```c
/* FUN_0065746c, role = ctx+0x24 */
if (raNA && !raWB) {                 /* FUN_00653070 */
    role = (waCV & 0x800) ? 2 : ((waCV & 0x10000) ? 6 : 1);
} else if (!waUB) {
    role = (!raNA && !raDS && raWB) ? 4 : ((raNA && raDS && raWB) ? 4 : 5);
} else {
    if ((!raNA && raDS && raWB) || (raNA && raDS && raWB)) role = 3;
    else if (!raNA && !raDS && raWB)                       role = (ctx_flags & 0x400) ? 3 : 4;
    else                                                   role = (raNA && raDS && raWB) ? 4 : 5;
}
```

Factory defaults are `raNA=1, raDS=1, raWB=0, waCV=0x8300` → **role 1**. Role **6** is
"NAT router whose WAN uplink is wireless", and that is the one value that forces create/AP mode.
`airportctl/mode.py` reproduces this exactly; `airportctl/test_mode.py` checks every branch
offline.

`waCV`'s uplink bit is also written at *runtime*, right after the Wi-Fi loader runs:

```c
/* FUN_0065746c, after FUN_0068b0c8 */
for each radio: if (radio->flags & 2 /* STA */) waCV = (waCV & ~0x8000) | 0x10000;
for each radio: if (radio->flags & 8 /* WDS */) waCV = (waCV & ~0x8000) | 0x10000;
if (waCV & 0x10000) ACPClearProblemDirect('waNL' /* WAN no link */);
```

That is only the in-memory copy, but it is the clearest proof of what the bit means — and a
warning: if a client ever *stores* `waCV` with `0x10000`, the role becomes 6 and `raSt` is dead.
`airportctl mode wan wired` puts it back.

### A third gate that is normally inactive

Inside the `else` branch, `raSt == 1` is still downgraded to create when `FUN_00672b94()` is
non-zero. That function just returns `DAT_00d60334`, the **soft-reset-mode** flag, set by
`FUN_00677578` ("Begin soft reset mode.", posts problem `'soft'`) and cleared by `FUN_00675268`.
It is 0 in normal operation.

## What happens once the gate is open

`FUN_00689ab8` sets `radio->flags |= 2`, which makes the VAP type 1 (STA). Then
`FUN_00684e34` — called immediately after `FUN_0068b0c8` in every init/apply path — walks the
VAPs and, for `vap->type == 1 && radio->flags & 2`, calls `FUN_006845e4` to write the
supplicant config and spawns

```
/sbin/wpa_supplicant -K -M %s -F %s -D net80211 -i %s -c %s
```

`FUN_006845e4` writes `ap_scan=1`, `network={ ssid="…", scan_ssid=1, mode=0 }` and, for
`raWM == 5`, `proto=RSN / pairwise=CCMP / group=CCMP TKIP WEP104 / key_mgmt=WPA-PSK` with
`psk=<64 hex>` taken **verbatim from `raWE`** — i.e. the same 32-byte PMK rule as the AP side, so
`airportctl wifi join` already supplies the right key material. (`raWM` 3/8 → WPA, 4/6/7 →
WPA+RSN, 5 → RSN, 1/2/9-12 → WEP.) `proxy_sta=1` / `wds_partner=` only appear for VAP types 7/3,
i.e. the extend/WDS roles.

The supplicant is **wpa_supplicant v0.6.5** (statically linked into the crunched binary): no SAE,
no PMF. **In practice it never gets that far — see below.**

## Confirmed on hardware (2026-09-23): the supplicant segfaults at startup

Once the gate is open, `FUN_00684e34` *does* spawn `/sbin/wpa_supplicant`, but it dies instantly
(zombie). `/sbin/dmesg` shows the cause:

```
pid NNN (wpa_supplicant), uid 0: exited on signal 11 (core not dumped)
... badvaddr: 0x0000004C   cause: 0x08 (load)   pc: 0x005CA34C
```

It is a **NULL-pointer SIGSEGV at startup**, not an association failure. `/sbin/wpa_supplicant`,
`/sbin/ACPd` and `/bin/ls` are the *same* crunchgen binary (inode-shared), so you can disassemble
the crash in your own copy of it (image base `0x400000`;
`mips-linux-gnu-objdump -d -EB -m mips:3000 --start-address=0x… ACPd.bin`). The chain: net80211
init calls its **"add interface"** step; it fails and init logs **`"Failed to add interface %s"`**;
the failure path then calls the driver deinit, which unconditionally calls **"Deinit Legacy WDS"**
(`FUN_005ca318`); that routine reads `drv->0x90` (still NULL, because "add interface" bailed) and
dereferences it at `+0x4C` → crash. So the real failure is **"failed to add interface"** — the
supplicant's own EAPOL state-machine init (`eapol_sm_init`) fails — and the segfault is a secondary
unchecked-NULL bug in the cleanup. The proxy-STA variant (`wifi join --psta`, VAP type 7) gives the
**identical crash** (same `pc 0x005CA34C`), so it's not a way around this.

The crash is **unconditional and config-independent**: running the supplicant by hand with a config
that contains only `ctrl_interface=` — no SSID, no PSK, no network — reproduces the exact same crash,
even against a hostap interface, without disturbing the running AP. It dies before any scan or
association, so the target network's security (WPA2/mixed/whatever) is irrelevant. Native client
join is therefore **non-viable on 7.8.1** — this is a bug in Apple's bundled `wpa_supplicant`, not a
setting. The kernel radio is fine (`hostapd` works), so the route to a working join is to run a
supplicant of your own — which is what the next section does.

**Capture it without touching credentials:** don't `cat /etc/wpa_supplicant*.conf` (it holds the
PMK). Everything you need is in `ps` (the zombie), `ifconfig wlan0` (state), and `dmesg` (the signal
+ register dump), plus static disassembly at the `pc`.

## A replacement supplicant: works

Because the defect is entirely in Apple's userland `wpa_supplicant` and **not** in the kernel or
radio, the fix is to *bypass* that binary: run a stock `wpa_supplicant` you build yourself on a
station vap you create by hand. This does not use the `ctim`/`raSt` gate at all — ACPd is never asked
to join anything.

**Result (A1392, 7.8.1, 2026-09-23):** stock **wpa_supplicant 0.7.3**, cross-compiled by
[`crossdev/wpa-build/build-wpa.sh`](../crossdev/wpa-build/README.md), scans, associates with a
third-party WPA2-PSK (CCMP) router, completes the 4-way handshake and carries traffic both ways
(gateway 0% loss, internet ~21 ms). With `airtunesd` restarted on the station interface, the
Express advertises `_raop`/`_airplay` on the home network and plays AirPlay from phones and laptops
there. ACPd keeps running, and the 5 GHz AP stays up alongside the 2.4 GHz client.

**The kernel side.** The `ath` driver advertises `drivercaps=<STA,…,WPA1,WPA2,…,WDS,BGSCAN,…>` and
`cryptocaps=<…,AES,AES_CCM,…>` — hardware WPA2/CCMP in station mode. Destroy the hostap vap, create a
managed one (`ifconfig wlan2 create wlandev ath0` comes up `media: … 11ng`, *no* `hostap`), and
`ifconfig wlan2 scan` lists the neighbours, e.g.

```
SSID            BSSID              CHAN  S:N   CAPS
HomeWiFi        xx:xx:xx:xx:xx:xx   11   21:0  EP  RSN HTCAP WME    <- WPA2 (RSN), strong signal
```

**The ABI surprise.** The kernel is NetBSD 4.0_STABLE, but its `net80211` is **FreeBSD 8-era**
(vaps, 802.11n), so the NetBSD 4.0 headers are wrong in several places: `SIOCS80211`/`SIOCG80211`
numbers, the scan request/result ioctls and record layout, `OPTIE` → `APPIE`, and even
`struct if_msghdr` (152 bytes, not 144). 0.7.3 is the first release whose `driver_bsd.c` speaks
FreeBSD 8 net80211; with shim headers fixing the rest, it builds with **no edits to upstream source**.
The full table, and how each value was found, is in the
[wpa-build README](../crossdev/wpa-build/README.md#why-073-and-the-kernel-abi).

**Running it** — [`crossdev/wpa-build/join-test.sh`](../crossdev/wpa-build/join-test.sh), over the
LAN cable, ~70 s:

1. `kill -STOP` ACPd, kill the 2.4 GHz `hostapd`, `ifconfig wlan0 destroy`,
   `ifconfig wlan2 create wlandev ath0` — **one vap per radio**: `ath0` refuses a second vap while the
   hostap one exists (`SIOCIFCREATE2: EIO`).
2. Give `wlan2` a static address, then take it **down**, then start the supplicant. 0.7.3's
   `driver_bsd` downs the interface during init and reads its own `RTM_IFINFO` as "interface removed",
   which closes its EAPOL socket — it then associates forever but never hears 4-way message 1/4.
   Starting from a down interface avoids that. (Set the address *before*: `SIOCSIFADDR` re-inits the
   vap and drops installed keys.)
3. `kill -CONT` ACPd. It leaves `wlan2` alone.
4. Restart `/sbin/airtunesd -i wlan2`: it registers `_raop`/`_airplay` only on its `-i` interface
   (default `bridge0`), and ACPd doesn't respawn it.

The passphrase never leaves the laptop: the harness sends only the derived PMK, into RAM.

**Limits.**

- **Not persistent.** Everything lives in the RAM disk; any reboot or power cut restores the stock
  AP setup and the harness must be re-run over SSH (cable, or via the Express's own AP). Nothing on
  the device autostarts from writable storage — see
  [crossdev § Storage](../crossdev/README.md#storage-usb-and-persistence).
- **Static address.** Running `dhclient` on the station interface made the debug `sshd` stall for
  minutes before auth (most likely reverse DNS after `resolv.conf` changed), so the harness uses a
  static IP outside the router's pool.
- **Leaf only.** A 3-address station can't bridge other hosts' frames, so the Express's LAN port and
  AP are *not* joined to the home network — only its own services (AirPlay) move there.
- **WPA2-PSK only.** No SAE (WPA3), no PMF, no EAP — a 2010 supplicant, built minimal.

## Recipe: the firmware's own join (reproduces the crash)

Cable to the LAN port, `nmcli c up airport-probe`, then:

```sh
cd .
python3 -m airportctl mode show                 # confirm: role 1, ctim <unset>
python3 -m airportctl mode ctim now             # the fix; read-back must be non-zero
python3 -m airportctl mode show                 # gate should now say OK
python3 -m airportctl wifi join YOUR-SSID --wifi-password @/path/to/pw --band 2.4 --reboot
```

Then over the cable (`tools/essh.sh`), check in this order:

1. `ps | grep wpa_supplicant` — the single most direct yes/no.
2. `cat /etc/wpa_supplicant*.conf` — should show `ssid="YOUR-SSID"`, `key_mgmt=WPA-PSK`,
   `psk=<64 hex>` matching our PMK.
3. `ifconfig wlan0` — `media: … hostap` means it is still an AP (gate not open); a station link
   shows no `hostap` mode and an associated BSSID.
4. `tools/find_express.py` to see whether it took a DHCP address on the target network.

**Keep connection sharing on `nat` for the first test** so the Express stays the DHCP router at
`10.0.1.1` on the cable and recovery is one `airportctl wifi restore` away. Only after a join
works should you switch to `mode sharing bridge` (what you actually want for AirPlay: the Express
sits on the house LAN with no double NAT) — at that point it no longer serves DHCP on the
cable, so find it again with `python3 find_express.py`.

**Safety:** do not leave a create-mode AP whose SSID+PMK match your real network. If the
join fails back into AP mode, restore immediately:

```sh
python3 -m airportctl wifi restore backups/WiFi-<name>-<ts>.cfb --reboot
```

## What "extend" (repeater) would need

`FUN_0068b0c8` registers the whole dynamic-WDS/proxy-STA framework —
`wifi.dwds.sta.join`/`.leave`, `wifi.proxy.sta.discovery`/`.idle`, `wifi.proxysta.status`,
`wifi.scan.request`/`.complete`, `wifi.wps.credentials`, plus the roam tunables
`rssi_5ghz_prefer`, `rssi_roam_threshold`, `band_pref`, `join_timeout` — and the supplicant
config generator emits `proxy_sta=1`, `ifsta=`, `proxysta_interfaces=`, `dwds_role=`,
`wds_partner=` for VAP types 3 and 7. So repeater mode is real firmware, driven by the blob keys
`dWDS` / `pSTA` on top of the same `raSt` gate. It is still Apple-to-Apple WDS on the other end,
so it does not help with a third-party router: for "extend", the practical answer remains a separate
Wi-Fi→Ethernet bridge feeding the Express's LAN port.

## Tooling in this repo

* `airportctl/mode.py` + `airportctl mode show | ctim | sharing | wan`:
  * `mode show` — reads `ctim`/`waCV`/`raNA`/`raDS`/`raWB`/`waUB` plus per-radio `raSt`, prints
    the computed role and exactly why join is or is not blocked.
  * `mode ctim [now|N]` — stores the configuration timestamp (with read-back).
  * `mode sharing {nat,dhcp,bridge}` — the three AirPort-Utility connection-sharing choices,
    with the "you will lose 10.0.1.1" warning.
  * `mode wan {wired,wireless,show}` — flips `waCV`'s uplink bit (only needed if `mode show`
    ever reports role 6).
* `airportctl/test_mode.py` — offline check of the role model against every firmware branch.
* `ghidra_scripts/FindStore.java` — find stores to a struct offset, optionally with a given
  immediate (how `ctx+0x24` was traced).
* `ghidra_scripts/NameFuncs.java` — recovers **2310 real function names** from the `__func__`
  strings ACPd passes to its lock/log wrappers. Run it on your own import and you get
  `ACPGetPropertyDirect`, `ACPSetPropertyDirectEx`, `ACPPostProblemDirect`,
  `ACPPropertyHandlerInstallDirect`, `ACPGetImportantProblemsString`, … back. Start here: it
  makes everything else in this document far easier to follow.

## Reference: the ACP property table

`FUN_00807418` is the property lookup: a flat array of 12-byte records
`{ fourcc, type, flags }` starting at VMA **0xc5af38**, terminated by a zero fourcc (520 records).
`type`: 1=byte, 2=string, 5=uint32, 6=bool, 7=IPv4 addr, 8=MAC, 10=action, 12=IPv6, 13=data.
`flags`: 0x04 = setprop needs the privileged flag, 0x08 = setprop needs auth, 0x20/0x40/0x80 =
not directly get/settable (a registered handler owns it). Dump it with
**`python3 tools/proptab.py /path/to/ACPd.bin [fourcc ...]`**:

```
0x00c5b34c  'raDS'   type=6  (bool    ) flags=0x00 -
0x00c5b358  'raNA'   type=6  (bool    ) flags=0x00 -
0x00c5b364  'raWB'   type=6  (bool    ) flags=0x00 -
0x00c5b418  'raSt'   type=5  (uint32  ) flags=0x80 handler-only(0x80)
0x00c5b64c  'waCV'   type=5  (uint32  ) flags=0x00 -
0x00c5b784  'waUB'   type=6  (bool    ) flags=0x00 -
0x00c5bdc0  'ctim'   type=5  (uint32  ) flags=0x00 -
```

So every property the gate depends on is freely settable over ACP. (Note the *flat* `raSt`
property is handler-only — irrelevant here, since `raSt` is set inside the `WiFi` blob.)

## Reproducing this

Every address above refers to `/sbin/ACPd` from **firmware 7.8.1** on an A1392, image base
`0x00400000`. The binary is Apple's and is not distributed here — pull it off your own unit and
import it as described in [extracting-acpd.md](extracting-acpd.md), then:

```sh
JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java)))) \
/path/to/ghidra/support/analyzeHeadless "$PWD/ghidra_project" acpd \
  -process ACPd.bin -readOnly -noanalysis \
  -scriptPath "$PWD/ghidra_scripts" -postScript Decompile.java out/ 0x689ab8 0x65746c 0x684e34
```

(`-process ACPd.bin` matters — without it headless picks no program and the scripts see `null`.)
On a different firmware version the addresses will move; `ghidra_scripts/FindStr.java` and
`ImmScan.java` re-find the anchors (the `ctim` fourcc `0x6374696d`, the string
`"/sbin/wpa_supplicant -K -M %s -F %s -D net80211 -i %s -c %s"`).
