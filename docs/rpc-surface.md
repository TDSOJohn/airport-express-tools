# ACP RPCs

ACP opcode `0x19` carries a CFL plist `{function: <name>, inputs: {...}}` and returns
`{status: ..., outputs: {...}}`. AirPort Utility and the base station's own daemons use RPCs
for everything that isn't a flat property ([properties.md](properties.md)).

Classification from the decompiled handlers (F); every **read** RPC called on an A1392 on
7.8.1 (L). Schemas: `airportctl/rpc.py`.

```sh
airportctl rpc --list                    # all mapped RPCs; unmarked = read-only
airportctl rpc acprpc.show               # the live registry
airportctl rpc wifi.scan.results.wlan1   # read-only calls: inputs filled in, no --force on a tested model
```

## Registries

88 distinct names (per-interface sets counted once), from two registrars:

| Registrar | Flags in `acprpc.show` | Names |
|---|---|---|
| ACPd, `FUN_006717dc` | `0x0` / `0x1` | 55 (`pppoe.test-client.check-connection` only with PPPoE configured) |
| other daemons over IPC, `FUN_0080b058`; ACPd forwards the call | `0x2` | below |

| Registrant | Names |
|---|---|
| hostapd, one set per Wi-Fi interface (22 names) | `wifi.{channel,mcs,tx.rate,mcast.rate}.{get,set}.<if>`, `wifi.statistics.<if>`, `wifi.scan.{results,request}.<if>`, `wifi.{debug,ampdu}.set.<if>`, `wifi.rotate.gtk.<if>`, `wifi.tal.{add_update,remove}.<if>`, `wifi.neighbor.set.<if>`, `wsc.internal.{start,stop,preauthorize,authorize,denied}.<if>` |
| dhcpd | `dhcp.server.leases.get` |
| dhclient (IPv4) | `dhcp.client.interface.state`, `dhcp.client.lease.action` |
| dhclient -P (DHCPv6, once the WAN has link) | `dhcp6.client.interface.state`, `dhcp6.client.lease.action` |
| mDNSResponder | `mdns.btmm.user`, `mdns.btmm.clearAllUsers`, `icloud.mdns.lhbag` |
| iCloudd | `icloud.newcastle.bag`, `icloud.mdns.badsig`, `icloud.cached.lhbag` |

hostapd schemas from `FUN_005b44fc`; Apple's wpa_supplicant registers a similar set in
client mode (`FUN_005cbf48`). Per-interface names exist only while that interface's hostapd
runs.

