#!/usr/bin/env python3
"""Summarize a libpcap (Ethernet) capture without tshark: ARP, DHCP, mDNS, ICMP/ICMPv6, TCP/UDP.

Capture without root via the wireshark group, e.g.:
  dumpcap -q -i enp5s0 -a duration:30 -F pcap -w capture.pcap

usage: pcap_summary.py FILE.pcap
"""
import collections
import ipaddress
import struct
import sys


def mac(b):
    return ':'.join(f'{x:02x}' for x in b)


def ip4(b):
    return '.'.join(str(x) for x in b)


def ip6(b):
    return str(ipaddress.IPv6Address(bytes(b)))


def dns_records(payload):
    out = []

    def readname(off):
        labels, end, hops = [], None, 0
        while off < len(payload) and hops < 20:
            l = payload[off]
            if l == 0:
                off += 1
                break
            if l & 0xC0 == 0xC0:
                if end is None:
                    end = off + 2
                off = struct.unpack('!H', payload[off:off + 2])[0] & 0x3FFF
                hops += 1
                continue
            labels.append(payload[off + 1:off + 1 + l].decode('utf-8', 'replace'))
            off += 1 + l
        return '.'.join(labels), (end if end is not None else off)

    try:
        qd, an, ns, ar = struct.unpack('!4H', payload[4:12])
        off = 12
        for _ in range(qd):
            n, off = readname(off)
            off += 4
            out.append(('Q', n, None))
        for _ in range(an + ns + ar):
            n, off = readname(off)
            rtype, _rclass, _ttl, rdlen = struct.unpack('!HHIH', payload[off:off + 10])
            off += 10
            rd = off
            extra = None
            if rtype == 12:
                extra, _ = readname(rd)
            elif rtype == 1 and rdlen == 4:
                extra = ip4(payload[rd:rd + 4])
            elif rtype == 28 and rdlen == 16:
                extra = ip6(payload[rd:rd + 16])
            elif rtype == 33:
                port = struct.unpack('!H', payload[rd + 4:rd + 6])[0]
                tgt, _ = readname(rd + 6)
                extra = f'{tgt}:{port}'
            elif rtype == 16:
                txt, p = [], rd
                while p < rd + rdlen:
                    l = payload[p]
                    txt.append(payload[p + 1:p + 1 + l].decode('utf-8', 'replace'))
                    p += 1 + l
                extra = ' | '.join(txt)
            out.append((rtype, n, extra))
            off = rd + rdlen
    except Exception as e:  # truncated / odd packets
        out.append(('ERR', str(e), None))
    return out


def fmt_dns(pl):
    names = {1: 'A', 12: 'PTR', 16: 'TXT', 28: 'AAAA', 33: 'SRV'}
    parts = []
    for kind, name, extra in dns_records(pl):
        if kind == 'Q':
            parts.append(f'Q? {name}')
        elif kind == 'ERR':
            parts.append(f'(parse err {name})')
        elif kind != 47:  # skip NSEC
            parts.append(f'{names.get(kind, kind)} {name}' + (f' -> {extra}' if extra else ''))
    return '; '.join(parts)


def dhcp(pl):
    if len(pl) < 240:
        return 'DHCP (short)'
    opts, i = {}, 240
    while i < len(pl):
        c = pl[i]
        if c == 255:
            break
        if c == 0:
            i += 1
            continue
        l = pl[i + 1]
        opts[c] = pl[i + 2:i + 2 + l]
        i += 2 + l
    mt = {1: 'DISCOVER', 2: 'OFFER', 3: 'REQUEST', 4: 'DECLINE', 5: 'ACK', 6: 'NAK',
          7: 'RELEASE', 8: 'INFORM'}.get(opts.get(53, b'\x00')[0], '?')
    s = f'DHCP {mt} client={mac(pl[28:34])}'
    if pl[16:20] != b'\x00\x00\x00\x00':
        s += f' yiaddr={ip4(pl[16:20])}'
    if 12 in opts:
        s += f' hostname={opts[12].decode(errors="replace")}'
    if 60 in opts:
        s += f' vendor={opts[60].decode(errors="replace")}'
    if 54 in opts:
        s += f' server={ip4(opts[54])}'
    if 1 in opts:
        s += f' mask={ip4(opts[1])}'
    if 3 in opts:
        s += f' router={ip4(opts[3][:4])}'
    return s


