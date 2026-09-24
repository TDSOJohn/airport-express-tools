# The ACP RPC surface of firmware 7.8.1

ACP exposes two things: ~520 **properties** (`getprop`/`setprop`, opcodes 0x14/0x15) and
**RPCs** (opcode 0x19), which carry a CFL plist `{function: <name>, inputs: {...}}` and
return `{status: ..., outputs: {...}}`. The RPCs are the richer interface — they are what
AirPort Utility and the base station's own daemons use for anything that isn't a flat
setting — and they are not documented anywhere else.

This page covers every RPC the firmware registers. Each one was classified by reading its
decompiled handler, and the read-only ones were **called on a live A1392 (7.8.1) on
2026-09-24**. The results are below.

```sh
airportctl rpc --list                    # everything, read-only ones unmarked
airportctl rpc acprpc.show               # the live registry, straight from the device
airportctl rpc wifi.scan.results.wlan1   # read-only calls need no --force; inputs are filled in
```

## Two registries, 87 names

`acprpc.show` prints the daemon's live registry. On the test unit it listed **87** RPCs,
from two sources:

* **ACPd's own** — registrar `FUN_006717dc`, listed with flags `0x0`/`0x1`. 55 names;
  the regenerated map is `re/rpc_map.txt`.
* **Registered by other daemons over IPC** — registrar `FUN_0080b058`, listed with flags
  `0x2`. ACPd forwards the call to the process that registered the name:

  | registrant | names |
  |---|---|
  | hostapd, **one set per Wi-Fi interface** (`wlan1` below) | `wifi.{channel,mcs,tx.rate,mcast.rate}.{get,set}.<if>`, `wifi.statistics.<if>`, `wifi.scan.{results,request}.<if>`, `wifi.{debug,ampdu}.set.<if>`, `wifi.rotate.gtk.<if>`, `wifi.tal.{add_update,remove}.<if>`, `wifi.neighbor.set.<if>`, `wsc.internal.{start,stop,preauthorize,authorize,denied}.<if>` |
  | dhcpd | `dhcp.server.leases.get` |
  | dhclient | `dhcp.client.interface.state`, `dhcp.client.lease.action` (+ `dhcp6.client.interface.state` when DHCPv6 runs) |
  | mDNSResponder | `mdns.btmm.user`, `mdns.btmm.clearAllUsers`, `icloud.mdns.lhbag` |
  | iCloudd | `icloud.newcastle.bag`, `icloud.mdns.badsig`, `icloud.cached.lhbag` |

  The map is `re/rpc_map_remote.txt` (`RpcMap.java 0x80b058`). The hostapd names are
  built at run time (`"wifi.statistics." + ifname`), so the script shows them as `?`. The
  schemas in `airportctl/rpc.py` were resolved by hand from `FUN_005b44fc` (hostapd) and
  `FUN_005cbf48` (Apple's wpa_supplicant, which registers a similar set in client mode).

Per-interface names only exist while that interface's hostapd is running. In the test
state (the replacement supplicant from [join-mode.md](join-mode.md) on `wlan2`, `wlan0`'s
hostapd killed) only `wlan1` was registered. `wifi.statistics.wlan0` failed as unknown,
even though `acpd.system.show` still listed `wlan0`. ACPd's own view goes stale when
something outside it changes the interfaces.

## Wire behaviour, as observed

* **Unknown name and missing required input fail the same way:** the ACP header carries
  error `0xffffe5b9` = −6727 (`kNotFoundErr`) and no body. `acpmon.show` with no `cmd`
  fails like this; with `cmd: ""` it works.
* **Handler errors** come back in the body instead: `{'outputs': {}, 'status': -6727}`
  (`acpd.system.interfaces` on this unit).
* **Negative integers are 8-byte signed CFL ints** (RSSI −52, `txrate` −1, status −6727).
  1/2/4-byte ints are unsigned, as in Apple's bplist. `cfl.py` decoded all ints as
  unsigned before this was found.
* **Types 7 and 10 are both strings on the wire.** 10 reaches the handler as a C `char *`
  (e.g. `btmm.rpc` `strcmp`s `action` against `"start"`), 7 as a `CFString`. That settles
  the one open question of the static map.

## Every RPC, classified

**read** = handler only reads; called live. **action** = does something but stores no
setting. **event** = a notification that a helper daemon sends *into* ACPd; calling it
yourself injects a fake event. **write** = changes live or stored settings.

### read (all called on the A1392)

| RPC | inputs → outputs | what it returns |
|---|---|---|
| `acprpc.show` | `cmd` → `output` | the live registry (name, flags, `BUSY` while it runs) |
| `acpmon.show` | `cmd` → `output` | ACP monitoring sessions (kqueue fds, session list) |
| `acpd.system.show` | → `output` | ~6 KB text dump of ACPd's system object: role ("DHCP/NAT via 802.3"), flag word decoded (NAT, DHCP, IPv6 modes, BTMM, `last cfg time` = `ctim`), each Ethernet PHY with link state and WAN/LAN role, radios (`ath0` ch 6 mode 6, `ath1` ch 132 mode 5), VAPs with SSID/MAC, bridge members, LAN address and DHCP range |
| `acpd.system.interfaces` | → `data` | the configuration option ("DHCP/NAT via Ethernet", …) plus WAN/LAN/Protected WAN/Guest interface details; returned status −6727 on this unit (cause not traced; the WAN port was unplugged) |
| `acp.getStaticConfig` | `variables`(dict, default `{}`) → `variables` | **the boot environment**: `apple-sn` (serial), `ethaddr`, `apple-sku` (`ETSI` = EU regulatory domain), `apple-minver`, `radio-cal-ath0/1` (calibration blobs). Pass `{name: ...}` keys to read single variables |
| `wifi.interface.stats.get` | → `data` | net80211 counters per VAP, zeros omitted (`rx_beacon`, `rx_mgmt`, `rx_ssidmismatch`, `tx_badstate`, …) |
| `wifi.chain.noise.get` | `index` → `data` | per-chain noise floor for radio *index*: `factory-cal-nf`, `median-pwr`, `uncal-nf`, control/extension channel (e.g. −97/−96 dBm) |
| `wifi.antenna.config.get` | `index` → `rxant`, `txant` | **a stub**: the handler validates `index` and never writes the outputs; always 0/0 |
| `wifi.channel.get.<if>` | `interface` → `channel` | 132 on `wlan1` |
| `wifi.mcs.get.<if>` | `interface` → `mcsindex` | 127 (presumably auto) |
| `wifi.tx.rate.get.<if>` | `interface` → `txrate` | −1 (presumably auto) |
| `wifi.mcast.rate.get.<if>` | `interface` → `rate` | 6 (Mb/s) |
| `wifi.statistics.<if>` | `interface` → `data` | `{wlan1: [...]}`: one entry per associated station; empty with no clients |
| `wifi.scan.results.<if>` | `interface` → `data` | **the base station's own site survey**, with decoded IEs: `SSID_STR`, `BSSID`, `CHANNEL`, `RSSI`, `NOISE`, `RATES`, `CAPABILITIES`, `RSN_IE` (ciphers/AKMs), `HT_CAPS_IE`, `80211D_IE` (country, per-band max power), raw `IE`. 8 networks on the 5 GHz radio here |
| `dhcp.server.leases.get` | `pool` → `data` | `{leases: [{ipAddress, macAddress, hostname, interface, pool, leaseEnds, leaseEndsTime}]}`; `pool` is one of `all active free expired abandoned backup` |

Trimmed samples (identifiers replaced):

```text
acp.getStaticConfig  -> {'apple-minver': '76200.16', 'apple-sku': 'ETSI', 'apple-sn': '<serial>',
                         'ethaddr': '20:c9:d0:xx:xx:xx', 'radio-cal-ath0': '020e20c9d0…', …}
wifi.chain.noise.get {'index': 1} -> {'factory-cal-nf-ctl': [' -98.00', ' -96.25'],
                         'median-pwr-ctl': [' -96.75', ' -96.00'], 'uncal-nf-ctl': ['-101.75', '-103.25'], …}
wifi.scan.results.wlan1 -> {'wlan1': [{'SSID_STR': 'neighbour', 'BSSID': '0A:…', 'CHANNEL': 100,
                         'RSSI': -52, 'RATES': [6, 9, …, 54], 'RSN_IE': {'IE_KEY_RSN_UCIPHERS': [4],
                         'IE_KEY_RSN_AUTHSELS': [2], …}, '80211D_IE': {'IE_KEY_80211D_COUNTRY_CODE': 'IT', …}}, …]}
dhcp.server.leases.get {'pool': 'active'} -> {'leases': [{'ipAddress': '10.0.1.4', 'hostname': 'laptop',
                         'pool': 'active', 'leaseEndsTime': 129716, …}]}
```

`getStaticConfig` returns the serial number and calibration data, and `scan.results`
returns your neighbours' networks. Don't paste either into a public issue unedited.

### action

| RPC | what the handler does |
|---|---|
| `acpd.checkConnection` | HTTP GET `http://apsu.apple.com/version.xml`: the firmware-update check. Not read-only: it makes an outbound request |
| `acpd.clearLog` | truncates `/var/log/ACPd.log` and `.1`–`.3` |
| `syslogd.flush` | **discards** the in-memory syslog buffer (it frees the entries, it doesn't write them out) |
| `acpd.update.phys` | calls a PHY-refresh hook if one is installed |
| `acpd.busyLoopControl` | `cmd: start` spawns `/sbin/busyloop` (CPU load), `stop` kills it |
| `btmm.rpc` | `action: start|stop` Back to My Mac |
| `wifi.diagnostic.mode` | `action: start|stop` → posts internal events 10/11 |
| `wifi.scan.request` | runs a scan **only when `ctim == 0`** (unconfigured / setup mode). With the configuration timestamp set it's a no-op returning 0. The old static reading had this inverted |
| `wifi.scan.request.<if>` | asks that interface's hostapd to scan |
| `wifi.rotate.gtk.<if>` | rotates the group key |
| `pppoe.test-client.check-connection` | `serviceName`, `userName`, `password` → `result`: spawns `pppoectl` + `ifwatchd` to test a PPPoE login |
| `remoteBonjour.browse` | `serviceType`, `domain` (default `local.`) → `uuid`: starts a Bonjour browse on behalf of the ACP session |
| `acp.injectPacket` | `packetInfo`: writes a raw frame to `/dev/bpf` (Ethernet or 802.11) |
| `user.checkFileSharingAccess` | `flags`, `user`, `pass` → `access`, `info`: checks credentials against the file-sharing user list (`usrd`) |
| `wsc.start` / `wsc.stop` / `wsc.authorize` | open/close a WPS window, authorize a client by MAC + PIN (flags 0x1) |
| `dhcp.client.lease.action`, `dhcp.client.interface.state` | ACPd → dhclient commands (renew/release, interface up/down) |
| `mdns.btmm.clearAllUsers`, `icloud.newcastle.bag`, `icloud.mdns.badsig`, `icloud.cached.lhbag` | BTMM / iCloud housekeeping (commands to mDNSResponder / iCloudd; handlers not read) |

### event (daemon → ACPd notifications; don't call)

`wifi.ap.status`, `wifi.sta.status`, `wifi.sta.event`, `wifi.legacy.wds.status`,
`wifi.legacy.wds.link`, `wifi.dynamic.wds.extender.status`, `wifi.proxysta.status`,
`wifi.dwds.sta.join`, `wifi.dwds.sta.leave`, `wifi.proxy.sta.discovery`,
`wifi.proxy.sta.idle`, `wifi.scan.complete`, `wifi.wps.credentials`,
`wsc.internal.join{Requested,Abandoned,Succeeded,Failed,Expired}`, `wsc.internal.data`,
`dhcp.client.lease.{accept,reject,release}`, `dhcp6.client.lease.address-delete`,
`dhcp6.client.lease.prefix-delegation`.

Most just queue the dict for the Wi-Fi or DHCP state machine (`FUN_00674f64`). Several
act at once: `dhcp6.client.lease.address-delete` runs `ifconfig <wan> inet6 <addr>
-alias`, and `wsc.internal.joinSucceeded` hands a PSK to the WPS state machine.

### write

| RPC | effect |
|---|---|
| `acp.setStaticConfig` | **sets boot-environment variables** (serial, MAC, radio calibration). Gated by `FUN_0067f05c` (not yet identified). Can brick the unit: never call it |
| `wifi.diagnostic.caldata` | `action: read|write`, `interface`, `path`: moves `radio-cal-*` radio calibration data to or from a file (from the handler's strings; not traced in detail) |
| `acpd.setDirtyPlist` | `drTY`, `allowMinimal`: applies a configuration change set. This is AirPort Utility's "Update" |
| `acp.setDynamicStoreValue` | `key`, `value`: writes the `DynS` dynamic store and posts a change event |
| `wifi.channel.announce` | `interface`, `channel`: switches the radio **and stores** `WiFi.radios[n].raCh` |
| `wifi.antenna.config.set` | a stub, like its getter: validates `index`, does nothing |
| `wifi.{channel,mcs,tx.rate,mcast.rate,debug,ampdu}.set.<if>` | runtime hostapd settings (`mcast.rate.set` also takes `type`) |
| `wifi.tal.add_update.<if>`, `wifi.tal.remove.<if>` | `talEntry` dict |
| `wifi.neighbor.set.<if>` | 802.11k neighbour report entry: `action`, `channel`, `operatingclass`, `bssidinfo`, `phytype`, `mac` |
| `wsc.internal.{start,stop,preauthorize,authorize,denied}.<if>` | ACPd → hostapd WPS control |
| `mdns.btmm.user` | `name`, `secret`: BTMM credentials |
| `icloud.mdns.lhbag` | `lhBagData` |
| `cloud.update.<service>` | `changes` → `changes`, `commitUUID`: iCloud-pushed config (the unit registers one per service UUID, e.g. `cloud.update.f21bbe1f-…`) |

### Not called yet: `acpd.parseDirtyPlist`

`drTY` → `result`, `interruptions`. It runs the same worker as `setDirtyPlist`
(`FUN_00658a18`) with its apply flag set to 0. It answers `"minimal"`, `"restart"` or
`"reboot"`, which says how disruptive a change set would be, and `interruptions` names
what would drop. The worker only commits when the flag is set, so this looks like a true
dry run. But the per-property helpers it calls (`FUN_0067e484`, `FUN_0067f5fc`) haven't
been read, and the `drTY` format isn't known. It stays uncalled until both are clear.
If it is a dry run, it's the safe way to learn which properties apply live.

## Registration encoding

`FUN_006717dc(name, flags, handler, <schema...>)` is ACPd's registrar and
`FUN_0080b058` the remote one, with the same arguments. The schema is a varargs list
terminated by a NULL name. `FUN_00671404` turns it into the plist
`{flags: <int>, params: [{name, type, defaultType, input}, ...]}`. The per-entry stride is
**variable**, which is the thing to get right when reading these call sites:

```c
name = w[0];  if (name == NULL) end_of_list;
type = w[1];                       /* must be non-zero */
input = w[2];                      /* bool: input parameter vs output */
if (input == 0)            stride = 3;
else {
    defaultType = w[3];
    stride = (defaultType == 0 || defaultType == 0x10) ? 4 : 5;  /* w[4] = default value */
}
```

Names are inline CoreFoundation constant strings (`isa == 0x56070000`, text at `+8`).

Regenerate with `ghidra_scripts/RpcMap.java` (see [extracting-acpd.md](extracting-acpd.md)):

```sh
analyzeHeadless ... -postScript RpcMap.java 0x6717dc rpc_map.txt          # ACPd's own
analyzeHeadless ... -postScript RpcMap.java 0x80b058 rpc_map_remote.txt   # other daemons
```

The script tracks o32 arguments through registers and the outgoing stack area. Up to
2026-09-24 it treated a store (`sb s2, …`) as a write to `s2`. That lost the value and
silently cut short the schemas of `acpmon.show`, `pppoe.test-client.check-connection`,
`icloud.mdns.badsig` and `icloud.cached.lhbag`.

The generic `<group>.sysctl` registrar (`FUN_00671808`; the old version of this page
called it `<group>.show`) exists in the binary but has no callers, and no `.sysctl` name
appears in the live registry. It would expose debug variables with a `group`/`name`/
`action` interface, where an `action` starting with `=` writes the variable.

## Type codes

| code | reading | evidence |
|---|---|---|
| 1 | bool | `allowMinimal` |
| 2 | int or data | `interruptions`, `lhBagData` |
| 3 | data | `mac`/`psk` in the WPS calls; `bss_info`, `ies` |
| 5 | dictionary | `data`, `credentials`, `variables`, `drTY`; live replies |
| 7 | string (`CFString` in the handler) | live `output` replies |
| 9 | number | `defaultType` switch in `FUN_00671404`; live replies |
| 10 | string (C `char *` in the handler) | live `cmd`/`interface`/`pool` inputs |
| 12 | IPv4 address | `ipv4` (DHCPv4), `address` (DHCPv6) |
| 13 | MAC address (6 bytes) | handlers copy 6 bytes |
| 14 | session handle | only `__acpSession` |
| 15 | any | only `acp.setDynamicStoreValue`'s `value` |