| State (L) | Registered |
|---|---:|
| A1392, AP, WAN unplugged | 107 = 54 ACPd + 22 `wlan0` + 22 `wlan1` + 9 other |
| A1392, AP, wired WAN | 109 (+ the two `dhcp6.client.*`) |
| A1392, replacement supplicant on `wlan2`, `wlan0` destroyed | 85 (only `wlan1`'s set) |
| A1301, 7.6.9, AP | 94 ([models.md](models.md#acp-and-access)) |

ACPd's own view goes stale when something else changes the interfaces: with `wlan0`
destroyed, `acpd.system.show` still lists it and `acpd.system.interfaces` returns -6727.

## Wire behaviour

| Case | Result |
|---|---|
| Unknown name, or a required input missing | ACP header error `0xffffe5b9` = -6727 (`kNotFoundErr`), no body (`acpmon.show` without `cmd` fails; `cmd: ""` works) |
| Handler error | in the body: `{'outputs': {}, 'status': -6727}` |
| Negative integers | 8-byte signed CFL ints (RSSI -52, `txrate` -1, status -6727); 1/2/4-byte ints are unsigned |
| Types 7 and 10 | both strings on the wire; 10 reaches the handler as a C `char *`, 7 as a `CFString` |

## Read (all called on the A1392)

| RPC | Inputs → outputs | Returns |
|---|---|---|
| `acprpc.show` | `cmd` → `output` | the live registry (name, flags, `BUSY` while running) |
| `acpmon.show` | `cmd` → `output` | ACP monitoring sessions (kqueue fds, sessions) |
| `acpd.system.show` | → `output` | ~6 KB text: role ("DHCP/NAT via 802.3"), decoded flag word (NAT, DHCP, IPv6 modes, BTMM, `last cfg time` = `ctim`), Ethernet PHYs with link and WAN/LAN role, radios with channel and mode, VAPs with SSID/MAC, bridge members, LAN address, DHCP range |
| `acpd.system.interfaces` | → `data` | interface tree: `config`, `WAN` (name, MAC, IPv4/IPv6), `LAN` = `bridge0` with members: Ethernet with ARP `Cache` and `SwitchCache`, each VAP with `SSID`, `BSSID`, `Channel`, `PHY`, `opmode`, `clients`, parent radio |
| `acp.getStaticConfig` | `variables` (dict, default `{}`) → `variables` | the factory nvram ([boot.md](boot.md#factory-nvram-flash3)); `{name: ...}` keys read single variables |
| `wifi.interface.stats.get` | → `data` | net80211 counters per VAP, zeros omitted |
| `wifi.chain.noise.get` | `index` → `data` | per-chain noise floor for a radio: `factory-cal-nf`, `median-pwr`, `uncal-nf`, control/extension channel |
| `wifi.antenna.config.get` | `index` → `rxant`, `txant` | stub: always 0 / 0 |
| `wifi.channel.get.<if>` | `interface` → `channel` | |
| `wifi.mcs.get.<if>` | `interface` → `mcsindex` | 127 (auto) |
| `wifi.tx.rate.get.<if>` | `interface` → `txrate` | -1 (auto) |
| `wifi.mcast.rate.get.<if>` | `interface` → `rate` | Mb/s (2 on 2.4 GHz, 6 on 5 GHz) |
| `wifi.statistics.<if>` | `interface` → `data` | one entry per associated station |
| `wifi.scan.results.<if>` | `interface` → `data` | site survey with decoded IEs: `SSID_STR`, `BSSID`, `CHANNEL`, `RSSI`, `NOISE`, `RATES`, `CAPABILITIES`, `RSN_IE`, `HT_CAPS_IE`, `80211D_IE`, raw `IE` |
| `dhcp.server.leases.get` | `pool` → `data` | `{leases: [{ipAddress, macAddress, hostname, interface, pool, leaseEnds, leaseEndsTime}]}`; `pool` ∈ `all active free expired abandoned backup` |

Samples (identifiers replaced):

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

`acp.getStaticConfig` returns the serial and calibration data; `wifi.scan.results` returns
neighbours' networks.

## Action

Does something; stores no setting.

| RPC | Handler |
|---|---|
| `acpd.checkConnection` | HTTP GET `http://apsu.apple.com/version.xml` (update check; outbound request) |
| `acpd.clearLog` | truncates `/var/log/ACPd.log` and `.1`–`.3` |
| `syslogd.flush` | discards the in-memory syslog buffer |
| `acpd.update.phys` | calls a PHY-refresh hook if installed |
| `acpd.busyLoopControl` | `cmd: start` spawns `/sbin/busyloop` (CPU load), `stop` kills it |
| `btmm.rpc` | `action: start\|stop` Back to My Mac |
| `wifi.diagnostic.mode` | `action: start\|stop` → internal events 10 / 11 |
| `wifi.scan.request` | scans only when `ctim == 0` (setup mode); otherwise a no-op returning 0 |
| `wifi.scan.request.<if>` | that interface's hostapd scans |
| `wifi.rotate.gtk.<if>` | rotates the group key |
| `pppoe.test-client.check-connection` | `serviceName`, `userName`, `password` → `result`: spawns `pppoectl` + `ifwatchd` |
| `remoteBonjour.browse` | `serviceType`, `domain` (default `local.`) → `uuid` |
| `acp.injectPacket` | `packetInfo`: raw frame to `/dev/bpf` (Ethernet or 802.11) |
| `user.checkFileSharingAccess` | `flags`, `user`, `pass` → `access`, `info` (file-sharing users, `usrd`) |
| `wsc.start`, `wsc.stop`, `wsc.authorize` | WPS window; authorize a client by MAC + PIN (flags 0x1) |
| `dhcp.client.lease.action`, `dhcp.client.interface.state`, `dhcp6.client.lease.action`, `dhcp6.client.interface.state` | ACPd → dhclient: renew/release, interface up/down |
| `mdns.btmm.clearAllUsers`, `icloud.newcastle.bag`, `icloud.mdns.badsig`, `icloud.cached.lhbag` | BTMM / iCloud housekeeping (handlers not read) |

## Event

Notifications a helper daemon sends into ACPd; calling one injects a fake event. Most queue
the dict for the Wi-Fi or DHCP state machine (`FUN_00674f64`).

`wifi.ap.status`, `wifi.sta.status`, `wifi.sta.event`, `wifi.legacy.wds.status`,
`wifi.legacy.wds.link`, `wifi.dynamic.wds.extender.status`, `wifi.proxysta.status`,
`wifi.dwds.sta.join`, `wifi.dwds.sta.leave`, `wifi.proxy.sta.discovery`,
`wifi.proxy.sta.idle`, `wifi.scan.complete`, `wifi.wps.credentials`,
`wsc.internal.join{Requested,Abandoned,Succeeded,Failed,Expired}`, `wsc.internal.data`,
`dhcp.client.lease.{accept,reject,release}`, `dhcp6.client.lease.address-delete`,
`dhcp6.client.lease.prefix-delegation`.

Immediate effects: `dhcp6.client.lease.address-delete` runs
`ifconfig <wan> inet6 <addr> -alias`; `wsc.internal.joinSucceeded` hands a PSK to the WPS
state machine.

## Write

| RPC | Effect |
|---|---|
| `acp.setStaticConfig` | sets factory nvram variables (serial, MAC, calibration); gate `FUN_0067f05c`. **Can brick the unit; never call** |
| `wifi.diagnostic.caldata` | `action: read\|write`, `interface`, `path`: radio calibration to/from a file |
| `acpd.setDirtyPlist` | `drTY`, `allowMinimal`: applies a configuration change set (AirPort Utility's "Update") |
| `acpd.parseDirtyPlist` | `drTY` → `result` (`"minimal"` / `"restart"` / `"reboot"`), `interruptions`. Same worker as `setDirtyPlist` (`FUN_00658a18`) with the apply flag 0, so likely a dry run; helpers `FUN_0067e484`, `FUN_0067f5fc` and the `drTY` format unread. Not called |
| `acp.setDynamicStoreValue` | `key`, `value`: writes the `DynS` store, posts a change event |
| `wifi.channel.announce` | `interface`, `channel`: switches the radio and stores `WiFi.radios[n].raCh` |
| `wifi.antenna.config.set` | stub |
| `wifi.{channel,mcs,tx.rate,mcast.rate,debug,ampdu}.set.<if>` | runtime hostapd settings (`mcast.rate.set` also takes `type`) |
| `wifi.tal.add_update.<if>`, `wifi.tal.remove.<if>` | `talEntry` dict |
| `wifi.neighbor.set.<if>` | 802.11k neighbour report: `action`, `channel`, `operatingclass`, `bssidinfo`, `phytype`, `mac` |
| `wsc.internal.{start,stop,preauthorize,authorize,denied}.<if>` | ACPd → hostapd WPS control |
| `mdns.btmm.user` | `name`, `secret`: BTMM credentials |
| `icloud.mdns.lhbag` | `lhBagData` |
| `cloud.update.<service>` | `changes` → `changes`, `commitUUID`: iCloud-pushed config, one per service UUID |

Unused: the generic `<group>.sysctl` registrar `FUN_00671808` has no callers (would expose
debug variables via `group` / `name` / `action`, `=`-prefixed action writes).

## Registration encoding

`FUN_006717dc(name, flags, handler, <schema...>)` (ACPd) and `FUN_0080b058` (remote) take
the same arguments. The schema is a NULL-name-terminated varargs list; `FUN_00671404` turns
it into `{flags: <int>, params: [{name, type, defaultType, input}, ...]}`. Variable stride:

```c
name = w[0];  if (name == NULL) end_of_list;
type = w[1];                       /* non-zero */
input = w[2];                      /* input vs output parameter */
if (input == 0)            stride = 3;
else {
    defaultType = w[3];
    stride = (defaultType == 0 || defaultType == 0x10) ? 4 : 5;  /* w[4] = default value */
}
```

Names are inline CoreFoundation constant strings (`isa == 0x56070000`, text at `+8`).
Regenerate with [`ghidra_scripts/RpcMap.java`](../ghidra_scripts/README.md):
`RpcMap.java 0x6717dc` (ACPd's own), `RpcMap.java 0x80b058` (other daemons; hostapd names are
built at run time and show as `?`).

## Type codes

| Code | Type | Seen in |
|---|---|---|
| 1 | bool | `allowMinimal` |
| 2 | int or data | `interruptions`, `lhBagData` |
| 3 | data | `mac`, `psk` (WPS); `bss_info`, `ies` |
| 5 | dictionary | `data`, `credentials`, `variables`, `drTY` |
| 7 | string (`CFString` in the handler) | `output` replies |
| 9 | number | `defaultType` switch in `FUN_00671404` |
| 10 | string (C `char *` in the handler) | `cmd`, `interface`, `pool` |
| 12 | IPv4 address | `ipv4` (DHCPv4), `address` (DHCPv6) |
| 13 | MAC address | 6 bytes |
| 14 | session handle | `__acpSession` only |
| 15 | any | `acp.setDynamicStoreValue` `value` |
