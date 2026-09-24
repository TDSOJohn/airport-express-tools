#!/usr/bin/env python3
"""Wait for the AirPort Express to go down and come back after a reboot, then verify Wi-Fi.

The 'airport-probe' NetworkManager profile doesn't autoconnect, so it is re-activated once the
Ethernet link returns. When the ACP port answers again, the Wi-Fi config is read back and Wi-Fi
scans check that every radio (by BSSID) is broadcasting. A 5 GHz radio on a DFS channel can take
a minute or more after boot to appear (radar channel availability check).
"""
import argparse
import os
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

from airportctl import acp, cfl  # noqa: E402


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--host', default='10.0.1.1')
    ap.add_argument('--iface', default='enp5s0')
    ap.add_argument('--profile', default='airport-probe', help='NetworkManager profile on IFACE')
    ap.add_argument('--password', default=os.environ.get('AIRPORT_PASSWORD') or acp.default_password(),
                    help='admin password or @FILE (default: $AIRPORT_PASSWORD, else as airportctl -p)')
    ap.add_argument('--timeout', type=float, default=300, help='seconds to wait for the reboot cycle')
    ap.add_argument('--expect-ssid', help='SSID every radio should broadcast afterwards')
    ap.add_argument('--expect-security', help="text every radio's scan SECURITY column should contain, e.g. WPA2")
    args = ap.parse_args()
    password = acp.read_password(args.password)

    def carrier():
        try:
            with open(f'/sys/class/net/{args.iface}/carrier') as f:
                return f.read().strip() == '1'
        except OSError:
            return False

    def profile_active():
        return args.profile in run('nmcli', '-t', '-f', 'NAME', 'connection', 'show', '--active').splitlines()

    def has_ipv4():
        return bool(run('ip', '-4', '-o', 'addr', 'show', 'dev', args.iface).strip())

    def acp_port_open():
        try:
            with socket.create_connection((args.host, acp.ACP_PORT), timeout=2):
                return True
        except OSError:
            return False

    t0 = time.time()
    last, saw_down, up_since = None, False, None
    while time.time() - t0 < args.timeout:
        c = carrier()
        a = profile_active()
        v4 = a and has_ipv4()
        p = v4 and acp_port_open()
        if (c, a, v4, p) != last:
            print(f'{time.time() - t0:6.1f}s link={c} profile={a} ipv4={v4} acp={p}', flush=True)
            last = (c, a, v4, p)
        if not (c and p):
            saw_down = True
        if c and not a:
            run('nmcli', '--wait', '20', 'connection', 'up', args.profile)
            up_since = time.time()
        elif c and not v4 and up_since and time.time() - up_since > 45:
            print('no DHCP lease after 45s, re-activating profile', flush=True)
            run('nmcli', 'connection', 'down', args.profile)
            up_since = None
        if saw_down and p:
            break
        time.sleep(2)
    else:
        sys.exit('timed out' + ('' if saw_down else ' (the Express never appeared to go down)'))

    print(f'Express back after {time.time() - t0:.0f}s')
    print('internet route:', (run('ip', 'route', 'get', '1.1.1.1').splitlines() or ['(none)'])[0])

    err, props = acp.get_props(args.host, password, ['WiFi'])
    if err or props[0][1] & 1:
        sys.exit(f'reading the WiFi config failed (error 0x{err:08x})')
    radios = cfl.parse(props[0][2])['radios']
    bssids = [':'.join(f'{b:02X}' for b in r['raMA']) for r in radios]
    for radio, bssid in zip(radios, bssids):
        print(f'config: {bssid} raNm={radio["raNm"]!r} raSt={radio["raSt"]} raCh={radio["raCh"]} '
              f'raWM={radio.get("raWM")}')

    def as_expected(bssid):
        line = seen.get(bssid)
        return (line is not None
                and (args.expect_ssid is None or args.expect_ssid in line)
                and (args.expect_security is None or args.expect_security in line))

    seen = {}
    for _ in range(12):
        time.sleep(10)
        lines = run('nmcli', '-f', 'SSID,BSSID,CHAN,SIGNAL,SECURITY', 'dev', 'wifi', 'list', '--rescan', 'yes').splitlines()
        seen.update({b: line for b in bssids for line in lines if b in line})
        if all(as_expected(b) for b in bssids):
            break
    print('Wi-Fi scan:')
    for bssid in bssids:
        print('  ' + seen.get(bssid, f'{bssid}  (not seen)') + ('' if as_expected(bssid) else '   <- not as expected'))


if __name__ == '__main__':
    main()
