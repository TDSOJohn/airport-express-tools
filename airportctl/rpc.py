"""The ACP RPC surface of firmware 7.8.1, generated from ghidra_scripts/RpcMap.java.

Each entry: name -> (flags, handler_vma, [(param, type_code, is_output, default_type)]).
Type codes are the firmware's own; TYPE_NAMES is a partly-inferred decoding (see
../docs/rpc-surface.md). RPCS are registered by ACPd itself (registrar 0x6717dc);
REMOTE_RPCS by other daemons over IPC (registrar 0x80b058, flags 0x2 in `acprpc.show`).
A name ending in `.<if>` is registered once per interface, e.g. wifi.statistics.wlan1.
READ_ONLY was checked against the decompiled handlers and called on an A1392.
"""

TYPE_NAMES = {
    1: 'bool',
    2: 'int',
    3: 'data',
    5: 'dict',
    7: 'string',
    9: 'number',
    10: 'string',
    12: 'address',
    13: 'mac',
    14: 'session',
    15: 'any',
}

# Handlers that only read state (checked in the decompiled code, and called live on an
# A1392 running 7.8.1). Taking no inputs is NOT the test: acpd.clearLog, syslogd.flush and
# acpd.update.phys take none and still act. Values are the default inputs `airportctl rpc`
# fills in; '<if>' is replaced by the interface in the RPC name.
READ_ONLY = {
    'acp.getStaticConfig': {},
    'acpd.system.interfaces': {},
    'acpd.system.show': {},
    'acpmon.show': {'cmd': ''},
    'acprpc.show': {'cmd': ''},
    'dhcp.server.leases.get': {'pool': 'all'},
    'wifi.antenna.config.get': {'index': 0},
    'wifi.chain.noise.get': {'index': 0},
    'wifi.interface.stats.get': {},
    'wifi.channel.get.<if>': {'interface': '<if>'},
    'wifi.mcast.rate.get.<if>': {'interface': '<if>'},
    'wifi.mcs.get.<if>': {'interface': '<if>'},
    'wifi.scan.results.<if>': {'interface': '<if>'},
    'wifi.statistics.<if>': {'interface': '<if>'},
    'wifi.tx.rate.get.<if>': {'interface': '<if>'},
}

