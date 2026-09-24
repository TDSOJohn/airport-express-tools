#!/usr/bin/env python3
"""Browse Bonjour services on one interface with legacy-unicast mDNS queries.

Queries go to ff02::fb (IPv6 link-local) and, if the interface has an IPv4 address, 224.0.0.251.
Sending from an ephemeral port makes responders answer unicast, so this works alongside avahi-daemon.

usage: mdns_probe.py IFACE
"""
import select
import socket
import struct
import subprocess
import sys
import time

from pcap_summary import fmt_dns

NAMES = ['_services._dns-sd._udp.local', '_airport._tcp.local', '_acp-sync._tcp.local']


def query(name, qid, qtype=12):
    q = b''.join(bytes([len(label)]) + label.encode() for label in name.split('.')) + b'\x00'
    return struct.pack('!6H', qid, 0, 1, 0, 0, 0) + q + struct.pack('!HH', qtype, 1)


def main(iface):
    socks = []
    idx = socket.if_nametoindex(iface)
    s6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, idx)
    s6.bind(('::', 0, 0, idx))
    socks.append((s6, ('ff02::fb', 5353, 0, idx)))

    out = subprocess.run(['ip', '-4', '-o', 'addr', 'show', 'dev', iface], capture_output=True, text=True).stdout
    if out.split():
        local4 = out.split()[3].split('/')[0]
        s4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s4.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local4))
        s4.bind((local4, 0))
        socks.append((s4, ('224.0.0.251', 5353)))
        print(f'IPv4 on {iface}: {local4}')
    else:
        print(f'no IPv4 on {iface}, IPv6 link-local only')

    for i, name in enumerate(NAMES):
        for s, dst in socks:
            s.sendto(query(name, 0x4100 + i), dst)

    deadline = time.time() + 4
    seen = set()
    while time.time() < deadline:
        ready, _, _ = select.select([s for s, _ in socks], [], [], max(0, deadline - time.time()))
        for s in ready:
            data, src = s.recvfrom(9000)
            if (src[0], data) in seen:
                continue
            seen.add((src[0], data))
            print(f'reply from {src[0]}: {fmt_dns(data)}')
    if not seen:
        print('no mDNS replies')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
