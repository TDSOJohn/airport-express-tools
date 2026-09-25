"""`airportctl ui`: a local web page for the everyday commands.

A browser can't open raw TCP to port 5009, so this is a small stdlib HTTP bridge: it serves
ui.html and a few JSON endpoints. Every change goes through the CLI itself: the page's form
becomes an argv, parsed by cli.build_parser() and run by cli.run(). The choices, the refusals
(join gate, codec guard), the backups and the messages are therefore the CLI's own, and the
log shows the equivalent command line.

Local-only by design:
  * binds 127.0.0.1;
  * rejects any Host header other than 127.0.0.1:PORT / localhost:PORT (DNS rebinding);
  * every /api/ call needs a random per-run token, which the page reads from the URL fragment
    (never sent in a request line or logged). The token travels in a custom header, so a
    cross-site page can't even send the request without a CORS preflight, which is refused.
The admin password stays in this process; no endpoint returns it, or the PMK (raWE).
"""
import contextlib
import datetime
import io
import json
import os
import re
import secrets
import shlex
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, acp, cli, props
from . import mode as modemod
from . import wifi as wifimod

TOKEN_HEADER = 'X-Airportctl-Token'
MAX_BODY = 64 * 1024
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui.html')
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; "
       "frame-ancestors 'none'")

# Wi-Fi and mode changes are stored, then applied by the firmware at the next boot.
NEEDS_REBOOT = {'wifi.ssid', 'wifi.secure', 'wifi.hidden', 'wifi.join', 'wifi.restore',
                'mode.ctim', 'mode.wan'}
# Commands without a --dry-run flag: they run immediately.
NO_DRY_RUN = {'led', 'wifi.backup', 'reboot', 'join.start', 'join.remove'}


def _join_address(p):
    """Address flags for `join install`: DHCP (optionally with a fixed fallback) or fixed."""
    ip, gw = (p.get('ip') or '').strip(), (p.get('gateway') or '').strip()
    if p.get('mode') == 'fixed':
        return [f'--ip={ip}', f'--gateway={gw}']
    return [f'--fallback-ip={ip}', f'--gateway={gw}'] if ip else []


def _radio(p):
    r = p.get('radio')
    return [] if r in (None, '', 'all') else ['--radio', str(int(r))]


def _backup_file(name):
    """A .cfb basename that exists in BACKUP_DIR, as a full path; anything else is refused."""
    if not isinstance(name, str) or os.path.basename(name) != name or not name.endswith('.cfb'):
        raise ValueError('not a backup file name')
    path = os.path.join(wifimod.BACKUP_DIR, name)
    if not os.path.isfile(path):
        raise ValueError(f'no such backup: {name}')
    return path


def _led(p):
    if p.get('state') not in props.LED_MODES:
        raise ValueError(f"led state must be one of {', '.join(props.LED_MODES)}")
    return p['state']


# action -> params -> (subcommand words and options, positionals). Options that take a value
# use the --opt=VALUE form and positionals go after `--`, so a value starting with '-' is
# never read as a flag.
ACTIONS = {
    'name': lambda p: (['name'], [p['name']]),
    'led': lambda p: (['led'], [_led(p)]),
    'wifi.ssid': lambda p: (
        ['wifi', 'ssid', *_radio(p)]
        + ([f"--wifi-password={p['wifi_password']}"] if p.get('wifi_password') else []),
        [p['name']]),
    'wifi.secure': lambda p: (['wifi', 'secure', *_radio(p)],
                              [p['mode']] + ([p['secret']] if p.get('secret') else [])),
    'wifi.hidden': lambda p: (['wifi', 'hidden', *_radio(p)], ['on' if p.get('on') else 'off']),
    'wifi.join': lambda p: (
        ['wifi', 'join', f"--band={p.get('band', '2.4')}", f"--security={p.get('security', 'wpa2')}",
         f"--wifi-password={p.get('wifi_password', '')}"] + (['--psta'] if p.get('psta') else []),
        [p['ssid']]),
    'join.install': lambda p: (
        ['join', 'install', f"--wifi-password={p.get('wifi_password', '')}"] + _join_address(p),
        [p['ssid']]),
    'join.start': lambda p: (['join', 'start'], []),
    'join.remove': lambda p: (['join', 'remove'], []),
    'wifi.backup': lambda p: (['wifi', 'backup', f"--note={p.get('note') or 'manual'}"], []),
    'wifi.restore': lambda p: (['wifi', 'restore'], [_backup_file(p.get('file'))]),
    'mode.ctim': lambda p: (['mode', 'ctim'], ['now']),
    'mode.wan': lambda p: (['mode', 'wan'], ['wired']),
    'reboot': lambda p: (['reboot'], []),
}
SECRET_OPTS = ('--wifi-password=',)


