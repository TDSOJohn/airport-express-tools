"""Device role ("airport mode") model: the gate that decides whether the per-radio raSt
(create / join) in the WiFi blob is honoured at all.

Decoded from ACPd (see ../docs/join-mode.md). The VAP loader FUN_00689ab8 only reads
`raSt` out of the WiFi blob when BOTH of these hold:

    device_role != 6        (role = the daemon-context field ctx+0x24)
    ctim        != 0        (ACP property `ctim`, the stored configuration timestamp)

Otherwise it hard-writes raSt=0 and flags the radio as an AP - which is exactly what we saw on
2026-09-15 when `wifi join` produced an evil-twin AP instead of a client.

The role is computed once at daemon init (FUN_0065746c) from five stored properties:

    raNA (bool)   connection sharing: NAT ("share a public IP address")
    raDS (bool)   connection sharing: hand out DHCP leases
    raWB (bool)   connection sharing: off / bridge mode
    waUB (bool)   WAN-port-used-as-bridge flag
    waCV (int)    WAN config bitfield; bit 0x8000 = wired WAN uplink,
                  bit 0x10000 = wireless WAN uplink, bit 0x800 = third uplink flavour

The three raNA/raDS/raWB predicates in the firmware are FUN_00653070/65304c/6530b8/653094;
`nat`/`dhcp`/`bridge` below are the three combinations the factory-default writer
(FUN_0066dd88) and the config sanitiser (FUN_00672c30) produce, i.e. AirPort Utility's three
"Connection Sharing" choices.
"""
import re
import struct
import time

from . import acp

GATE_PROPS = ('ctim', 'waCV', 'raNA', 'raDS', 'raWB', 'waUB')

# raNA, raDS, raWB for each "Connection Sharing" choice.
SHARING = {
    'nat':    (True,  True,  False),   # share a public IP address (factory default)
    'dhcp':   (False, True,  True),    # distribute a range of IP addresses, no NAT
    'bridge': (False, False, True),    # off (bridge mode)
}

WACV_WIRED = 0x8000      # WAN uplink is the Ethernet WAN port
WACV_WIRELESS = 0x10000  # WAN uplink is wireless (set at runtime when a radio is STA/WDS)
WACV_UPLINK_MASK = WACV_WIRED | WACV_WIRELESS

ROLE_LABELS = {
    1: 'router/NAT, wired WAN uplink',
    2: 'router/NAT, waCV bit 0x800 uplink',
    3: 'bridge/DHCP with waUB set',
    4: 'bridge',
    5: 'DHCP-only bridge',
    6: 'router/NAT, WIRELESS WAN uplink  << blocks raSt',
}


def role_label(role):
    return ROLE_LABELS.get(role, f'role {role} (unknown)')


def device_role(raNA, raDS, raWB, waUB, waCV, ipv6_tunnel=False):
    """Reproduce FUN_0065746c's ctx+0x24 computation. `ipv6_tunnel` is the ctx flag 0x400 that
    the 6cfg property sets; it only matters for one bridge sub-case (role 3 vs 4)."""
    if raNA and not raWB:                       # FUN_00653070
        if waCV & 0x800:
            return 2
        return 6 if waCV & WACV_WIRELESS else 1
    only_bridge = (not raNA) and (not raDS) and raWB        # FUN_006530b8
    all_three = raNA and raDS and raWB                      # FUN_0065304c
    dhcp_bridge = (not raNA) and raDS and raWB              # FUN_00653094
    if not waUB:
        if only_bridge:
            return 4
        return 4 if all_three else 5
    if dhcp_bridge or all_three:
        return 3
    if only_bridge:
        return 3 if ipv6_tunnel else 4
    return 4 if all_three else 5


def read_gate(host, password):
    """Read the gate properties. Returns {name: int|None}; None means the device reported an
    error for it (for `ctim` that means "no stored value", which is what blocks join)."""
    err, got = acp.get_props(host, password, GATE_PROPS)
    if err:
        hint = ' (wrong admin password)' if err == acp.ERR_WRONG_PASSWORD else ''
        raise RuntimeError(f'getprop failed: ACP error 0x{err:08x}{hint}')
    out = {}
    errors = {}
    for name, flags, raw in got:
        if flags & 1:
            out[name] = None
            errors[name] = int.from_bytes(raw[:4], 'big')
        else:
            out[name] = int.from_bytes(raw, 'big') if raw else 0
    for name in GATE_PROPS:
        out.setdefault(name, None)
    return out, errors


