"""Find the base station when 10.0.1.1 doesn't answer, over IPv6 link-local.

The Express always has an IPv6 link-local address on the cable, whatever its IPv4 state: in
bridge mode with no WAN link it has no usable IPv4 at all and serves no DHCP (seen 2026-09-28),
yet ACP (5009) and SSH still answer at fe80::<EUI-64 of its MAC>%<our interface>. This finds
that address without knowing the MAC: it sends a one-shot mDNS query for `_airport._tcp.local`
(the service every AirPort base station advertises) to ff02::fb on each interface and takes
the source address of each reply. The query comes from an ephemeral port, so mDNSResponder
answers it by unicast straight back to us ("legacy unicast", RFC 6762 § 6.7): no root and no
Avahi/Bonjour needed.

For an Express that joined your Wi-Fi (`airportctl join`) and has a normal IPv4 address there,
tools/find_express.py sweeps the LAN instead.
"""
import select
import socket
import struct
import time

from . import acp

DEFAULT_HOST = '10.0.1.1'
MDNS_GROUP = 'ff02::fb'
MDNS_PORT = 5353
SERVICE = '_airport._tcp.local'
QTYPE_PTR = 12


def _query(name):
    labels = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\0'
    # id 0, flags 0, one question, no answers; then QTYPE PTR, QCLASS IN
    return struct.pack('!6H', 0, 0, 1, 0, 0, 0) + labels + struct.pack('!2H', QTYPE_PTR, 1)


def link_local_candidates(timeout=1.5):
    """[(host, interface)] of every responder advertising _airport._tcp on an IPv6 link, in
    reply order. host is 'fe80::…%ifname', ready for socket.create_connection and ssh."""
    socks = {}
    query = _query(SERVICE)
    for index, name in socket.if_nameindex():
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, index)
            s.sendto(query, (MDNS_GROUP, MDNS_PORT, 0, index))
        except OSError:          # interface down, no IPv6, loopback...
            s.close()
            continue
        socks[s] = name
    found = []
    try:
        end = time.monotonic() + timeout
        while socks and (left := end - time.monotonic()) > 0:
            ready, _, _ = select.select(list(socks), [], [], left)
            for s in ready:
                try:
                    data, src = s.recvfrom(9000)
                except OSError:
                    continue
                addr = src[0].split('%')[0]
                # a reply to our query (QR bit set) that names the service, from a link-local
                if (len(data) > 12 and data[2] & 0x80 and b'\x08_airport' in data
                        and addr.lower().startswith('fe80:')):
                    host = f'{addr}%{socks[s]}'
                    if host not in (h for h, _ in found):
                        found.append((host, socks[s]))
    finally:
        for s in socks:
            s.close()
    return found


def answers(host, timeout=2.0):
    """True if something accepts a TCP connection on the ACP port."""
    try:
        with socket.create_connection((host, acp.ACP_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def find(timeout=1.5):
    """[(host, interface)] of the link-local responders whose ACP port answers."""
    return [(h, i) for h, i in link_local_candidates(timeout) if answers(h)]


def resolve_default(log=None):
    """The address to use when no --host was given: 10.0.1.1 if it answers, else the first
    base station found over IPv6 link-local (reported through log), else 10.0.1.1 anyway so
    the command fails with its usual error."""
    if answers(DEFAULT_HOST):
        return DEFAULT_HOST
    found = find()
    if not found:
        return DEFAULT_HOST
    host, iface = found[0]
    if log:
        others = ''.join(f'\n   also answering: {h}' for h, _ in found[1:])
        log(f'note: {DEFAULT_HOST} is not answering; using the base station found over IPv6 '
            f'link-local on {iface}: {host}{others}')
    return host
