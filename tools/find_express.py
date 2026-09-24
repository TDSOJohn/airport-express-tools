#!/usr/bin/env python3
"""Find the AirPort Express on the local LAN once it's a Wi-Fi client (no longer 10.0.1.1).

Sweeps the given IPv4 /24, reads the ARP table for Apple's 20:c9:d0 MAC prefix (the Express's
Ethernet/radio OUI), and confirms each candidate by reading its ACP syNm. Also tries Avahi
(_airport._tcp) if avahi-browse is present. Prints the Express's IP and name, or times out.

usage: find_express.py [--net 192.168.1] [--timeout 180] [--password PW|@FILE]
"""
import argparse
import concurrent.futures
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import sys
import time

# Make the airportctl package importable from tools/ (and from a checkout's parent folder).
_here = os.path.dirname(os.path.abspath(__file__))
for _d in (_here, os.path.dirname(_here)):
    if os.path.isdir(os.path.join(_d, 'airportctl')):
        sys.path.insert(0, _d)
        break

import airportctl.acp as acp  # noqa: E402

OUI = ('20:c9:d0',)  # Apple AirPort; the Express's waMA/raMA start here


def ping(ip):
    subprocess.run(['ping', '-c1', '-W1', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def arp_apple():
    out = subprocess.run(['ip', 'neigh'], capture_output=True, text=True).stdout
    hits = []
    for line in out.splitlines():
        m = re.match(r'(\d+\.\d+\.\d+\.\d+).*lladdr ([0-9a-f:]{17})', line)
        if m and m.group(2).lower().startswith(OUI):
            hits.append(m.group(1))
    return hits


def avahi():
    if not shutil.which('avahi-browse'):
        return []
    out = subprocess.run(['avahi-browse', '-rptk', '_airport._tcp'],
                         capture_output=True, text=True, timeout=15).stdout
    return [f.split(';')[7] for f in out.splitlines()
            if f.startswith('=') and len(f.split(';')) > 8 and ':' not in f.split(';')[7]]


def confirms(ip, password):
    try:
        name = acp.get_raw(ip, password, 'syNm', timeout=3).rstrip(b'\0').decode('utf-8', 'replace')
        return name
    except (OSError, RuntimeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--net', default='192.168.1')
    ap.add_argument('--timeout', type=int, default=180)
    ap.add_argument('--password', default=acp.default_password(),
                    help='admin password or @FILE (default: as airportctl -p)')
    a = ap.parse_args()
    password = acp.read_password(a.password)
    deadline = time.time() + a.timeout
    seen = set()
    print(f'searching {a.net}.0/24 for an Apple {OUI[0]}* host answering ACP...', flush=True)
    while time.time() < deadline:
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            ex.map(ping, [f'{a.net}.{i}' for i in range(1, 255)])
        candidates = list(dict.fromkeys(avahi() + arp_apple()))
        for ip in candidates:
            if ip in seen:
                continue
            seen.add(ip)
            name = confirms(ip, password)
            if name:
                print(f'FOUND  {ip}  ACP syNm={name!r}', flush=True)
                return 0
            print(f'  {ip}: Apple host but no ACP answer yet', flush=True)
        print(f'  ...not up yet ({int(deadline - time.time())}s left)', flush=True)
    print('TIMED OUT - Express did not appear on the LAN', flush=True)
    return 1


if __name__ == '__main__':
    sys.exit(main())