RPCS = {
    'acp.getStaticConfig': (0x0, '0x0067a2c4', [('variables', 5, False, 5), ('variables', 5, True, None)]),
    'acp.injectPacket': (0x0, '0x00692744', [('packetInfo', 5, False, None)]),
    'acp.setDynamicStoreValue': (0x0, '0x0067a054', [('key', 7, False, None), ('value', 15, False, None)]),
    'acp.setStaticConfig': (0x0, '0x0067a158', [('variables', 5, False, None)]),
    'acpd.busyLoopControl': (0x0, '0x00654934', [('cmd', 10, False, None)]),
    'acpd.checkConnection': (0x0, '0x0067c0d0', []),
    'acpd.clearLog': (0x0, '0x00656958', []),
    'acpd.parseDirtyPlist': (0x0, '0x0065909c', [('drTY', 5, False, None), ('result', 7, True, None), ('interruptions', 2, True, None)]),
    'acpd.setDirtyPlist': (0x0, '0x0065a288', [('drTY', 5, False, None), ('allowMinimal', 1, False, None)]),
    'acpd.system.interfaces': (0x0, '0x0065a4bc', [('data', 5, True, None)]),
    'acpd.system.show': (0x0, '0x0065a684', [('output', 7, True, None)]),
    'acpd.update.phys': (0x0, '0x0065a484', []),
    'acpmon.show': (0x0, '0x0066be70', [('cmd', 10, False, None), ('output', 7, True, None)]),
    'acprpc.show': (0x0, '0x00670918', [('cmd', 10, False, None), ('output', 7, True, None)]),
    'btmm.rpc': (0x0, '0x00653cf4', [('action', 10, False, None)]),
    'cloud.update.<service>': (0x0, '0x00651f80', [('__acpSession', 14, False, None), ('__rpcName', 10, False, None), ('changes', 5, False, None), ('changes', 5, True, None), ('commitUUID', 7, True, None)]),
    'dhcp.client.lease.accept': (0x0, '0x0065c538', [('ipv4', 12, False, None)]),
    'dhcp.client.lease.reject': (0x0, '0x0065cf38', [('data', 5, False, None)]),
    'dhcp.client.lease.release': (0x0, '0x0065ced4', [('action', 10, False, None)]),
    'dhcp6.client.lease.address-delete': (0x0, '0x006643a4', [('address', 10, False, None)]),
    'dhcp6.client.lease.prefix-delegation': (0x0, '0x664468', [('address', 12, False, None), ('length', 9, False, None), ('validTime', 9, False, None), ('preferredTime', 9, False, None)]),
    'pppoe.test-client.check-connection': (0x0, '0x0064c79c', [('serviceName', 10, False, 16), ('userName', 10, False, 16), ('password', 10, False, 16), ('result', 7, True, None)]),
    'remoteBonjour.browse': (0x0, '0x006701f0', [('__acpSession', 14, False, None), ('serviceType', 10, False, None), ('domain', 10, False, 16), ('uuid', 7, True, None)]),
    'syslogd.flush': (0x0, '0x0069361c', []),
    'user.checkFileSharingAccess': (0x1, '0x0067ddc4', [('flags', 9, False, None), ('user', 7, False, None), ('pass', 7, False, None), ('access', 9, True, None), ('info', 5, True, None)]),
    'wifi.antenna.config.get': (0x0, '0x00686954', [('index', 9, False, None), ('rxant', 9, True, None), ('txant', 9, True, None)]),
    'wifi.antenna.config.set': (0x0, '0x006868b4', [('index', 9, False, None), ('rxant', 9, False, None), ('txant', 9, False, None)]),
    'wifi.ap.status': (0x0, '0x00686f74', [('data', 5, False, None)]),
    'wifi.chain.noise.get': (0x0, '0x00686828', [('index', 9, False, None), ('data', 5, True, None)]),
    'wifi.channel.announce': (0x0, '0x00687aa8', [('interface', 10, False, None), ('channel', 9, False, None)]),
    'wifi.diagnostic.caldata': (0x0, '0x00659438', [('action', 10, False, None), ('interface', 10, False, None), ('path', 10, False, None)]),
    'wifi.diagnostic.mode': (0x0, '0x0065898c', [('action', 10, False, None)]),
    'wifi.dwds.sta.join': (0x0, '0x00686cec', [('interface', 10, False, None), ('mac', 13, False, None)]),
    'wifi.dwds.sta.leave': (0x0, '0x00686c2c', [('interface', 10, False, None), ('mac', 13, False, None)]),
    'wifi.dynamic.wds.extender.status': (0x0, '0x00686e1c', [('data', 5, False, None)]),
    'wifi.interface.stats.get': (0x0, '0x006867e8', [('data', 5, True, None)]),
    'wifi.legacy.wds.link': (0x0, '0x00686e80', [('data', 5, False, None)]),
    'wifi.legacy.wds.status': (0x0, '0x00686ec8', [('data', 5, False, None)]),
    'wifi.proxy.sta.discovery': (0x0, '0x00686b10', [('interface', 10, False, None), ('mac', 13, False, None), ('ifdiscovery', 10, False, None)]),
    'wifi.proxy.sta.idle': (0x0, '0x006869f4', [('interface', 10, False, None), ('mac', 13, False, None), ('ifdiscovery', 10, False, None)]),
    'wifi.proxysta.status': (0x0, '0x00686db8', [('data', 5, False, None)]),
    'wifi.scan.complete': (0x0, '0x00686704', [('interface', 10, False, None)]),
    'wifi.scan.request': (0x0, '0x00686698', []),
    'wifi.sta.event': (0x0, '0x67f3f8', [('macAddr', 13, False, None), ('eventName', 7, False, None)]),
    'wifi.sta.status': (0x0, '0x00686f10', [('data', 5, False, None)]),
    'wifi.wps.credentials': (0x0, '0x00686384', [('interface', 10, False, None), ('credentials', 5, False, None)]),
    'wsc.authorize': (0x1, '0x0068e3b8', [('mac', 3, False, None), ('name', 7, False, None), ('pin', 7, False, None), ('ttl', 9, False, 9)]),
    'wsc.internal.data': (0x0, '0x0068dbb0', []),
    'wsc.internal.joinAbandoned': (0x0, '0x0068e078', [('mac', 13, False, None), ('interface', 7, False, None)]),
    'wsc.internal.joinExpired': (0x0, '0x0068dc00', [('mac', 13, False, None), ('interface', 7, False, None)]),
    'wsc.internal.joinFailed': (0x0, '0x0068def8', [('mac', 13, False, None), ('reason', 9, False, None), ('interface', 7, False, None)]),
    'wsc.internal.joinRequested': (0x0, '0x0068e10c', [('mac', 13, False, None), ('name', 7, False, None), ('flags', 9, False, None), ('interface', 7, False, None), ('ssid', 7, False, None)]),
    'wsc.internal.joinSucceeded': (0x0, '0x0068dfa4', [('mac', 13, False, None), ('psk', 3, False, None), ('interface', 7, False, None), ('ssid', 7, False, None)]),
    'wsc.start': (0x1, '0x68e728', [('mode', 9, False, None), ('timeout', 9, False, 9), ('flags', 9, False, 9), ('ttl', 9, False, 9)]),
    'wsc.stop': (0x1, '0x0068e5ac', [('flags', 9, False, 9)]),
}

