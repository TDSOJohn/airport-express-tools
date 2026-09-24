"""argparse CLI for airportctl. See `python3 -m airportctl -h`."""
import argparse
import datetime
import json
import pprint
import struct

from . import acp, mode as modemod, props, rpc as rpcmod
from . import wifi as wifimod


def _select(wifi, radio):
    rs = wifimod.radios(wifi)
    if radio is None:
        return list(range(len(rs)))
    if not 0 <= radio < len(rs):
        raise SystemExit(f'--radio {radio} out of range (0..{len(rs) - 1})')
    return [radio]


def _commit(args, wifi, summary):
    print(summary)
    if args.dry_run:
        print('dry run, nothing written')
        return
    wifimod.write(args.host, args.password, wifi, do_backup=not args.no_backup)
    if args.reboot:
        print('rebooting to apply...')
        acp.reboot(args.host, args.password)
        print('reboot requested')
    else:
        print(f'note: a reboot is required to apply  ->  python3 -m airportctl --host {args.host} reboot')


def cmd_wifi_show(args):
    wifi, _ = wifimod.load(args.host, args.password)
    print(wifimod.summarize(wifi))


def cmd_wifi_ssid(args):
    secret = acp.read_password(args.wifi_password) if args.wifi_password else None
    wifi, _ = wifimod.load(args.host, args.password)
    lines = []
    for i in _select(wifi, args.radio):
        r = wifimod.radios(wifi)[i]
        old = r.get('raNm')
        wifimod.set_ssid(r, args.name)
        line = f'radio {i}: ssid {old!r} -> {args.name!r}'
        # A WPA PMK (raWE) is derived from the SSID, so renaming invalidates it.
        if r.get('raWM') in props.WPA_RAWM_VALUES and 'raWE' in r:
            if secret:
                wifimod.secure(r, {3: 'wpa', 5: 'wpa2'}.get(r['raWM'], 'mixed'), secret)
                line += '  (re-derived WPA PMK for the new SSID)'
            else:
                line += ('  !! WPA PMK still bound to the OLD SSID - clients will fail; '
                         're-run `wifi secure ...` or pass --wifi-password')
        lines.append(line)
    _commit(args, wifi, '\n'.join(lines))


def cmd_wifi_secure(args):
    secret = acp.read_password(args.secret) if args.secret else None
    wifi, _ = wifimod.load(args.host, args.password)
    lines = []
    for i in _select(wifi, args.radio):
        r = wifimod.radios(wifi)[i]
        old = props.rawm_label(r.get('raWM'))
        wifimod.secure(r, args.mode, secret)
        extra = f'  (PMK from ssid {r.get("raNm")!r})' if args.mode in props.WPA_MODES else ''
        lines.append(f'radio {i}: security {old} -> {props.rawm_label(r.get("raWM"))}{extra}')
    _commit(args, wifi, '\n'.join(lines))


def cmd_wifi_join(args):
    secret = acp.read_password(args.wifi_password)
    wifi, _ = wifimod.load(args.host, args.password)
    rs = wifimod.radios(wifi)
    join_idx = {'2.4': 0, '5': 1}[args.band]
    if join_idx >= len(rs):
        raise SystemExit(f'--band {args.band} maps to radio {join_idx}, which does not exist')
    lines = []
    try:
        gate, _ = modemod.read_gate(args.host, args.password)
        role, reasons = modemod.join_blocked(gate)
        for r in reasons:
            lines.append('!! the firmware will IGNORE raSt and stay an access point: ' + r)
        if reasons and not (args.force or args.dry_run):
            print('\n'.join(lines))
            raise SystemExit('refusing to write: writing this now would broadcast an AP named '
                             'after the target network (an evil twin). Open the gate first '
                             '(`mode ctim now`), or pass --force / --dry-run.')
    except (RuntimeError, ValueError, OSError) as e:
        lines.append(f'!! could not check the join gate ({e}) - run `mode show` first')
    lines.append(f'!! switching to WIRELESS-CLIENT mode: if the join succeeds the Express leaves '
                 f'10.0.1.1 and takes a DHCP address on {args.ssid!r}; if it fails it keeps its '
                 f'current wired role, so recovery over the cable stays possible either way.')
    for i, r in enumerate(rs):
        if i == join_idx:
            wifimod.join(r, args.ssid, secret, mode=args.security, psta=args.psta)
            lines.append(f'radio {i} ({"2.4" if i == 0 else "5"} GHz): JOIN {args.ssid!r}  '
                         f'{args.security}  raSt=1 pSTA={args.psta} dWDS=False')
        else:
            wifimod.set_station(r, 'off')
            lines.append(f'radio {i}: Wi-Fi OFF (raSt=3)')
    _commit(args, wifi, '\n'.join(lines))