def summarize(p):
    head = f'{mac(p[6:12])} > {mac(p[0:6])}'
    et = struct.unpack('!H', p[12:14])[0]
    body = p[14:]
    if et < 0x0600:
        return f'{head} 802.3/LLC len {et} dsap 0x{body[0]:02x}'
    if et == 0x0806:
        op = struct.unpack('!H', body[6:8])[0]
        sha, spa, tpa = body[8:14], body[14:18], body[24:28]
        if op == 1:
            return f'{head} ARP who-has {ip4(tpa)} tell {ip4(spa)} ({mac(sha)})'
        return f'{head} ARP reply {ip4(spa)} is-at {mac(sha)}'
    if et == 0x0800:
        ihl = (body[0] & 0x0F) * 4
        proto, s, d = body[9], ip4(body[12:16]), ip4(body[16:20])
        l4 = body[ihl:]
        if proto == 17:
            sp, dp = struct.unpack('!HH', l4[0:4])
            desc = f'{head} IPv4 {s}:{sp} > {d}:{dp} UDP'
            if {sp, dp} & {67, 68}:
                desc += ' ' + dhcp(l4[8:])
            elif 5353 in (sp, dp):
                desc += ' mDNS ' + fmt_dns(l4[8:])
            return desc
        if proto == 6:
            sp, dp = struct.unpack('!HH', l4[0:4])
            return f'{head} IPv4 {s}:{sp} > {d}:{dp} TCP flags 0x{l4[13]:02x}'
        if proto == 1:
            return f'{head} IPv4 {s} > {d} ICMP type {l4[0]}'
        if proto == 2:
            return f'{head} IPv4 {s} > {d} IGMP'
        return f'{head} IPv4 {s} > {d} proto {proto}'
    if et == 0x86DD:
        nh, s, d = body[6], ip6(body[8:24]), ip6(body[24:40])
        l4 = body[40:]
        if nh == 0:  # hop-by-hop header (MLD)
            nh, l4 = l4[0], l4[(l4[1] + 1) * 8:]
        if nh == 58:
            names = {128: 'echo req', 129: 'echo reply', 130: 'MLD query', 131: 'MLD report',
                     133: 'RS', 134: 'RA', 135: 'NS', 136: 'NA', 143: 'MLDv2 report'}
            return f'{head} IPv6 {s} > {d} ICMPv6 {names.get(l4[0], l4[0])}'
        if nh in (6, 17):
            sp, dp = struct.unpack('!HH', l4[0:4])
            desc = f'{head} IPv6 [{s}]:{sp} > [{d}]:{dp} {"TCP" if nh == 6 else "UDP"}'
            if nh == 17 and 5353 in (sp, dp):
                desc += ' mDNS ' + fmt_dns(l4[8:])
            return desc
        return f'{head} IPv6 {s} > {d} nh {nh}'
    return f'{head} ethertype 0x{et:04x} len {len(p)}'


def main(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic = data[:4]
    if magic in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1'):
        e = '<'
    elif magic in (b'\xa1\xb2\xc3\xd4', b'\xa1\xb2\x3c\x4d'):
        e = '>'
    else:
        sys.exit(f'not a libpcap file (magic {magic.hex()}); capture with dumpcap -F pcap')
    # nanosecond-resolution pcap files store nanoseconds, not microseconds, in the fraction field
    frac = 1e9 if magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d') else 1e6
    off, frames, macs, t0 = 24, [], collections.Counter(), None
    while off + 16 <= len(data):
        ts, tfrac, incl, _orig = struct.unpack(e + 'IIII', data[off:off + 16])
        off += 16
        pkt = data[off:off + incl]
        off += incl
        t = ts + tfrac / frac
        t0 = t if t0 is None else t0
        try:
            s = summarize(pkt)
        except Exception as ex:
            s = f'{mac(pkt[6:12])} > {mac(pkt[0:6])} (decode error: {ex})'
        frames.append((t - t0, s))
        macs[mac(pkt[6:12])] += 1
    print(f'{len(frames)} frames')
    seen = collections.OrderedDict()
    for t, s in frames:
        if s in seen:
            seen[s][1] += 1
        else:
            seen[s] = [t, 1]
    for s, (t, n) in seen.items():
        print(f'{t:7.2f}s x{n:<3} {s}')
    print('source MACs:', dict(macs))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
