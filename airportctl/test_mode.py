"""Offline check of mode.device_role() against the branches of ACPd's FUN_0065746c.

Run: python3 airportctl/test_mode.py   (no device needed)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from airportctl import mode

cases = [
    # (raNA, raDS, raWB, waUB, waCV, expected, why)
    (1, 1, 0, 0, 0x8300, 1, 'factory default (FUN_0066dd88): NAT+DHCP, wired WAN'),
    (1, 1, 0, 0, 0x8300 | 0x800, 2, 'waCV bit 0x800'),
    (1, 1, 0, 0, 0x10300, 6, 'wireless WAN uplink -> role 6, blocks raSt'),
    (1, 0, 0, 0, 0x10300, 6, 'raNA && !raWB is all that matters for the 1/2/6 branch'),
    (0, 0, 1, 0, 0x8300, 4, 'bridge, waUB clear (FUN_006530b8)'),
    (0, 1, 1, 0, 0x8300, 5, 'dhcp-bridge, waUB clear'),
    (0, 1, 1, 1, 0x8300, 3, 'dhcp-bridge, waUB set (FUN_00653094)'),
    (1, 1, 1, 1, 0x8300, 3, 'all three + waUB (FUN_0065304c)'),
    (0, 0, 1, 1, 0x8300, 4, 'bridge + waUB, no ipv6 tunnel flag'),
    (0, 0, 0, 0, 0x8300, 5, 'nothing set (sanitiser would force raWB=1 first)'),
]
bad = 0
for raNA, raDS, raWB, waUB, waCV, exp, why in cases:
    got = mode.device_role(bool(raNA), bool(raDS), bool(raWB), bool(waUB), waCV)
    ok = got == exp
    bad += not ok
    print(f'{"ok " if ok else "FAIL"} raNA={raNA} raDS={raDS} raWB={raWB} waUB={waUB} '
          f'waCV=0x{waCV:x} -> {got} (want {exp})  {why}')
print(mode.device_role(False, False, True, True, 0x8300, ipv6_tunnel=True), '= bridge+waUB+ipv6 flag (want 3)')
# gate reasoning
for gate, label in [({'raNA':1,'raDS':1,'raWB':0,'waUB':0,'waCV':0x8300,'ctim':None}, 'live unit as last left'),
                    ({'raNA':1,'raDS':1,'raWB':0,'waUB':0,'waCV':0x8300,'ctim':1758300000}, 'after `mode ctim now`'),
                    ({'raNA':1,'raDS':1,'raWB':0,'waUB':0,'waCV':0x18300,'ctim':1758300000}, 'ctim set but waCV wireless')]:
    role, reasons = mode.join_blocked(gate)
    print(f'\n{label}: role={role} blocked={len(reasons)}')
    for r in reasons:
        print('   - ' + r)
sys.exit(1 if bad else 0)
