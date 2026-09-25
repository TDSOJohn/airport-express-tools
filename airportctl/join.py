"""`airportctl join`: make the Express a Wi-Fi client with our own wpa_supplicant, over SSH.

The firmware's own client mode (`wifi join`, raSt=1) can't work on 7.8.1: its supplicant
crashes at startup (docs/join-mode.md). This puts a replacement on the Express's persistent
/mnt/Flash instead and starts it (docs/autorun.md):

    /mnt/Flash/autorun.sh              payload/autorun.sh: the join, the LED, the failsafe
    /mnt/Flash/autorun/wpa_supplicant  payload/wpa_supplicant (prebuilt, see payload/NOTICE.txt)
    /mnt/Flash/autorun/dhcpc           payload/dhcpc (prebuilt from crossdev/src/dhcpc.c)
    /mnt/Flash/autorun/wpa.conf        the network, with the PMK only (never the passphrase)
    /mnt/Flash/autorun/join.conf       IP=dhcp [FALLBACK_IP= GW= MASK=], or a fixed IP= GW= MASK=
    /mnt/Flash/autorun/ssid            the network name, for `status`

The 2.4 GHz radio becomes the client; the 5 GHz network stays up. On stock firmware the join
lasts until the next reboot (`join start` redoes it); with the autorun firmware it is redone
at every boot.

Needs the debug SSH login (dbug=0x3000, see docs/dbug.md), which is a manual prerequisite,
and an `ssh` client on PATH (OpenSSH; tested on Linux). The root password is the admin
password.
"""
import hashlib
import ipaddress
import os
import shlex
import subprocess
import tempfile

from . import wifi as wifimod

F = '/mnt/Flash'
D = F + '/autorun'
PAYLOAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'payload')
KNOWN_HOSTS = os.path.join(os.path.dirname(wifimod.BACKUP_DIR), '.airport_known_hosts')
SPARE_KB = 256          # rc.d/flash reformats /mnt/Flash if it ever fails to mount: keep margin
SSH_OFF = ('no SSH login on {host}. `airportctl join` needs the debug SSH shell: set '
           'dbug=0x3000 and reboot (docs/dbug.md). That is a root shell guarded only by the '
           'admin password, so enable it on purpose.')

# The OpenSSH on the Express is from 2007 (see tools/essh.sh).
SSH_OPTS = ['-o', 'HostKeyAlgorithms=+ssh-rsa',
            '-o', 'KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1,'
                  'diffie-hellman-group-exchange-sha1',
            '-o', 'Ciphers=+aes128-cbc,aes256-cbc,3des-cbc', '-o', 'MACs=+hmac-sha1,hmac-md5',
            '-o', 'StrictHostKeyChecking=accept-new', '-o', 'PubkeyAuthentication=no',
            '-o', 'PreferredAuthentications=password,keyboard-interactive',
            '-o', 'ConnectTimeout=10', '-o', 'LogLevel=ERROR']


def ssh(host, password, command, data=None, timeout=120):
    """Run one shell command on the Express as root; return stdout (bytes if data is bytes).
    The password reaches ssh through a throwaway SSH_ASKPASS helper and the environment."""
    with tempfile.TemporaryDirectory() as tmp:
        askpass = os.path.join(tmp, 'askpass.sh')
        with open(askpass, 'w') as f:
            f.write('#!/bin/sh\nprintf \'%s\\n\' "$AIRPORTCTL_SSH_PW"\n')
        os.chmod(askpass, 0o700)
        env = dict(os.environ, SSH_ASKPASS=askpass, SSH_ASKPASS_REQUIRE='force',
                   DISPLAY=os.environ.get('DISPLAY', 'none'), AIRPORTCTL_SSH_PW=password)
        argv = ['ssh', *SSH_OPTS, '-o', f'UserKnownHostsFile={KNOWN_HOSTS}',
                f'root@{host}', command]
        try:
            r = subprocess.run(argv, input=data, capture_output=True, env=env, timeout=timeout,
                               stdin=None if data is not None else subprocess.DEVNULL)
        except FileNotFoundError:
            raise RuntimeError('no `ssh` client on PATH (OpenSSH is needed for `join`)')
        except subprocess.TimeoutExpired:
            raise RuntimeError(f'SSH command timed out after {timeout} s')
    if r.returncode == 255:
        err = r.stderr.decode(errors='replace').strip()
        if 'refused' in err:
            raise RuntimeError(SSH_OFF.format(host=host))
        if 'timed out' in err or 'No route' in err or 'unreachable' in err:
            raise RuntimeError(f'cannot reach {host} ({err})')
        raise RuntimeError(f'SSH to {host} failed: {err or "exit 255"}')
    if r.returncode != 0:
        raise RuntimeError(f'command on the Express failed ({r.returncode}): '
                           f'{r.stderr.decode(errors="replace").strip()}')
    return r.stdout