def cmd_wifi_hidden(args):
    on = args.state == 'on'
    wifi, _ = wifimod.load(args.host, args.password)
    lines = []
    for i in _select(wifi, args.radio):
        r = wifimod.radios(wifi)[i]
        lines.append(f'radio {i}: hidden {bool(r.get("raCl"))} -> {on}')
        wifimod.set_hidden(r, on)
    _commit(args, wifi, '\n'.join(lines))


def cmd_wifi_backup(args):
    path = wifimod.backup(args.host, args.password, note=args.note)
    print(f'saved {path}')


def cmd_wifi_restore(args):
    print(f'restoring the WiFi blob from {args.file}')
    if args.dry_run:
        blob = wifimod.cfl.parse(open(args.file, 'rb').read())
        print(wifimod.summarize(blob))
        print('dry run, nothing written')
        return
    wifimod.restore(args.host, args.password, args.file, do_backup=not args.no_backup)
    if args.reboot:
        print('rebooting to apply...')
        acp.reboot(args.host, args.password)
        print('reboot requested')
    else:
        print('note: a reboot is required to apply')


def cmd_name(args):
    old = acp.get_raw(args.host, args.password, 'syNm')
    old_txt = old.rstrip(b'\0').decode('utf-8', 'replace')
    value = args.name.encode('utf-8') + (b'\0' if old.endswith(b'\0') else b'')
    print(f'syNm: {old_txt!r} -> {args.name!r}')
    if args.dry_run:
        print('dry run, nothing written')
        return
    fails = acp.set_props(args.host, args.password, [('syNm', value)])
    if fails:
        raise SystemExit('device rejected syNm: ' + ', '.join(f'{n}=0x{c:08x}' for n, c in fails))
    print('read back:', repr(acp.get_raw(args.host, args.password, 'syNm').rstrip(b'\0').decode('utf-8', 'replace')))


def cmd_admin_password(args):
    """Change the admin password (syPW): ACP auth and, with dbug on, the SSH root login."""
    if args.new:
        new = acp.read_password(args.new)
    else:
        import getpass
        new = getpass.getpass('new admin password: ')
        if getpass.getpass('again: ') != new:
            raise SystemExit('passwords differ, nothing written')
    # ACP keys its header with the first 32 bytes of the password, so longer ones would
    # be truncated on the wire; keep to printable ASCII so ssh askpass and shells agree.
    if not 8 <= len(new) <= 32 or not all(33 <= ord(c) < 127 for c in new):
        raise SystemExit('use 8-32 printable ASCII characters, no spaces')
    if new == args.password:
        raise SystemExit('that is already the password')
    if args.dry_run:
        print('dry run, nothing written')
        return
    fails = acp.set_props(args.host, args.password, [('syPW', new.encode())])
    if fails:
        raise SystemExit('device rejected syPW: ' + ', '.join(f'{n}=0x{c:08x}' for n, c in fails))
    ok_new = acp.get_raw(args.host, new, 'syPW').rstrip(b'\0') == new.encode()
    try:
        acp.get_raw(args.host, args.password, 'syNm')
        old_rejected = False
    except RuntimeError:
        old_rejected = True
    print(f'new password accepted and read back: {ok_new}; old password rejected: {old_rejected}')
    if not ok_new:
        raise SystemExit('read-back with the new password failed: try the old one before rebooting')


def cmd_led(args):
    cur = int.from_bytes(acp.get_raw(args.host, args.password, 'LEDc'), 'big')
    if args.state is None or args.state == 'show':
        print(f'LEDc = {cur}  ({props.led_label(cur)})')
        return
    if args.state in props.LED_MODES:
        val = props.LED_MODES[args.state]
    else:
        try:
            val = int(args.state, 0)
        except ValueError:
            raise SystemExit(f"led: expected one of {', '.join(props.LED_MODES)}, 'show', or a "
                             f"number, got {args.state!r}")
    print(f'LEDc: {cur} ({props.led_label(cur)}) -> {val} ({props.led_label(val)})')
    fails = acp.set_props(args.host, args.password, [('LEDc', struct.pack('>I', val))])
    if fails:
        raise SystemExit('device rejected LEDc: ' + ', '.join(f'{n}=0x{c:08x}' for n, c in fails))
    rb = int.from_bytes(acp.get_raw(args.host, args.password, 'LEDc'), 'big')
    if rb == val:
        print(f'read back: {rb} ({props.led_label(rb)}) - live, no reboot needed')
    else:
        print(f'read back: {rb} ({props.led_label(rb)})  !! value did not stick '
              '(only 0-3 are accepted)')


