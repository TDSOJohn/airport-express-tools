# The ACP RPC surface of ACPd 7.8.1

ACP exposes two things: ~520 **properties** (`getprop`/`setprop`, opcodes 0x14/0x15) and
**RPCs** (opcode 0x19), which carry a CFL plist `{function: <name>, inputs: {...}}` and
return `{status: ..., outputs: {...}}`. The RPCs are the richer interface — they are what
AirPort Utility drives for anything that isn't a flat setting — and they are not documented
anywhere. This is all 56 of them, recovered statically.

> **Untested.** Every line below was read out of the binary; none of these calls has been
> made against a live base station yet. Treat the type decoding as a hypothesis.

Regenerate with `ghidra_scripts/RpcMap.java` (see [extracting-acpd.md](extracting-acpd.md)):

```sh
analyzeHeadless ... -postScript RpcMap.java 0x6717dc rpc_map.txt
```

Call one with `airportctl rpc <name> [--json '{"k": v}']`, or list them offline with
`airportctl rpc --list`. A `"hex:aabbcc"` JSON value is sent as raw bytes, for `data`/`mac`
parameters.

## How a registration is encoded

`FUN_006717dc(name, flags, handler, <schema...>)` is the registrar; the schema is a varargs
list terminated by a NULL name. `FUN_00671404` turns it into the plist
`{flags: <int>, params: [{name, type, defaultType, input}, ...]}`, and the per-entry stride
is **variable**, which is the thing to get right when reading these call sites:

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
`flags` is 0 for everything except the WPS and file-sharing calls, which use 1.

## Type codes

The `defaultType` switch in `FUN_00671404` confirms **8 = boolean** and **9 = number**
(`CFNumber` create), and cases 2/3/5 construct string/data/dictionary objects. The rest is
inferred from parameter names and is marked as such:

| code | reading | confidence |
|---|---|---|
| 1 | bool | inferred (`allowMinimal`) |
| 2 | int | inferred (`interruptions`) |
| 3 | data | inferred (`mac`, `psk` in the WPS calls) |
| 5 | dictionary | strong — `data`, `credentials`, `variables`, `changes`, `drTY` |
| 7 | string | strong — `user`, `pass`, `ssid`, `uuid`, `output` |
| 9 | number | **confirmed** by the `defaultType` switch |
| 10 | string | strong — `interface`, `cmd`, `action`, `domain` |
| 12 | address | inferred — `ipv4` (DHCPv4), `address` (DHCPv6) |
| 13 | MAC address | strong — `macAddr`, `mac` |
| 14 | session handle | inferred — only ever `__acpSession` |
| 15 | any | inferred — only `acp.setDynamicStoreValue`'s `value` |

**Open question:** 7 and 10 both look like strings. Resolving it means finding where the
dispatcher validates an incoming `inputs` dict against `type` — start at `FUN_006712c4`,
the other half of the registrar. That is the one loose end in this map.

## The calls

`→` marks an **output**; everything else is an input. `=dN` is a default value of type N.

### FUN_00692688 — raw packet injection

| RPC | parameters | handler |
|---|---|---|
| `acp.injectPacket` | `packetInfo`:dict | `00692744` |

### FUN_0065117c — iCloud / Back-to-My-Mac sync (name built at run time: `cloud.update.` + service)

| RPC | parameters | handler |
|---|---|---|
| `cloud.update.<service>` | `__acpSession`:session, `__rpcName`:string, `changes`:dict, `changes`:dict →, `commitUUID`:string → | `00651f80` |

### FUN_0068b0c8 — Wi-Fi subsystem (the same function that loads the `WiFi` blob and calls the VAP loader)

| RPC | parameters | handler |
|---|---|---|
| `wifi.ap.status` | `data`:dict | `00686f74` |
| `wifi.sta.event` | `macAddr`:mac, `eventName`:string | `0x67f3f8` |
| `wifi.sta.status` | `data`:dict | `00686f10` |
| `wifi.legacy.wds.status` | `data`:dict | `00686ec8` |
| `wifi.legacy.wds.link` | `data`:dict | `00686e80` |
| `wifi.dwds.sta.join` | `interface`:string, `mac`:mac | `00686cec` |
| `wifi.dwds.sta.leave` | `interface`:string, `mac`:mac | `00686c2c` |
| `wifi.dynamic.wds.extender.status` | `data`:dict | `00686e1c` |
| `wifi.channel.announce` | `interface`:string, `channel`:number | `00687aa8` |
| `wifi.proxy.sta.discovery` | `interface`:string, `mac`:mac, `ifdiscovery`:string | `00686b10` |
| `wifi.proxy.sta.idle` | `interface`:string, `mac`:mac, `ifdiscovery`:string | `006869f4` |
| `wifi.proxysta.status` | `data`:dict | `00686db8` |
| `wifi.antenna.config.get` | `index`:number, `rxant`:number →, `txant`:number → | `00686954` |
| `wifi.antenna.config.set` | `index`:number, `rxant`:number, `txant`:number | `006868b4` |
| `wifi.chain.noise.get` | `index`:number, `data`:dict → | `00686828` |
| `wifi.interface.stats.get` | `data`:dict → | `006867e8` |
| `wifi.scan.complete` | `interface`:string | `00686704` |
| `wifi.scan.request` | — | `00686698` |
| `wifi.wps.credentials` | `interface`:string, `credentials`:dict | `00686384` |

### FUN_0065cbfc — DHCPv4 client