def _sh(host, password, command, **kw):
    return ssh(host, password, command, **kw).decode(errors='replace')


def join_conf(ip='dhcp', gateway=None, netmask='255.255.255.0', fallback_ip=None):
    """join.conf for autorun.sh: DHCP (optionally with a fixed fallback address) or a fixed
    address. GW/MASK describe the fixed address, whichever of the two it is."""
    if ip == 'dhcp':
        if not fallback_ip:
            if gateway:
                raise ValueError('--gateway is only for a fixed address (--ip or --fallback-ip)')
            return 'IP=dhcp\n'
        if not gateway:
            raise ValueError('--fallback-ip needs --gateway')
        _check_net(fallback_ip, gateway, netmask)
        return f'IP=dhcp\nFALLBACK_IP={fallback_ip}\nGW={gateway}\nMASK={netmask}\n'
    if fallback_ip:
        raise ValueError('--fallback-ip only goes with DHCP')
    if not gateway:
        raise ValueError('a fixed --ip needs --gateway')
    _check_net(ip, gateway, netmask)
    return f'IP={ip}\nGW={gateway}\nMASK={netmask}\n'


def _check_net(ip, gateway, netmask):
    try:
        net = ipaddress.IPv4Network(f'{ip}/{netmask}', strict=False)
        ipa, gw = ipaddress.IPv4Address(ip), ipaddress.IPv4Address(gateway)
    except ValueError as e:
        raise ValueError(f'bad address: {e}')
    if gw not in net or ipa == gw or ipa in (net.network_address, net.broadcast_address):
        raise ValueError(f'{ip}/{netmask} and gateway {gateway} are not a usable pair')


def wpa_conf(ssid, wifi_password):
    """WPA2-PSK network block with the SSID in hex (no quoting issues) and the PMK only."""
    if not 1 <= len(ssid.encode('utf-8')) <= 32:
        raise ValueError('network name must be 1-32 bytes')
    if not 8 <= len(wifi_password) <= 63 or not wifi_password.isascii():
        raise ValueError('WPA2 password must be 8-63 ASCII characters')
    return (f'ctrl_interface=/var/run/wpa_own\nap_scan=1\nnetwork={{\n'
            f'\tssid={ssid.encode("utf-8").hex()}\n\tkey_mgmt=WPA-PSK\n\tproto=RSN\n'
            f'\tpairwise=CCMP\n\tgroup=CCMP TKIP\n'
            f'\tpsk={wifimod.pmk(wifi_password, ssid).hex()}\n}}\n')


def _payload(name):
    with open(os.path.join(PAYLOAD, name), 'rb') as f:
        return f.read()


def running(host, password):
    """PIDs of our supplicant on the Express (empty if not joined)."""
    out = _sh(host, password, '/bin/ps ax | while read pid rest; do case "$rest" in '
                              f'*{D}/wpa_supplicant*) echo $pid;; esac; done')
    return out.split()


