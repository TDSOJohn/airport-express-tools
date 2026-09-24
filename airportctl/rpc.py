"""The ACP RPC surface of ACPd 7.8.1, generated from ghidra_scripts/RpcMap.java.

Each entry: name -> (flags, handler_vma, [(param, type_code, is_output, default_type)]).
Type codes are the firmware's own; TYPE_NAMES is a partly-inferred decoding (see
../docs/rpc-surface.md). Nothing here has been exercised on a live device.
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

# RPCs with no input parameters: calling them cannot change configuration.
READ_ONLY = {
    'acp.getStaticConfig',
    'acpd.checkConnection',
    'acpd.system.interfaces',
    'acpd.system.show',
    'acpmon.show',
    'acprpc.show',
    'wifi.interface.stats.get',
    'wifi.scan.request',
}

RPCS = {
    '<group>.show': (0x0, '0x00670cf0', [('group', 10, False, None), ('name', 10, False, None), ('action', 10, False, None), ('output', 7, True, None)]),
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
    'acpmon.show': (0x0, '0x0066be70', []),
    'acprpc.show': (0x0, '0x00670918', [('cmd', 10, False, None), ('output', 7, True, None)]),
    'btmm.rpc': (0x0, '0x00653cf4', [('action', 10, False, None)]),
    'cloud.update.<service>': (0x0, '0x00651f80', [('__acpSession', 14, False, None), ('__rpcName', 10, False, None), ('changes', 5, False, None), ('changes', 5, True, None), ('commitUUID', 7, True, None)]),
    'dhcp.client.lease.accept': (0x0, '0x0065c538', [('ipv4', 12, False, None)]),
    'dhcp.client.lease.reject': (0x0, '0x0065cf38', [('data', 5, False, None)]),
    'dhcp.client.lease.release': (0x0, '0x0065ced4', [('action', 10, False, None)]),
    'dhcp6.client.lease.address-delete': (0x0, '0x006643a4', [('address', 10, False, None)]),
    'dhcp6.client.lease.prefix-delegation': (0x0, '0x664468', [('address', 12, False, None), ('length', 9, False, None), ('validTime', 9, False, None), ('preferredTime', 9, False, None)]),
    'pppoe.test-client.check-connection': (0x0, '0x0064c79c', []),
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


def describe(name):
    """One-line signature, e.g. wifi.antenna.config.get(index:number) -> rxant, txant."""
    e = RPCS.get(name)
    if not e:
        return None
    _flags, _handler, params = e
    ins = [f"{p[0]}:{TYPE_NAMES.get(p[1], p[1])}" for p in params if not p[2]]
    outs = [p[0] for p in params if p[2]]
    sig = name + '(' + ', '.join(ins) + ')'
    return sig + (' -> ' + ', '.join(outs) if outs else '')