| RPC | parameters | handler |
|---|---|---|
| `dhcp.client.lease.reject` | `data`:dict | `0065cf38` |
| `dhcp.client.lease.accept` | `ipv4`:address | `0065c538` |
| `dhcp.client.lease.release` | `action`:string | `0065ced4` |

### FUN_0065746c — daemon init — the general ACPd control surface

| RPC | parameters | handler |
|---|---|---|
| `acpd.system.show` | `output`:string → | `0065a684` |
| `acpd.system.interfaces` | `data`:dict → | `0065a4bc` |
| `wifi.diagnostic.mode` | `action`:string | `0065898c` |
| `wifi.diagnostic.caldata` | `action`:string, `interface`:string, `path`:string | `00659438` |
| `acpd.update.phys` | — | `0065a484` |
| `acpd.parseDirtyPlist` | `drTY`:dict, `result`:string →, `interruptions`:int → | `0065909c` |
| `acpd.setDirtyPlist` | `drTY`:dict, `allowMinimal`:bool | `0065a288` |
| `acpd.clearLog` | — | `00656958` |
| `acpd.busyLoopControl` | `cmd`:string | `00654934` |
| `btmm.rpc` | `action`:string | `00653cf4` |

### FUN_00664820 — DHCPv6 client

| RPC | parameters | handler |
|---|---|---|
| `dhcp6.client.lease.address-delete` | `address`:string | `006643a4` |
| `dhcp6.client.lease.prefix-delegation` | `address`:address, `length`:number, `validTime`:number, `preferredTime`:number | `0x664468` |

### FUN_0064c5e8 — PPPoE test client

| RPC | parameters | handler |
|---|---|---|
| `pppoe.test-client.check-connection` | — | `0064c79c` |

### FUN_0067be70 — connectivity check

| RPC | parameters | handler |
|---|---|---|
| `acpd.checkConnection` | — | `0067c0d0` |

### FUN_0066ca20 — acpmon

| RPC | parameters | handler |
|---|---|---|
| `acpmon.show` | — | `0066be70` |

### FUN_00670150 — remote Bonjour browsing

| RPC | parameters | handler |
|---|---|---|
| `remoteBonjour.browse` | `__acpSession`:session, `serviceType`:string, `domain`:string =d16, `uuid`:string → | `006701f0` |

### FUN_00672ab4 — the RPC subsystem itself

| RPC | parameters | handler |
|---|---|---|
| `acprpc.show` | `cmd`:string, `output`:string → | `00670918` |

### FUN_00679f4c — static config / dynamic store

| RPC | parameters | handler |
|---|---|---|
| `acp.getStaticConfig` | `variables`:dict =d5, `variables`:dict → | `0067a2c4` |
| `acp.setStaticConfig` | `variables`:dict | `0067a158` |
| `acp.setDynamicStoreValue` | `key`:string, `value`:any | `0067a054` |

### FUN_0067dce4 — file-sharing user check

| RPC | parameters | handler |
|---|---|---|
| `user.checkFileSharingAccess` | `flags`:number, `user`:string, `pass`:string, `access`:number →, `info`:dict → | `0067ddc4` |

### FUN_0068d6dc — WPS / Wi-Fi Simple Config

| RPC | parameters | handler |
|---|---|---|
| `wsc.start` | `mode`:number, `timeout`:number =d9, `flags`:number =d9, `ttl`:number =d9 | `0x68e728` |
| `wsc.stop` | `flags`:number =d9 | `0068e5ac` |
| `wsc.authorize` | `mac`:data, `name`:string, `pin`:string, `ttl`:number =d9 | `0068e3b8` |
| `wsc.internal.joinRequested` | `mac`:mac, `name`:string, `flags`:number, `interface`:string, `ssid`:string | `0068e10c` |
| `wsc.internal.joinAbandoned` | `mac`:mac, `interface`:string | `0068e078` |
| `wsc.internal.joinSucceeded` | `mac`:mac, `psk`:data, `interface`:string, `ssid`:string | `0068dfa4` |
| `wsc.internal.joinFailed` | `mac`:mac, `reason`:number, `interface`:string | `0068def8` |
| `wsc.internal.joinExpired` | `mac`:mac, `interface`:string | `0068dc00` |
| `wsc.internal.data` | — | `0068dbb0` |

### FUN_006933b4 — syslogd

| RPC | parameters | handler |
|---|---|---|
| `syslogd.flush` | — | `0069361c` |

### FUN_00671808 — generic `<group>.show` registrar — how `acprpc.show`, `acpmon.show` and `acpd.system.show` exist

| RPC | parameters | handler |
|---|---|---|
| `<group>.show` | `group`:string, `name`:string, `action`:string, `output`:string → | `00670cf0` |

## Where to start

Eight of these take no inputs at all, so calling them cannot change configuration:

* `acp.getStaticConfig`
* `acpd.checkConnection`
* `acpd.system.interfaces`
* `acpd.system.show`
* `acpmon.show`
* `acprpc.show`
* `wifi.interface.stats.get`
* `wifi.scan.request`

`acpd.system.show` and `acpmon.show` are the obvious first probes — they exist to print
state. `wifi.scan.request` is the interesting one for [join mode](join-mode.md): it makes
the base station scan for networks, and it refuses to run while `ctim == 0`, the same gate
that blocks client mode. `wifi.scan.complete` then carries the results.

`acpd.setDirtyPlist` is the apply path AirPort Utility uses for a whole configuration at
once, and `acpd.parseDirtyPlist` is its dry run — that pairing is worth understanding
before writing anything through it, since it is also how `ctim` gets set in Apple's flow.