def join_blocked(gate):
    """Return a list of human-readable reasons the loader will ignore raSt (empty = unlocked)."""
    reasons = []
    role = device_role(bool(gate.get('raNA')), bool(gate.get('raDS')), bool(gate.get('raWB')),
                       bool(gate.get('waUB')), gate.get('waCV') or 0)
    if role == 6:
        reasons.append('device role is 6 (router/NAT with a wireless WAN uplink): the loader '
                       'forces create/AP mode. Clear waCV bit 0x10000 -> `mode wan wired`.')
    if not gate.get('ctim'):
        reasons.append('ctim is unset/0 (the base station has never been given a configuration '
                       'timestamp): the loader forces create/AP mode. Fix -> `mode ctim now`.')
    return role, reasons


def sharing_of(gate):
    """The "Connection Sharing" choice the stored raNA/raDS/raWB match, or 'custom'."""
    flags = (bool(gate.get('raNA')), bool(gate.get('raDS')), bool(gate.get('raWB')))
    return next((k for k, t in SHARING.items() if t == flags), 'custom')


# acpd.system.show lists the switch PHYs; index 0 is the WAN port in every mode (in NAT it is
# "linked to interface eth0", in bridge mode the switch maps both ports onto eth1).
_PHY_LINK = re.compile(r'PHY \(0x[0-9A-Fa-f]+\) index (\d+)\s+Link State - Current\s+'
                       r'\(link state ([^)]*)\)')


def phy_links(show_text):
    """{phy index: link text} from acpd.system.show, e.g. {0: 'is Down', 1: '100Mbps Full
    Duplex'}; the text is normalised to single spaces."""
    return {int(i): ' '.join(t.split())
            for i, t in _PHY_LINK.findall(show_text)}


def wan_link(host, password):
    """The WAN port's link as ACPd sees it: e.g. '100Mbps Full Duplex', or None with no link."""
    out = acp.rpc(host, password, 'acpd.system.show')
    links = phy_links((out.get('outputs') or {}).get('output') or '')
    if 0 not in links:
        raise RuntimeError('acpd.system.show has no WAN port (PHY index 0) link state')
    return None if links[0].lower().endswith('down') else links[0]


def uplink_warning(sharing, link):
    """Why the Express is cut off, or None. Outside NAT mode it is not the router at 10.0.1.1
    and relies on the WAN port for its network, so with no WAN link nothing works: in bridge
    mode (seen 2026-09-28) its LAN port and Wi-Fi got no DHCP and it had no working IPv4 address
    itself, only IPv6 link-local."""
    if sharing == 'nat' or link:
        return None
    return (f'connection sharing is {sharing} and the WAN port has no link: the Express is not '
            'the router at 10.0.1.1, so devices on its LAN port and Wi-Fi get no address or '
            'internet, and it has no working IPv4 address itself (airportctl can still reach '
            'it over IPv6 link-local). Plug in the WAN cable, or switch back: '
            '`airportctl mode sharing nat` and reboot.')


def uplink(host, password, gate=None):
    """{'sharing', 'wan_link', 'warning'} for the current state."""
    if gate is None:
        gate, _ = read_gate(host, password)
    sharing = sharing_of(gate)
    link = wan_link(host, password)
    return {'sharing': sharing, 'wan_link': link, 'warning': uplink_warning(sharing, link)}


def set_ctim(host, password, value):
    fails = acp.set_props(host, password, [('ctim', struct.pack('>I', value & 0xFFFFFFFF))])
    if fails:
        raise RuntimeError('device rejected ctim: '
                           + ', '.join(f'{n}=0x{c:08x}' for n, c in fails))


def set_sharing(host, password, choice):
    raNA, raDS, raWB = SHARING[choice]
    fails = acp.set_props(host, password, [('raNA', bytes([raNA])), ('raDS', bytes([raDS])),
                                           ('raWB', bytes([raWB]))])
    if fails:
        raise RuntimeError('device rejected the sharing props: '
                           + ', '.join(f'{n}=0x{c:08x}' for n, c in fails))


def set_wan_uplink(host, password, kind):
    """Force waCV's uplink bit: 'wired' (0x8000) or 'wireless' (0x10000)."""
    gate, _ = read_gate(host, password)
    cur = gate.get('waCV')
    if cur is None:
        raise RuntimeError('waCV has no stored value; refusing to guess a whole WAN config')
    bit = WACV_WIRED if kind == 'wired' else WACV_WIRELESS
    new = (cur & ~WACV_UPLINK_MASK) | bit
    fails = acp.set_props(host, password, [('waCV', struct.pack('>I', new))])
    if fails:
        raise RuntimeError('device rejected waCV: '
                           + ', '.join(f'{n}=0x{c:08x}' for n, c in fails))
    return cur, new


def now():
    return int(time.time())