def shown_command(action, argv, params):
    """The equivalent command line, with Wi-Fi passwords and keys masked."""
    out = []
    for a in argv:
        if a.startswith(SECRET_OPTS):
            a = a.split('=', 1)[0] + '=***'
        elif action == 'wifi.secure' and params.get('secret') and a == params['secret']:
            a = '***'
        out.append(a if a.endswith('=***') or a == '***' else shlex.quote(a))
    return 'airportctl ' + ' '.join(out)


class State:
    def __init__(self, host, password):
        self.host = host
        self.password = password
        self.pending_reboot = False
        self.lock = threading.Lock()    # one ACP conversation at a time; also guards stdout capture


def _radio_view(i, r):
    ch = r.get('raCh')
    band = ('5 GHz' if ch > 14 else '2.4 GHz') if isinstance(ch, int) and ch else \
        ('2.4 GHz' if i == 0 else '5 GHz')
    wm = r.get('raWM', 0)
    kind = ('open' if wm == 0 else 'wep' if wm in (1, 2) else 'wpa' if wm == 3 else
            'wpa2' if wm == 5 else 'mixed')
    st = r.get('raSt', 0)
    return {'index': i, 'band': band, 'ssid': r.get('raNm'), 'security': kind,
            'security_label': props.rawm_label(wm), 'has_key': 'raWE' in r, 'channel': ch,
            'hidden': bool(r.get('raCl')), 'station': st, 'station_label': props.station_label(st)}


def status(state):
    """Everything the page shows, read in one go. Sections that fail carry an 'error'."""
    h, pw = state.host, state.password
    out = {'host': h, 'version': __version__, 'pending_reboot': state.pending_reboot,
           'backup_dir': wifimod.BACKUP_DIR}
    try:
        dev = cli.read_device(h, pw)
    except (RuntimeError, ValueError, OSError) as e:
        out['error'] = str(e)
        return out
    out['device'] = {
        'name': dev.get('syNm'), 'product': dev.get('syAP'),
        'model': props.product_label(dev.get('syAP')), 'firmware': dev.get('syVs'),
        'uptime': str(datetime.timedelta(seconds=dev['syUT'])) if 'syUT' in dev else None,
        'tested': cli.is_tested(dev), 'report_url': cli.REPORT_URL}
    try:
        led = int.from_bytes(acp.get_raw(h, pw, 'LEDc'), 'big')
        out['led'] = {'value': led, 'label': props.led_label(led),
                      'state': next((k for k, v in props.LED_MODES.items() if v == led), None)}
    except (RuntimeError, ValueError, OSError) as e:
        out['led'] = {'error': str(e)}
    try:
        wifi, _ = wifimod.load(h, pw)
        out['radios'] = [_radio_view(i, r) for i, r in enumerate(wifimod.radios(wifi))]
    except (RuntimeError, ValueError, OSError) as e:
        out['radios_error'] = str(e)
    try:
        gate, _ = modemod.read_gate(h, pw)
        role, reasons = modemod.join_blocked(gate)
        sharing = next((k for k, t in modemod.SHARING.items()
                        if t == (bool(gate.get('raNA')), bool(gate.get('raDS')),
                                 bool(gate.get('raWB')))), 'custom')
        out['gate'] = {'role': role, 'role_label': modemod.role_label(role), 'sharing': sharing,
                       'ctim': gate.get('ctim'), 'reasons': reasons,
                       'fixes': (['mode.wan'] if role == 6 else [])
                       + ([] if gate.get('ctim') else ['mode.ctim'])}
    except (RuntimeError, ValueError, OSError) as e:
        out['gate'] = {'error': str(e)}
    return out