def cmd_rpc(args):
    if args.list:
        for name in sorted(rpcmod.RPCS):
            mark = ' ' if name in rpcmod.READ_ONLY else '*'
            print(f'{mark} {rpcmod.describe(name)}')
        print('\n* = not read-only: takes inputs and/or changes state. '
              'See docs/rpc-surface.md.')
        return
    if not args.name:
        raise SystemExit('rpc: give an RPC name, or --list')
    inputs = json.loads(args.json) if args.json else {}
    if not isinstance(inputs, dict):
        raise SystemExit('rpc: --json must be a JSON object')
    for k, v in list(inputs.items()):          # "hex:aabbcc" -> raw bytes (data/mac params)
        if isinstance(v, str) and v.startswith('hex:'):
            inputs[k] = bytes.fromhex(v[4:].replace(':', ''))
    known = rpcmod.describe(args.name)
    print(known or f'{args.name}  (not in the static map)')
    if args.name not in rpcmod.READ_ONLY and not args.force:
        raise SystemExit('refusing: this RPC takes input parameters and may change the base '
                         "station's state. Re-run with --force if that is what you want.")
    print(f'calling with inputs={inputs!r}')
    if args.dry_run:
        print('dry run, nothing sent')
        return
    print(pprint.pformat(acp.rpc(args.host, args.password, args.name, inputs)))


def cmd_reboot(args):
    print(f'rebooting {args.host}...')
    acp.reboot(args.host, args.password)
    print('reboot requested')


def cmd_mode_show(args):
    gate, errors = modemod.read_gate(args.host, args.password)
    role, reasons = modemod.join_blocked(gate)

    def fmt(name):
        v = gate.get(name)
        if v is None:
            return f'{name} = <unset>   (device error 0x{errors.get(name, 0):08x})'
        if name in ('raNA', 'raDS', 'raWB', 'waUB'):
            return f'{name} = {bool(v)}'
        if name == 'waCV':
            bits = []
            if v & modemod.WACV_WIRED:
                bits.append('0x8000 wired WAN uplink')
            if v & modemod.WACV_WIRELESS:
                bits.append('0x10000 WIRELESS WAN uplink')
            if v & 0x800:
                bits.append('0x800')
            return f'{name} = 0x{v:08x}   (' + ', '.join(bits or ['no uplink bit']) + ')'
        if name == 'ctim':
            when = datetime.datetime.fromtimestamp(v).isoformat(' ') if v else 'zero'
            return f'{name} = {v}   ({when})'
        return f'{name} = {v}'

    print('stored properties (read at daemon init):')
    for n in modemod.GATE_PROPS:
        print('  ' + fmt(n))
    sharing = next((k for k, t in modemod.SHARING.items()
                    if t == (bool(gate.get('raNA')), bool(gate.get('raDS')), bool(gate.get('raWB')))),
                   'custom')
    print(f'\nconnection sharing = {sharing}')
    print(f'device role (ACPd ctx+0x24) = {role}  ({modemod.role_label(role)})')
    try:
        wifi, _ = wifimod.load(args.host, args.password)
        for i, r in enumerate(wifimod.radios(wifi)):
            print(f'  radio {i}: raSt={r.get("raSt", 0)} '
                  f'({props.station_label(r.get("raSt", 0))})  ssid={r.get("raNm")!r}')
    except (RuntimeError, ValueError, OSError) as e:
        print(f'  (could not read the WiFi blob: {e})')
    print('\njoin gate (FUN_00689ab8: raSt is read only when role != 6 and ctim != 0):')
    if reasons:
        for r in reasons:
            print('  BLOCKED: ' + r)
    else:
        print('  OK - the per-radio raSt in the WiFi blob is honoured; `wifi join` can work.')


def cmd_mode_ctim(args):
    gate, errors = modemod.read_gate(args.host, args.password)
    cur = gate.get('ctim')
    value = modemod.now() if args.value in (None, 'now') else int(args.value, 0)
    print(f'ctim: {cur if cur is not None else "<unset>"} -> {value}')
    if args.dry_run:
        print('dry run, nothing written')
        return
    modemod.set_ctim(args.host, args.password, value)
    gate, errors = modemod.read_gate(args.host, args.password)
    rb = gate.get('ctim')
    if rb == value:
        print(f'read back: {rb}  (stored - a reboot is needed before the Wi-Fi loader re-reads it)')
    else:
        print(f'read back: {rb if rb is not None else "<unset>"}  !! value did not stick')


