# Client mode ("join a wireless network")

| Layer | A1392 / 7.8.1 | Tool |
|---|---|---|
| [Gate](#the-gate): `raSt = 1` honoured only if `ctim ≠ 0` and role ≠ 6 | opens with a stored `ctim`; the radio then comes up as a station (L) | `airportctl mode` |
| [Firmware supplicant](#firmware-supplicant) (wpa_supplicant 0.6.5) | segfaults at startup with every configuration (L) | none |
| [Replacement supplicant](#replacement-supplicant) (wpa_supplicant 0.7.3) | joins WPA2-PSK networks, AirPlay on the joined network (L) | `airportctl join` |

Other models: `join` needs an Atheros radio and a build for the CPU
([models.md](models.md#airportctl-on-each-model)). Commands:
[airportctl](../airportctl/README.md#commands).

## The gate

Per radio, `raSt` in the [`WiFi` blob](wifi-blob.md): 0 = create (AP), 1 = join (STA),
3 = off. The VAP loader reads it only when both conditions hold:

```c
/* FUN_00689ab8, ~0x689d18 */
if (ctx->role /* ctx+0x24 */ == 6 || ctim == 0) { raSt = 0; radio->flags |= 1 /* AP */; }
else                                            { raSt = blob["raSt"]; if (raSt == 1) radio->flags |= 2 /* STA */; }
```

| | |
|---|---|
| Gate closed | a blob with `raSt = 1` comes up as an **AP broadcasting the target SSID with its PMK** (an evil twin) |
| Third condition | in the `else` branch, `raSt = 1` is downgraded to create while `FUN_00672b94()` (= `DAT_00d60334`, soft-reset mode) is non-zero; set by `FUN_00677578` (posts problem `soft`), cleared by `FUN_00675268` |

### `ctim`

| | |
|---|---|
| Property | `ctim` (`0x6374696d`), configuration timestamp; table entry `0xc5bdc0`, uint32, flags 0: get- and settable over ACP; no handler |
| Unset | units configured only over ACP have none (`getprop` → -10), so they count as never configured |
| Set by | every AirPort Utility apply; `FUN_00686384` (`wifi.wps.credentials`) applies `{ctim: <now>, WiFi: <blob>}`; `airportctl mode ctim now` |
| Cleared by | nothing in ACPd; persists across reboots |
| Other effects of `ctim == 0` | problem `ctim` posted (`FUN_00659910`); `ACPCloud_*` / certificate paths gated (`FUN_0067f010`); `wifi.scan.request` scans only in this state |

### Role (`ctx+0x24`)

`ctx` = `DAT_00e46ec0` (0x230 bytes, filled by `FUN_0065746c`). Role is computed at init from
five stored properties:

| Property | Type | Meaning |
|---|---|---|
| `raNA` | bool | connection sharing: NAT |
| `raDS` | bool | connection sharing: hand out DHCP leases |
| `raWB` | bool | connection sharing: off / bridge |
| `waUB` | bool | WAN port used as a bridge |
| `waCV` | int | WAN config bits: `0x8000` wired uplink, `0x10000` wireless uplink, `0x800` a third uplink type |

```c
/* FUN_0065746c */
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

| Role | Setup |
|---|---|
| 1 | NAT router, wired WAN (factory: `raNA=1 raDS=1 raWB=0 waCV=0x8300`) |
| 4 | bridge (`airportctl mode sharing bridge`) |
| 6 | NAT router with a wireless WAN uplink: forces AP mode, closes the gate |

At run time, after the Wi-Fi loader, ACPd sets the in-memory `waCV` for any STA or WDS radio:

```c
for each radio: if (radio->flags & (2 /* STA */ | 8 /* WDS */)) waCV = (waCV & ~0x8000) | 0x10000;
if (waCV & 0x10000) ACPClearProblemDirect('waNL');
```

If `0x10000` is ever stored, the role becomes 6; `airportctl mode wan wired` clears it.
`airportctl/mode.py` implements the formula; `airportctl/test_mode.py` covers every branch.

Gate properties as dumped by `tools/proptab.py`:

```
0x00c5b34c  'raDS'   type=6  (bool    ) flags=0x00 -
0x00c5b358  'raNA'   type=6  (bool    ) flags=0x00 -
0x00c5b364  'raWB'   type=6  (bool    ) flags=0x00 -
0x00c5b418  'raSt'   type=5  (uint32  ) flags=0x80 handler-only(0x80)
0x00c5b64c  'waCV'   type=5  (uint32  ) flags=0x00 -
0x00c5b784  'waUB'   type=6  (bool    ) flags=0x00 -
0x00c5bdc0  'ctim'   type=5  (uint32  ) flags=0x00 -
```

(The flat `raSt` is handler-only; the gate reads `raSt` from the `WiFi` blob.)

## Firmware supplicant

| | |
|---|---|
| Binary | `/sbin/wpa_supplicant`, a link to the crunched megabinary; v0.6.5: no SAE, no PMF |
| Started by | `FUN_00684e34` (after `FUN_0068b0c8` in every init/apply path), for VAP type 1 with radio flag 2: `/sbin/wpa_supplicant -K -M %s -F %s -D net80211 -i %s -c %s` |
| Config (`FUN_006845e4`) | `ap_scan=1`, `network={ ssid="…", scan_ssid=1, mode=0 }`; `raWM` 5 → `proto=RSN pairwise=CCMP group=CCMP TKIP WEP104 key_mgmt=WPA-PSK` (3/8 WPA, 4/6/7 WPA+RSN, 1/2/9–12 WEP); `psk=` = `raWE` verbatim. VAP types 7/3 add `proxy_sta=1` / `wds_partner=` |
| Result (L) | SIGSEGV at startup: `pc 0x005CA34C`, `badvaddr 0x4C`, `cause 0x08` (load); a zombie in `ps` |
| Cause (F) | net80211 "add interface" fails (`Failed to add interface %s`; `eapol_sm_init` fails) → deinit → "Deinit Legacy WDS" (`FUN_005ca318`) dereferences `drv->0x90` (NULL) at `+0x4C` |
| Scope (L) | config-independent: same crash with a config of only `ctrl_interface=`, against a hostap interface, and with `--psta` (VAP type 7) |
| Diagnose | `ps`, `ifconfig wlan0`, `dmesg`; `/etc/wpa_supplicant*.conf` holds the PMK |

The crash disassembles in any copy of the megabinary (image base `0x400000`):
`mips-linux-gnu-objdump -d -EB -m mips:3000 --start-address=0x… ACPd.bin`.

## Replacement supplicant

Stock wpa_supplicant 0.7.3, cross-built with header shims and no source edits
([crossdev/wpa-build](../crossdev/wpa-build/README.md): kernel ABI table, size, config). It
runs on a station VAP created by hand and bypasses the gate; ACPd is never asked to join.

| | |
|---|---|
| Interface | managed VAP `wlan2` on `ath0` (2.4 GHz). One VAP per radio: the hostap VAP must go first (`SIOCIFCREATE2: EIO` otherwise) |
| Kernel caps (L) | `drivercaps=<STA,…,WPA1,WPA2,…,WDS,BGSCAN,…>`, `cryptocaps=<…,AES,AES_CCM,…>` |
| Security | WPA2-PSK (CCMP) only; no SAE / WPA3, PMF, EAP |
| Alongside | 5 GHz AP, Ethernet and ACPd keep running |
| Topology | leaf: a 3-address station can't bridge other hosts, so the LAN port and the AP stay off the joined network; only the Express's own services move there |
| AirPlay | `/sbin/airtunesd -i wlan2`: it registers `_raop` / `_airplay` only on its `-i` interface (default `bridge0`), and ACPd doesn't respawn it |
| Secrets | only the PMK goes to the device; the passphrase stays on the client |
| Persistence | `/mnt/Flash` holds the files (`airportctl join install`); the join itself is redone after each boot by `airportctl join start` or the [autorun](autorun.md) image |
| Verified (L) | scan, association, 4-way handshake, GTK, traffic both ways, AirPlay playback on the joined network (third-party router) |

### Join sequence

As run by `airportctl/payload/autorun.sh` and `crossdev/wpa-build/join-test.sh`:

1. `kill -STOP` ACPd; stop the 2.4 GHz `hostapd`; `ifconfig wlan0 destroy`;
   `ifconfig wlan2 create wlandev ath0`.
2. `ifconfig wlan2 up`, then `down`, then start the supplicant. Starting with the interface
   **down** is required: 0.7.3's `driver_bsd` downs it during init, reads its own
   `RTM_IFINFO` as "interface removed" and closes its EAPOL socket, after which it
   associates but never sees 4-way message 1/4.
3. `kill -CONT` ACPd (it leaves `wlan2` alone).
4. Address: [DHCP](#addressing-dhcp) or fixed.
5. Restart `airtunesd -i wlan2`.

## Addressing (DHCP)

| | |
|---|---|
| Address changes (L) | setting, aliasing, removing or replacing the IPv4 address on a keyed `wlan2` keeps the WPA keys; a lease is set on the live link |
| Stock `/sbin/dhclient` | ISC dhclient 4.1.0 + Apple changes (`main` = `FUN_00556de0`), tied to ACPd: registers the `dhcp.client.*` RPCs, sends `dhcp.client.lease.accept` on every bind (`FUN_00554d84`, no flag to disable), exit hook runs `acp-update-network` and `dns-update-script`, `dhclient-script` sets `0.0.0.0` in `PREINIT`. Not used |
| Own client | [`crossdev/src/dhcpc.c`](../crossdev/src/dhcpc.c): raw `/dev/bpf`, 120 KB static, one-shot; prints the lease as shell variables; never touches the interface, routes or `resolv.conf` |

`autorun.sh` flow:

1. Join with no address on `wlan2`.
2. `dhcpc`: DISCOVER → OFFER → REQUEST → ACK (retransmits cover a handshake still running
   after `status: associated`).
3. Set the leased address on the live link, ping the router. Only if the router stays silent
   ~10 s: re-key (freeze ACPd, stop the supplicant, set the address, `wlan2` down, restart the
   supplicant).
4. Move AirPlay; leave a renew loop running.

| Behaviour | |
|---|---|
| Renew loop | at T1: unicast to the server, then broadcast, then a fresh DISCOVER; retries every minute; applies a changed address the same way. Follows T1/T2 from the original binding |
| Routes, DNS | no default route, `resolv.conf` untouched (AirPlay needs only the local subnet) |
| No server | `FALLBACK_IP` (+ `GW`, `MASK`) from `join.conf` if set, else the run fails (amber LED); 5 GHz AP and Ethernet stay up |
| Conflicts | no ARP check, no DHCPDECLINE; use a reservation on the router for a stable address |
| Files | log `/mnt/Memory/dhcp.log`, lease `/mnt/Memory/lease` |
| Timing (L) | lease in ~3 s; `join start` to joined + leased ~61 s, of which 20 s is the post-boot settle wait |

| Test | Covers |
|---|---|
| `crossdev/tests/dhcpc-test.sh` | `dhcpc` logic vs busybox `udhcpd` in a network namespace: INIT, INIT-REBOOT, unicast renew, broadcast rebind, NAK, timeout |
| `tests/autorun-mock.sh` | `autorun.sh` order of operations with stubbed device commands |
| On the A1392 (L) | all of the above against a real router; full `join install` → reboot → `join start`; renewal in place; power cycle |

## Name on the network

| | |
|---|---|
| Hostname | from `syNm`: "Base Station airPlay station" → `base-station-airplay-station` |
| mDNS | mDNSResponder announces `<hostname>.local` on every interface, `wlan2` included |
| DHCP | `dhcpc` sends the hostname as option 12 in DISCOVER and REQUEST |
| Rename | `airportctl join install --name` / `airportctl name`: `syNm` is stored at once; hostname, `.local` and the `_airport._tcp` name change when ACPd starts at the next boot (L) |

## Extend (repeater)

Present in firmware, not tested. `FUN_0068b0c8` registers `wifi.dwds.sta.join` / `.leave`,
`wifi.proxy.sta.discovery` / `.idle`, `wifi.proxysta.status`, `wifi.scan.request` /
`.complete`, `wifi.wps.credentials` and the roam tunables `rssi_5ghz_prefer`,
`rssi_roam_threshold`, `band_pref`, `join_timeout`. The supplicant config generator emits
`proxy_sta=1`, `ifsta=`, `proxysta_interfaces=`, `dwds_role=`, `wds_partner=` for VAP types 3
and 7. Driven by the blob keys `dWDS` / `pSTA` behind the same gate; the other end must be an
Apple base station (Apple WDS).