# Registered at run time by other daemons (hostapd per interface, dhcpd, dhclient,
# mDNSResponder, iCloudd); see re/rpc_map_remote.txt. Flags are as `acprpc.show` prints them.
REMOTE_RPCS = {
    'dhcp.client.interface.state': (0x2, '0x005556b0', [('state', 10, False, None)]),
    'dhcp.client.lease.action': (0x2, '0x00555624', [('action', 10, False, None)]),
    'dhcp.server.leases.get': (0x2, '0x005205fc', [('pool', 10, False, None), ('data', 5, True, None)]),
    'dhcp6.client.interface.state': (0x2, '0x00555588', [('state', 10, False, None)]),
    'icloud.cached.lhbag': (0x2, '0x005ed874', [('cachedFlag', 9, False, None)]),
    'icloud.mdns.badsig': (0x2, '0x005ed6a0', [('domain', 10, False, None), ('badSigFlag', 9, False, None)]),
    'icloud.mdns.lhbag': (0x2, '0x006b5cec', [('lhBagData', 2, False, None)]),
    'icloud.newcastle.bag': (0x2, '0x005eab68', []),
    'mdns.btmm.clearAllUsers': (0x2, '0x006b6040', []),
    'mdns.btmm.user': (0x2, '0x006b484c', [('name', 10, False, None), ('secret', 10, False, None)]),
    'wifi.ampdu.set.<if>': (0x2, '0x005b521c', [('interface', 10, False, None), ('ampdu', 10, False, None)]),
    'wifi.channel.get.<if>': (0x2, '0x005b57c0', [('interface', 10, False, None), ('channel', 9, True, None)]),
    'wifi.channel.set.<if>': (0x2, '0x005b6764', [('interface', 10, False, None), ('channel', 9, False, None)]),
    'wifi.debug.set.<if>': (0x2, '0x005b5308', [('interface', 10, False, None), ('dbglevel', 9, False, None)]),
    'wifi.mcast.rate.get.<if>': (0x2, '0x005b53c4', [('interface', 10, False, None), ('rate', 9, True, None)]),
    'wifi.mcast.rate.set.<if>': (0x2, '0x005b5434', [('interface', 10, False, None), ('rate', 9, False, None), ('type', 10, False, None)]),
    'wifi.mcs.get.<if>': (0x2, '0x005b56e0', [('interface', 10, False, None), ('mcsindex', 9, True, None)]),
    'wifi.mcs.set.<if>': (0x2, '0x005b5750', [('interface', 10, False, None), ('mcsindex', 9, False, None)]),
    'wifi.neighbor.set.<if>': (0x2, '0x005b5108', [('interface', 10, False, None), ('action', 10, False, None), ('channel', 9, False, None), ('operatingclass', 9, False, None), ('bssidinfo', 9, False, None), ('phytype', 9, False, None), ('mac', 13, False, None)]),
    'wifi.rotate.gtk.<if>': (0x2, '0x005b5eb0', [('interface', 10, False, None)]),
    'wifi.scan.request.<if>': (0x2, '0x005b5344', [('interface', 10, False, None)]),
    'wifi.scan.results.<if>': (0x2, '0x005b6254', [('interface', 10, False, None), ('data', 5, True, None)]),
    'wifi.statistics.<if>': (0x2, '0x005b60cc', [('interface', 10, False, None), ('data', 5, True, None)]),
    'wifi.tal.add_update.<if>': (0x2, '0x005b5a54', [('interface', 10, False, None), ('talEntry', 5, False, 5)]),
    'wifi.tal.remove.<if>': (0x2, '0x005b5830', [('interface', 10, False, None), ('talEntry', 5, False, 5)]),
    'wifi.tx.rate.get.<if>': (0x2, '0x005b5518', [('interface', 10, False, None), ('txrate', 9, True, None)]),
    'wifi.tx.rate.set.<if>': (0x2, '0x005b5588', [('interface', 10, False, None), ('txrate', 9, False, None)]),
    'wsc.internal.authorize.<if>': (0x2, '0x005b5f34', [('interface', 10, False, None), ('mac', 13, False, None), ('pin', 10, False, None), ('ttl', 9, False, None)]),
    'wsc.internal.denied.<if>': (0x2, '0x005b5ef0', [('interface', 10, False, None), ('mac', 13, False, None)]),
    'wsc.internal.preauthorize.<if>': (0x2, '0x005b5f98', [('mac', 13, False, None), ('ttl', 9, False, None)]),
    'wsc.internal.start.<if>': (0x2, '0x005b6084', [('interface', 10, False, None), ('flags', 9, False, None), ('extraInfo', 5, False, 5)]),
    'wsc.internal.stop.<if>': (0x2, '0x005b6048', [('interface', 10, False, None)]),
}
ALL_RPCS = {**RPCS, **REMOTE_RPCS}