def cmd_mode_sharing(args):
    gate, _ = modemod.read_gate(args.host, args.password)
    old = (bool(gate.get('raNA')), bool(gate.get('raDS')), bool(gate.get('raWB')))
    new = modemod.SHARING[args.choice]
    print(f'connection sharing: raNA/raDS/raWB {old} -> {new}  ({args.choice})')
    if args.choice != 'nat':
        print('!! in bridge/dhcp mode the Express stops being the DHCP router at 10.0.1.1.\n'
              '   Over the cable it will fall back to a link-local address - find it again with\n'
              '   `python3 find_express.py` or run a DHCP server on enp5s0 before rebooting it.')
    if args.dry_run:
        print('dry run, nothing written')
        return
    modemod.set_sharing(args.host, args.password, args.choice)
    gate, _ = modemod.read_gate(args.host, args.password)
    rb = (bool(gate.get('raNA')), bool(gate.get('raDS')), bool(gate.get('raWB')))
    print(f'read back: {rb}' + ('' if rb == new else '   !! values did not stick'))
    print('a reboot is required to apply')


def cmd_mode_wan(args):
    if args.kind == 'show':
        gate, _ = modemod.read_gate(args.host, args.password)
        v = gate.get('waCV')
        print(f'waCV = 0x{v:08x}' if v is not None else 'waCV = <unset>')
        return
    if args.dry_run:
        gate, _ = modemod.read_gate(args.host, args.password)
        cur = gate.get('waCV') or 0
        bit = modemod.WACV_WIRED if args.kind == 'wired' else modemod.WACV_WIRELESS
        print(f'waCV: 0x{cur:08x} -> 0x{(cur & ~modemod.WACV_UPLINK_MASK) | bit:08x} (dry run)')
        return
    cur, new = modemod.set_wan_uplink(args.host, args.password, args.kind)
    print(f'waCV: 0x{cur:08x} -> 0x{new:08x}  ({args.kind} WAN uplink)')
    gate, _ = modemod.read_gate(args.host, args.password)
    rb = gate.get('waCV')
    print(f'read back: 0x{rb:08x}' + ('' if rb == new else '   !! value did not stick'))
    print('a reboot is required to apply')


def _add_write_flags(sp):
    sp.add_argument('--radio', type=int, metavar='N', help='only this radio index (default: all)')
    sp.add_argument('--dry-run', action='store_true', help='show the change without writing')
    sp.add_argument('--reboot', action='store_true', help='reboot to apply after writing')
    sp.add_argument('--no-backup', action='store_true', help='skip the pre-write blob backup')


