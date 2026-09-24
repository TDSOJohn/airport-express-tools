"""WiFi-blob model: load (with a roundtrip safety guard), per-radio edits, and safe write.

The live Wi-Fi config is the `WiFi` property: a CFL blob {'radios': [ {<fourcc>: value}, ... ]}.
Verified field mapping (see ../docs/wifi-blob.md):
  raNm  SSID (str, 1-32 bytes)          raWM  security mode int (see props.SECURITY_RAWM)
  raWE  key bytes -> hostapd wpa_psk    raCl  hidden/closed network (bool)
  raEA  802.1X/EAP (bool; False = PSK)  raCr  passphrase string (display-only; not needed)
For WPA/WPA2, raWE is the 32-byte PMK the device copies verbatim into wpa_psk.
"""
import datetime
import hashlib
import os
import sys

from . import acp, cfl, props

def _default_backup_dir():
    """backups/ next to the package in a source checkout (including an editable install);
    otherwise a per-user state directory, so an installed copy doesn't write into site-packages.
    realpath keeps the answer the same however the package was reached (e.g. via a symlink)."""
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if os.path.isfile(os.path.join(root, 'pyproject.toml')):
        return os.path.join(root, 'backups')
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state')
    return os.path.join(base, 'airportctl', 'backups')


# Override with AIRPORTCTL_BACKUP_DIR.
BACKUP_DIR = os.environ.get('AIRPORTCTL_BACKUP_DIR') or _default_backup_dir()


def load(host, password):
    """Fetch + parse the WiFi blob. Refuse if it doesn't re-encode byte-identically, so we
    never write back a blob our codec would have subtly changed."""
    raw = acp.get_raw(host, password, 'WiFi')
    wifi = cfl.parse(raw)
    if cfl.compose(wifi) != raw:
        raise RuntimeError('refusing to proceed: current WiFi blob does not re-encode '
                           'byte-identically (codec gap) - inspect before writing')
    return wifi, raw


def radios(wifi):
    rs = wifi.get('radios')
    if not rs:
        raise RuntimeError('WiFi blob has no radios')
    return rs


def pmk(password, ssid):
    """WPA/WPA2 PMK = PBKDF2-HMAC-SHA1(password, ssid, 4096, 32). Confirmed on-device: the base
    station stores this in raWE and writes it verbatim into hostapd wpa_psk."""
    return hashlib.pbkdf2_hmac('sha1', password.encode('ascii'), ssid.encode('utf-8'), 4096, 32)


def _wep_key(key):
    if key is None:
        raise ValueError('WEP needs a hex key (10 hex = 40-bit, 26 hex = 104-bit)')
    h = key.lower().replace(':', '').replace(' ', '')
    try:
        b = bytes.fromhex(h)
    except ValueError:
        raise ValueError('WEP key must be hex (10, 26, or 32 hex digits)')
    if len(b) not in (5, 13, 16):
        raise ValueError('WEP key must be 5/13/16 bytes (10/26/32 hex digits)')
    return b


def set_ssid(radio, name):
    if not 1 <= len(name.encode('utf-8')) <= 32:
        raise ValueError('SSID must be 1-32 bytes')
    radio['raNm'] = name


def set_hidden(radio, on):
    radio['raCl'] = bool(on)


def secure(radio, mode, secret=None):
    """Apply a security mode to one radio dict. `secret` is the Wi-Fi password (WPA family)
    or a hex WEP key; ignored for 'open'."""
    radio['raEA'] = False           # PSK, never EAP
    radio.pop('raCr', None)         # passphrase field is display-only; keep it out
    if mode == 'open':
        radio['raWM'] = 0
        radio.pop('raWE', None)
        return
    if mode == 'wep':
        radio['raWM'] = props.SECURITY_RAWM['wep']
        radio['raWE'] = _wep_key(secret)
        return
    if mode in props.WPA_MODES:
        if not (secret and 8 <= len(secret) <= 63 and secret.isascii() and secret.isprintable()):
            raise ValueError('WPA/WPA2 password must be 8-63 printable ASCII characters')
        radio['raWM'] = props.SECURITY_RAWM[mode]
        radio['raWE'] = pmk(secret, radio['raNm'])
        return
    raise ValueError(f'unknown security mode: {mode}')


