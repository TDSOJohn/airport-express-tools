"""argparse CLI for airportctl. See `python3 -m airportctl -h`."""
import argparse
import datetime
import json
import pprint
import struct
import sys

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
    secret = args.wifi_password
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
    secret = args.secret
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
    secret = args.wifi_password
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
    lines.append('!! EXPERIMENTAL: this is the firmware\'s own client mode. On 7.8.1 its '
                 'wpa_supplicant crashes at startup, so after the reboot the radio does not '
                 'connect, and the other radio is switched off. `airportctl join` works instead '
                 '(our own supplicant, over SSH). To undo this, restore the backup printed below.')
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
        new = args.new
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
        for name in sorted(rpcmod.ALL_RPCS):
            mark = ' ' if name in rpcmod.READ_ONLY else '*'
            print(f'{mark} {rpcmod.describe(name)}')
        print('\n* = not verified read-only: may act or change state. `.<if>` = one per '
              'interface (e.g. wlan1). See docs/rpc-surface.md.')
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
    key, _ = rpcmod.lookup(args.name)
    if key not in rpcmod.READ_ONLY and not args.force:
        raise SystemExit('refusing: this RPC is not verified read-only and may change the base '
                         "station's state. Re-run with --force if that is what you want.")
    if key in rpcmod.READ_ONLY:
        inputs = {**rpcmod.default_inputs(args.name), **inputs}
    print(f'calling with inputs={inputs!r}')
    if args.dry_run:
        print('dry run, nothing sent')
        return
    print(pprint.pformat(acp.rpc(args.host, args.password, args.name, inputs)))


DEVICE_PROPS = ['syNm', 'syAP', 'syVs', 'syUT']
REPORT_URL = 'https://github.com/TDSOJohn/airport-express-tools/issues/new?template=device-report.yml'


def read_device(host, password):
    """syNm/syAP/syVs/syUT as a dict; properties the device doesn't return are left out."""
    err, got = acp.get_props(host, password, DEVICE_PROPS)
    if err:
        hint = ' (wrong admin password)' if err == acp.ERR_WRONG_PASSWORD else ''
        raise RuntimeError(f'getprop failed: ACP error 0x{err:08x}{hint}')
    dev = {}
    for name, flags, data in got:
        if flags & 1:
            continue
        if name in ('syAP', 'syUT'):
            dev[name] = int.from_bytes(data[:4], 'big')
        else:
            dev[name] = data.rstrip(b'\0').decode('utf-8', 'replace')
    return dev


def is_tested(dev):
    return (dev.get('syAP'), dev.get('syVs')) in props.TESTED


def cmd_info(args):
    dev = read_device(args.host, args.password)
    ap = dev.get('syAP')
    print(f"name:     {dev.get('syNm', '?')}")
    print(f"model:    syAP={ap if ap is not None else '?'}  ({props.product_label(ap)})")
    print(f"firmware: syVs={dev.get('syVs', '?')}")
    if 'syUT' in dev:
        print(f"uptime:   {datetime.timedelta(seconds=dev['syUT'])}")
    if is_tested(dev):
        print('status:   tested - everything in the README applies')
    else:
        print('status:   NOT tested - reads are safe; check `wifi show` and `mode show` make sense\n'
              '          before writing, and keep the backups. Please report what works:\n'
              f'          {REPORT_URL}')


def warn_if_untested(args):
    """Before a write: print a warning on an untested model/firmware. Never blocks."""
    try:
        dev = read_device(args.host, args.password)
    except (RuntimeError, ValueError, OSError):
        return  # the command itself will report the real problem
    if not is_tested(dev):
        print(f"!! untested device: syAP={dev.get('syAP')} ({props.product_label(dev.get('syAP'))}), "
              f"firmware {dev.get('syVs')}. airportctl was verified on syAP=115 / 7.8.1 only.\n"
              '   Every Wi-Fi write is backed up first; see "If something goes wrong" in the README.',
              file=sys.stderr)


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
              '   `python3 tools/find_express.py` or run a DHCP server on that cable before rebooting it.')
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