def build_parser():
    p = argparse.ArgumentParser(
        prog='airportctl',
        description='Configure a 2nd-gen AirPort Express (A1392) over the ACP admin protocol. '
                    'Use over a trusted direct cable only.')
    p.add_argument('--host', default='10.0.1.1', help='base station IP (default: 10.0.1.1)')
    p.add_argument('-p', '--password', default=acp.default_password(), metavar='PW',
                   help='admin password, or @FILE to read it from a file (default: $AIRPORT_PW, '
                        'else @$AIRPORT_PW_FILE or @~/.config/airport-express/admin-pw if it '
                        'exists, else public)')
    sub = p.add_subparsers(dest='cmd', required=True)

    wifi_p = sub.add_parser('wifi', help='Wi-Fi settings')
    wsub = wifi_p.add_subparsers(dest='wcmd', required=True)

    sp = wsub.add_parser('show', help='decode current WiFi blob per radio')
    sp.set_defaults(func=cmd_wifi_show)

    sp = wsub.add_parser('ssid', help='set the network name (raNm)')
    sp.add_argument('name')
    sp.add_argument('--wifi-password', metavar='PW|@FILE',
                    help='if WPA is set, re-derive the PMK for the new SSID (else it breaks)')
    _add_write_flags(sp)
    sp.set_defaults(func=cmd_wifi_ssid)

    sp = wsub.add_parser('secure', help='set security (raWM + raWE)')
    sp.add_argument('mode', choices=['open', 'wep', 'wpa', 'wpa2', 'mixed'])
    sp.add_argument('secret', nargs='?',
                    help='Wi-Fi password (WPA family; @FILE ok) or hex key (wep); omit for open')
    _add_write_flags(sp)
    sp.set_defaults(func=cmd_wifi_secure)

    sp = wsub.add_parser('join', help='become a wireless client of an existing network (raSt=1)')
    sp.add_argument('ssid', help='the network to join')
    sp.add_argument('--wifi-password', required=True, metavar='PW|@FILE',
                    help='the target network password (@FILE keeps it out of shell history)')
    sp.add_argument('--band', choices=['2.4', '5'], default='2.4',
                    help='which radio joins (2.4=radio0, 5=radio1; default 2.4, more robust)')
    sp.add_argument('--security', choices=['wpa2', 'mixed', 'wpa', 'open'], default='wpa2',
                    help='target network security (default wpa2)')
    sp.add_argument('--psta', action='store_true',
                    help='proxy-STA: bridge wired clients onto the joined network (off by default)')
    sp.add_argument('--force', action='store_true',
                    help='write even if the firmware join gate is closed (see `mode show`)')
    sp.add_argument('--dry-run', action='store_true', help='show the change without writing')
    sp.add_argument('--reboot', action='store_true', help='reboot to apply (required to take effect)')
    sp.add_argument('--no-backup', action='store_true', help='skip the pre-write blob backup')
    sp.set_defaults(func=cmd_wifi_join, radio=None)

    sp = wsub.add_parser('hidden', help='hide/show the SSID (raCl)')
    sp.add_argument('state', choices=['on', 'off'])
    _add_write_flags(sp)
    sp.set_defaults(func=cmd_wifi_hidden)

    sp = sub.add_parser('led', help='front status LED (LEDc): show, or set auto/amber/green')
    sp.add_argument('state', nargs='?', metavar='auto|amber|green|show|N',
                    help='set the LED (auto=0, amber=1, green=2, or a raw 0-3 value); '
                         'omit or "show" to read it. Live, no reboot.')
    sp.set_defaults(func=cmd_led)

    sp = sub.add_parser('name', help='set the base station name (syNm)')
    sp.add_argument('name')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_name)

    sp = wsub.add_parser('backup', help='save the live WiFi blob to backups/')
    sp.add_argument('--note', default='manual', help='label used in the file name')
    sp.set_defaults(func=cmd_wifi_backup)

    sp = wsub.add_parser('restore', help='write a saved WiFi blob back (recovery path)')
    sp.add_argument('file', help='a .cfb file from `wifi backup` or an auto-backup')
    sp.add_argument('--dry-run', action='store_true', help='decode the file, write nothing')
    sp.add_argument('--reboot', action='store_true', help='reboot to apply after writing')
    sp.add_argument('--no-backup', action='store_true',
                    help='skip backing up the config being replaced')
    sp.set_defaults(func=cmd_wifi_restore)

    mode_p = sub.add_parser('mode', help='device role / connection sharing (the join gate)')
    msub = mode_p.add_subparsers(dest='mcmd', required=True)

    sp = msub.add_parser('show', help='decode the join gate: ctim, waCV, sharing props, role')
    sp.set_defaults(func=cmd_mode_show)

    sp = msub.add_parser('ctim', help='set the configuration timestamp (unblocks client/join mode)')
    sp.add_argument('value', nargs='?', metavar='now|N',
                    help='unix time to store (default: now). Any non-zero value opens the gate.')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_mode_ctim)

    sp = msub.add_parser('sharing', help='connection sharing: nat | dhcp | bridge (raNA/raDS/raWB)')
    sp.add_argument('choice', choices=sorted(modemod.SHARING))
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_mode_sharing)

    sp = msub.add_parser('wan', help='waCV WAN-uplink bit: wired | wireless | show')
    sp.add_argument('kind', choices=['wired', 'wireless', 'show'])
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_mode_wan)

    sp = sub.add_parser('rpc', help='call an ACP RPC, or --list the known ones')
    sp.add_argument('name', nargs='?', help='RPC name, e.g. acpd.system.show')
    sp.add_argument('--list', action='store_true', help='print the statically mapped RPC surface')
    sp.add_argument('--json', metavar='JSON', help='inputs as a JSON object; a "hex:.." string '
                                                   'value is sent as raw bytes')
    sp.add_argument('--force', action='store_true', help='allow RPCs that take inputs')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_rpc)

    sp = sub.add_parser('admin-password', help='change the admin password (syPW; also the debug SSH login)')
    sp.add_argument('new', nargs='?', metavar='PW|@FILE',
                    help='new password, or @FILE (first line); omit to be prompted')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_admin_password)

    sp = sub.add_parser('reboot', help='reboot the base station')
    sp.set_defaults(func=cmd_reboot)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.password = acp.read_password(args.password)
    try:
        args.func(args)
    except (RuntimeError, ValueError, OSError) as e:
        raise SystemExit(f'error: {e}')


if __name__ == '__main__':
    main()