def set_station(radio, mode):
    """Set the radio role: 'create' (AP), 'join' (client/STA), or 'off'. Accepts an int too."""
    radio['raSt'] = props.STATION_MODES[mode] if isinstance(mode, str) else int(mode)


def join(radio, ssid, secret, mode='wpa2', psta=False):
    """Turn one radio into a wireless client of an existing network (raSt=1). Sets the target
    SSID (raNm), security (raWM) and the SSID-salted PMK (raWE), with EAP and dynamic-WDS off.
    `psta` (proxy-STA) bridges wired clients onto the joined network; leave off for plain AirPlay."""
    if mode not in props.WPA_MODES and mode != 'open':
        raise ValueError("join security must be one of: open, wpa, wpa2, mixed")
    set_ssid(radio, ssid)               # raNm = the network to join (and the PMK salt)
    radio['raSt'] = props.STATION_MODES['join']
    radio['dWDS'] = False               # not extending (WDS needs an Apple base station)
    radio['pSTA'] = bool(psta)
    secure(radio, mode, secret)         # raWM + raWE(PMK from ssid) + raEA=False


def backup(host, password, note='pre-write'):
    os.makedirs(BACKUP_DIR, mode=0o700, exist_ok=True)   # the blob holds the WPA PMK
    raw = acp.get_raw(host, password, 'WiFi')
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    path = os.path.join(BACKUP_DIR, f'WiFi-{note}-{ts}.cfb')
    with open(path, 'wb') as f:
        f.write(raw)
    return path


def restore(host, password, path, do_backup=True):
    """Write a raw .cfb blob (as produced by backup()) straight back to the device.

    The file must parse as a CFL blob with a radios array, so a truncated or wrong file is
    refused before anything is sent."""
    with open(path, 'rb') as f:
        raw = f.read()
    blob = cfl.parse(raw)          # refuses malformed files
    radios(blob)                   # ...and files that are not a WiFi blob
    if do_backup:
        print(f'  backup of the CURRENT config: {backup(host, password, note="pre-restore")}')
    fails = acp.set_props(host, password, [('WiFi', raw)])
    if fails:
        raise RuntimeError('device rejected the restore: '
                           + ', '.join(f'{n}=0x{c:08x}' for n, c in fails))
    if acp.get_raw(host, password, 'WiFi') == raw:
        print('  restore verified (read-back byte-identical)')
    else:
        print('  WARNING: read-back differs from the file - inspect with `wifi show`')
    return blob


def write(host, password, wifi, do_backup=True):
    """Back up the current blob, write the new one, and read it back to confirm."""
    if do_backup:
        print(f'  backup: {backup(host, password)}')
    fails = acp.set_props(host, password, [('WiFi', cfl.compose(wifi))])
    if fails:
        raise RuntimeError('device rejected the write: '
                           + ', '.join(f'{n}=0x{c:08x}' for n, c in fails))
    readback = cfl.parse(acp.get_raw(host, password, 'WiFi'))
    if readback == wifi:
        print('  write verified (read-back identical)')
    else:
        print('  WARNING: read-back blob differs from what was written - inspect with `wifi show`')
    return readback


def summarize(wifi):
    out = []
    for i, r in enumerate(radios(wifi)):
        out.append(
            f'radio {i}: ssid={r.get("raNm")!r}  security={props.rawm_label(r.get("raWM"))}'
            f'{"  +key" if "raWE" in r else ""}'
            f'  channel={r.get("raCh")}  hidden={bool(r.get("raCl"))}'
            f'  phymode={r.get("raMd")}  country={r.get("country")}')
    return '\n'.join(out)