def lookup(name):
    """Map a live RPC name to its table key: wifi.statistics.wlan1 -> wifi.statistics.<if>.

    Returns (key, interface-or-None), or (None, None) if the name is not mapped.
    """
    if name in ALL_RPCS:
        return name, None
    head, _, tail = name.rpartition('.')
    if head and f'{head}.<if>' in ALL_RPCS:
        return f'{head}.<if>', tail
    if name.startswith('cloud.update.'):
        return 'cloud.update.<service>', None
    return None, None


def default_inputs(name):
    """The inputs `airportctl rpc` sends to a READ_ONLY RPC when none are given."""
    key, iface = lookup(name)
    return {k: (iface if v == '<if>' else v) for k, v in READ_ONLY.get(key, {}).items()}


def describe(name):
    """One-line signature, e.g. wifi.antenna.config.get(index:number) -> rxant, txant."""
    key, _ = lookup(name)
    e = ALL_RPCS.get(key)
    if not e:
        return None
    _flags, _handler, params = e
    ins = [f"{p[0]}:{TYPE_NAMES.get(p[1], p[1])}" for p in params if not p[2]]
    outs = [p[0] for p in params if p[2]]
    sig = name + '(' + ', '.join(ins) + ')'
    return sig + (' -> ' + ', '.join(outs) if outs else '')