def install(host, password, ssid, wifi_password, ip='dhcp', gateway=None,
            netmask='255.255.255.0', fallback_ip=None, start_now=True, dry_run=False, log=print):
    jconf = join_conf(ip, gateway, netmask, fallback_ip)
    conf = wpa_conf(ssid, wifi_password)
    binaries = {name: _payload(name) for name in ('wpa_supplicant', 'dhcpc')}
    if ip == 'dhcp':
        how = 'with an address from DHCP' + (f' (else {fallback_ip}, netmask {netmask}, gateway '
                                             f'{gateway})' if fallback_ip else '')
    else:
        how = f'as {ip} (netmask {netmask}, gateway {gateway})'
    log(f'join {ssid!r} {how} on the 2.4 GHz radio; the 5 GHz network stays up')
    log(f'to {D}/: ' + ', '.join(f'{n} ({len(b)} B)' for n, b in binaries.items()) +
        f', wpa.conf (PMK only), join.conf, ssid; and {F}/autorun.sh')
    if dry_run:
        log('dry run, nothing written')
        return
    if not _sh(host, password, 'echo ok').startswith('ok'):
        raise RuntimeError('unexpected reply from the Express shell')
    upload = []
    for name, binary in binaries.items():
        have = _sh(host, password, f'[ -f {D}/{name} ] && openssl dgst -sha256 '
                                   f'{D}/{name} || true').strip()
        if have.endswith(hashlib.sha256(binary).hexdigest()):
            log(f'  {name} already there (same SHA-256)')
        else:
            upload.append(name)
    avail = int(_sh(host, password, f'df -k {F}').split('\n')[1].split()[3])
    need = sum(len(binaries[n]) // 1024 for n in upload) + 16 + SPARE_KB
    if avail < need:
        raise RuntimeError(f'only {avail} KB free on {F}, need {need} KB (incl. {SPARE_KB} spare)')
    _sh(host, password, f'mkdir -p {D} && chmod 700 {D}')
    if 'wpa_supplicant' in upload and running(host, password):
        raise RuntimeError('the supplicant is running from Flash; reboot before replacing it')
    for name in upload:
        # temp name then rename, so a running copy is never overwritten in place
        ssh(host, password, f'cat > {D}/{name}.new && chmod 755 {D}/{name}.new '
                            f'&& mv {D}/{name}.new {D}/{name}', data=binaries[name])
        log(f'  {name} uploaded')
    ssh(host, password, f'umask 077; cat > {D}/wpa.conf', data=conf.encode())
    ssh(host, password, f'cat > {D}/join.conf', data=jconf.encode())
    ssh(host, password, f'cat > {D}/ssid', data=ssid.encode('utf-8'))
    ssh(host, password, f'cat > {F}/autorun.sh.new && mv {F}/autorun.sh.new {F}/autorun.sh',
        data=_payload('autorun.sh'))
    log('  config and autorun.sh written')
    if start_now:
        try:
            start(host, password, log=log)
        except RuntimeError as e:   # e.g. already joined: the new config waits for a reboot
            log(f'  not started now: {e}. Stored; `airportctl join start` after the reboot.')


def start(host, password, log=print):
    """Run autorun.sh now, the way the boot hook would. Returns at once; see `status`."""
    if running(host, password) or _sh(host, password, '/sbin/ifconfig wlan2 > /dev/null 2>&1 '
                                                       '&& echo yes || true').strip():
        raise RuntimeError('the Express is already a client (wlan2 exists); reboot to start over')
    if not _sh(host, password, f'[ -f {F}/autorun.sh ] && echo yes || true').strip():
        raise RuntimeError('nothing installed: run `join install` first')
    _sh(host, password, f': > {F}/autorun.try; '
                        f'sh {F}/autorun.sh < /dev/null > /dev/null 2>&1 &')
    log('started: joining takes about 45 s (the LED turns green when it has joined, amber if '
        'it failed); then `airportctl join status`')


def status(host, password):
    """What is installed and what the last run did. Never reads wpa.conf (it holds the PMK)."""
    marks = ('autorun.sh', 'autorun/wpa_supplicant', 'autorun/dhcpc', 'autorun/wpa.conf',
             'autorun.try', 'autorun.off')
    out = _sh(host, password,
              f'cd {F}; for f in {" ".join(marks)}; do [ -e $f ] && echo "has $f"; done; '
              f'echo "--conf"; cat autorun/join.conf 2>/dev/null; '
              f'echo "--ssid"; cat autorun/ssid 2>/dev/null; echo; '
              f'echo "--hook"; case "$(cat /etc/rc)" in *autorun*) echo yes;; esac; '
              f'echo "--lease"; cat /mnt/Memory/lease 2>/dev/null; '
              f'echo "--log"; cat /mnt/Memory/autorun.log 2>/dev/null; true')
    sec, lines = None, {}
    for line in out.split('\n'):
        if line.startswith('--'):
            sec = line[2:]
            continue
        lines.setdefault(sec, []).append(line)
    has = {l[4:] for l in lines.get(None, []) if l.startswith('has ')}
    conf = dict(l.split('=', 1) for l in lines.get('conf', []) if '=' in l)
    lease = {k: v.strip('"') for k, v in (l.split('=', 1) for l in lines.get('lease', [])
                                          if '=' in l)}
    dhcp = conf.get('IP') == 'dhcp'
    log = [l for l in lines.get('log', []) if l.strip()]
    last = log[-1] if log else ''
    if not dhcp:
        ip, gw, mask = conf.get('IP'), conf.get('GW'), conf.get('MASK')
    elif lease:                 # this boot's lease (/mnt/Memory/lease)
        ip, gw, mask = (lease.get('DHCP_IP'), lease.get('DHCP_ROUTER') or lease.get('DHCP_SERVER'),
                        lease.get('DHCP_MASK'))
    elif any('using the fallback address' in l for l in log):
        ip, gw, mask = conf.get('FALLBACK_IP'), conf.get('GW'), conf.get('MASK')
    else:
        ip = gw = mask = None
    pids = running(host, password)
    state = ('not installed' if 'autorun.sh' not in has else
             'joined' if pids and last.startswith('joined') else
             'joining' if pids or (log and not last.startswith(('no ', 'joined'))) else
             'failed' if last.startswith('no ') else
             'stopped (the supplicant exited after joining)' if last.startswith('joined') else
             'installed, not running')
    return {'state': state, 'installed': sorted(has - {'autorun.try', 'autorun.off'}),
            'ssid': ''.join(lines.get('ssid', [])).strip() or None,
            'dhcp': dhcp, 'ip': ip, 'gateway': gw, 'netmask': mask,
            # what is stored, for the UI form (ip/gateway above are what is in use)
            'fallback_ip': conf.get('FALLBACK_IP'), 'fixed_gateway': conf.get('GW'),
            'lease_s': lease.get('DHCP_LEASE') if dhcp else None,
            'at_boot': bool(lines.get('hook')) and 'autorun.off' not in has,
            'boot_hook': bool(lines.get('hook')), 'disabled': 'autorun.off' in has,
            'pids': pids, 'log': [l for l in log if not l.startswith('\t')]}


def describe(st):
    lines = [f'state: {st["state"]}']
    name = repr(st['ssid']) if st['ssid'] else '(name not recorded)'
    if st['ip']:
        lines.append(f'network: {name}  address {st["ip"]}/'
                     f'{st["netmask"] or "255.255.255.0"}  gateway {st["gateway"]}' +
                     (f'  (DHCP, lease {st["lease_s"]} s)' if st.get('lease_s') else ''))
    elif st.get('dhcp'):
        lines.append(f'network: {name}  address: DHCP (no lease yet this boot)')
    if st['boot_hook']:
        lines.append('at boot: ' + ('DISABLED by the failsafe (autorun.off); '
                                    f'`rm {F}/autorun.off` to re-enable' if st['disabled']
                                    else 'yes (autorun firmware)'))
    else:
        lines.append('at boot: no (stock firmware): run `airportctl join start` after each reboot')
    if st['log']:
        lines.append('last run:')
        lines += ['  ' + l for l in st['log']]
    return '\n'.join(lines)


def remove(host, password, log=print):
    _sh(host, password, f'rm -rf {D} {F}/autorun.sh {F}/autorun.try {F}/autorun.off')
    log(f'removed {D} and {F}/autorun.sh. A join already running stays up until the next reboot.')