def cmd_join_install(args):
    from . import join
    join.install(args.host, args.password, args.ssid, args.wifi_password, args.ip, args.gateway,
                 netmask=args.netmask, fallback_ip=args.fallback_ip, start_now=not args.no_start,
                 dry_run=args.dry_run)


def cmd_join_start(args):
    from . import join
    join.start(args.host, args.password)


def cmd_join_status(args):
    from . import join
    print(join.describe(join.status(args.host, args.password)))


def cmd_join_remove(args):
    from . import join
    join.remove(args.host, args.password)


def cmd_ui(args):
    from . import ui
    ui.serve(args.host, args.password, port=args.port, open_browser=not args.no_browser)


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
    sp.set_defaults(func=cmd_wifi_ssid, writes=True)

    sp = wsub.add_parser('secure', help='set security (raWM + raWE)')
    sp.add_argument('mode', choices=['open', 'wep', 'wpa', 'wpa2', 'mixed'])
    sp.add_argument('secret', nargs='?',
                    help='Wi-Fi password (WPA family; @FILE ok) or hex key (wep); omit for open')
    _add_write_flags(sp)
    sp.set_defaults(func=cmd_wifi_secure, writes=True)

    sp = wsub.add_parser('join', help="EXPERIMENTAL: the firmware's own client mode (raSt=1); "
                                      "doesn't connect on 7.8.1, use `airportctl join`")
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
    sp.set_defaults(func=cmd_wifi_join, radio=None, writes=True)

    sp = wsub.add_parser('hidden', help='hide/show the SSID (raCl)')
    sp.add_argument('state', choices=['on', 'off'])
    _add_write_flags(sp)
    sp.set_defaults(func=cmd_wifi_hidden, writes=True)

    join_p = sub.add_parser('join', help='join a Wi-Fi network with our own wpa_supplicant (needs '
                                         'the debug SSH login; see docs/autorun.md)')
    jsub = join_p.add_subparsers(dest='jcmd', required=True)
    sp = jsub.add_parser('install', help='put the supplicant and the network on /mnt/Flash, '
                                         'then join (2.4 GHz; 5 GHz stays up)')
    sp.add_argument('ssid', help='the WPA2 network to join')
    sp.add_argument('--wifi-password', required=True, metavar='PW|@FILE',
                    help='its password; only the derived PMK is sent to the Express')
    sp.add_argument('--ip', default='dhcp', help="`dhcp` (default: ask the router), or a fixed "
                                                 "address outside the router's DHCP pool")
    sp.add_argument('--fallback-ip', metavar='IP', help='with DHCP: a fixed address to use when '
                                                        'no DHCP server answers')
    sp.add_argument('--gateway', help="the router's address, for a fixed --ip or --fallback-ip")
    sp.add_argument('--netmask', default='255.255.255.0',
                    help='for a fixed --ip or --fallback-ip (default 255.255.255.0)')
    sp.add_argument('--no-start', action='store_true', help='install only; `join start` later')
    sp.add_argument('--dry-run', action='store_true', help='show what would be written')
    sp.set_defaults(func=cmd_join_install, writes=True)
    sp = jsub.add_parser('start', help='join now (needed after every reboot on stock firmware)')
    sp.set_defaults(func=cmd_join_start)
    sp = jsub.add_parser('status', help='what is installed and how the last join went')
    sp.set_defaults(func=cmd_join_status)
    sp = jsub.add_parser('remove', help='delete everything `join install` put on /mnt/Flash')
    sp.set_defaults(func=cmd_join_remove)

    sp = sub.add_parser('led', help='front status LED (LEDc): show, or set auto/amber/green')
    sp.add_argument('state', nargs='?', metavar='auto|amber|green|show|N',
                    help='set the LED (auto=0, amber=1, green=2, or a raw 0-3 value); '
                         'omit or "show" to read it. Live, no reboot.')
    sp.set_defaults(func=cmd_led, writes=True)

    sp = sub.add_parser('name', help='set the base station name (syNm)')
    sp.add_argument('name')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_name, writes=True)

    sp = wsub.add_parser('backup', help=f'save the live WiFi blob to {wifimod.BACKUP_DIR}')
    sp.add_argument('--note', default='manual', help='label used in the file name')
    sp.set_defaults(func=cmd_wifi_backup)

    sp = wsub.add_parser('restore', help='write a saved WiFi blob back (recovery path)')
    sp.add_argument('file', help='a .cfb file from `wifi backup` or an auto-backup')
    sp.add_argument('--dry-run', action='store_true', help='decode the file, write nothing')
    sp.add_argument('--reboot', action='store_true', help='reboot to apply after writing')
    sp.add_argument('--no-backup', action='store_true',
                    help='skip backing up the config being replaced')
    sp.set_defaults(func=cmd_wifi_restore, writes=True)

    mode_p = sub.add_parser('mode', help='device role / connection sharing (the join gate)')
    msub = mode_p.add_subparsers(dest='mcmd', required=True)

    sp = msub.add_parser('show', help='decode the join gate: ctim, waCV, sharing props, role')
    sp.set_defaults(func=cmd_mode_show)

    sp = msub.add_parser('ctim', help='set the configuration timestamp (unblocks client/join mode)')
    sp.add_argument('value', nargs='?', metavar='now|N',
                    help='unix time to store (default: now). Any non-zero value opens the gate.')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_mode_ctim, writes=True)

    sp = msub.add_parser('sharing', help='connection sharing: nat | dhcp | bridge (raNA/raDS/raWB)')
    sp.add_argument('choice', choices=sorted(modemod.SHARING))
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_mode_sharing, writes=True)

    sp = msub.add_parser('wan', help='waCV WAN-uplink bit: wired | wireless | show')
    sp.add_argument('kind', choices=['wired', 'wireless', 'show'])
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_mode_wan, writes=True)

    sp = sub.add_parser('rpc', help='call an ACP RPC, or --list the known ones')
    sp.add_argument('name', nargs='?', help='RPC name, e.g. acpd.system.show')
    sp.add_argument('--list', action='store_true', help='print the statically mapped RPC surface')
    sp.add_argument('--json', metavar='JSON', help='inputs as a JSON object; a "hex:.." string '
                                                   'value is sent as raw bytes')
    sp.add_argument('--force', action='store_true', help='allow RPCs not verified read-only')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_rpc)

    sp = sub.add_parser('admin-password', help='change the admin password (syPW; also the debug SSH login)')
    sp.add_argument('new', nargs='?', metavar='PW|@FILE',
                    help='new password, or @FILE (first line); omit to be prompted')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_admin_password, writes=True)

    sp = sub.add_parser('info', help='model, firmware and whether this combination is tested')
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser('reboot', help='reboot the base station')
    sp.set_defaults(func=cmd_reboot)

    sp = sub.add_parser('ui', help='open a local web page for the everyday commands')
    sp.add_argument('--port', type=int, default=0, help='local port (default: a free one)')
    sp.add_argument('--no-browser', action='store_true', help='print the URL, do not open it')
    sp.set_defaults(func=cmd_ui)
    return p


def run(args):
    """Run a parsed command, warning first if it is a real write to an untested device.
    Secrets must already be resolved (see main); `airportctl ui` calls this directly."""
    # `led` and `mode wan` also have read-only forms
    reading = getattr(args, 'state', 'x') in (None, 'show') or getattr(args, 'kind', None) == 'show'
    if getattr(args, 'writes', False) and not getattr(args, 'dry_run', False) and not reading:
        warn_if_untested(args)
    args.func(args)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        # @FILE is a command-line convenience, so it is resolved here and not in the commands:
        # the UI passes typed values straight through, where a leading @ is just a character.
        args.password = acp.read_password(args.password)
        for name in ('wifi_password', 'secret', 'new'):
            if getattr(args, name, None):
                setattr(args, name, acp.read_password(getattr(args, name)))
        run(args)
    except (RuntimeError, ValueError, OSError) as e:
        raise SystemExit(f'error: {e}')


if __name__ == '__main__':
    main()