def backups():
    try:
        names = [n for n in os.listdir(wifimod.BACKUP_DIR) if n.endswith('.cfb')]
    except OSError:
        return []
    out = []
    for n in names:
        st = os.stat(os.path.join(wifimod.BACKUP_DIR, n))
        out.append({'file': n, 'size': st.st_size, 'mtime': int(st.st_mtime),
                    'when': datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')})
    return sorted(out, key=lambda b: -b['mtime'])


def run_action(state, action, params, dry_run):
    """Run one CLI command for the page; returns {ok, command, output, error}."""
    if action not in ACTIONS:
        return {'ok': False, 'error': f'unknown action {action!r}'}
    if not isinstance(params, dict) or not all(
            isinstance(v, (str, bool, int, type(None))) for v in params.values()):
        return {'ok': False, 'error': 'params must be an object of strings, numbers and booleans'}
    try:
        words, positionals = ACTIONS[action](params)
    except (KeyError, ValueError, TypeError) as e:
        return {'ok': False, 'error': f'bad parameters: {e}'}
    dry = dry_run and action not in NO_DRY_RUN
    argv = words + (['--dry-run'] if dry else []) + (['--'] + positionals if positionals else [])
    if not all(isinstance(a, str) for a in argv):
        return {'ok': False, 'error': 'bad parameters: expected text'}
    buf = io.StringIO()
    result = {'command': shown_command(action, argv, params), 'dry_run': dry}
    with state.lock, contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            args = cli.build_parser().parse_args(argv)
            args.host, args.password = state.host, state.password
            cli.run(args)
            result['ok'] = True
        except SystemExit as e:     # a CLI refusal, or argparse rejecting a value
            result['ok'] = False
            result['error'] = e.code if isinstance(e.code, str) else 'invalid value (see output)'
        except (RuntimeError, ValueError, OSError) as e:
            result['ok'] = False
            result['error'] = f'error: {e}'
    result['output'] = buf.getvalue()
    # the pre-write backup a Wi-Fi write just made, so the page can offer to undo it
    m = re.search(r'backup(?: of the CURRENT config)?: (\S+\.cfb)', result['output'])
    if result.get('ok') and not dry and m and os.path.isfile(m.group(1)):
        result['backup_file'] = os.path.basename(m.group(1))
    if result['ok'] and not dry:
        if action in NEEDS_REBOOT:
            state.pending_reboot = True
        elif action == 'reboot':
            state.pending_reboot = False
    return result


def join_status(state):
    """`airportctl join status` for the page. Uses SSH, so it's fetched on its own."""
    from . import join
    with state.lock:
        try:
            st = join.status(state.host, state.password)
            st['text'] = join.describe(st)
            return st
        except (RuntimeError, ValueError, OSError) as e:
            return {'error': str(e)}


def make_handler(state, token, port):
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
    page = open(PAGE, 'rb').read()

    class Handler(BaseHTTPRequestHandler):
        server_version = 'airportctl-ui'
        sys_version = ''

        def log_message(self, fmt, *a):     # quiet; never into a captured command's output
            pass

        def _send(self, code, body, ctype='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', CSP)
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(body)

        def _allowed(self):
            if self.headers.get('Host') not in allowed_hosts:
                self._send(403, {'ok': False, 'error': 'bad Host header'})
                return False
            if self.path.startswith('/api/') and not secrets.compare_digest(
                    self.headers.get(TOKEN_HEADER, ''), token):
                self._send(403, {'ok': False, 'error': 'missing or wrong token: reopen the URL '
                                                       '`airportctl ui` printed'})
                return False
            return True

        def do_GET(self):
            if not self._allowed():
                return
            if self.path == '/':
                self._send(200, page, 'text/html; charset=utf-8')
            elif self.path == '/api/status':
                with state.lock:
                    self._send(200, status(state))
            elif self.path == '/api/join':
                self._send(200, join_status(state))
            elif self.path == '/api/backups':
                self._send(200, {'dir': wifimod.BACKUP_DIR, 'backups': backups()})
            else:
                self._send(404, {'ok': False, 'error': 'not found'})

        def do_POST(self):
            if not self._allowed():
                return
            try:
                n = int(self.headers.get('Content-Length', 0))
                if not 0 < n <= MAX_BODY:
                    raise ValueError('body too large or empty')
                req = json.loads(self.rfile.read(n))
                if not isinstance(req, dict):
                    raise ValueError('expected a JSON object')
            except ValueError as e:
                self._send(400, {'ok': False, 'error': f'bad request: {e}'})
                return
            if self.path == '/api/run':
                self._send(200, run_action(state, req.get('action'), req.get('params') or {},
                                           bool(req.get('dry_run'))))
            elif self.path == '/api/connect':
                host = str(req.get('host') or '').strip()
                if not host:
                    self._send(400, {'ok': False, 'error': 'host is required'})
                    return
                with state.lock:
                    if host != state.host:
                        state.pending_reboot = False
                    state.host = host
                    if req.get('password'):
                        state.password = str(req['password'])
                self._send(200, {'ok': True})
            else:
                self._send(404, {'ok': False, 'error': 'not found'})

    return Handler


def serve(host, password, port=0, open_browser=True):
    token = secrets.token_urlsafe(24)
    state = State(host, password)
    httpd = ThreadingHTTPServer(('127.0.0.1', port), None)
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(state, token, port)
    url = f'http://127.0.0.1:{port}/#{token}'
    print(f'airportctl ui for {host}: {url}\n(local only; Ctrl-C to stop)', file=sys.stderr)
    if open_browser:
        threading.Timer(0.3, webbrowser.open, (url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
