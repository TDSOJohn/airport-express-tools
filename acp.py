"""ACP client (AirPort admin protocol, TCP 5009): header-key auth + getprop/setprop/rpc/reboot.

Ported from airpyrt-tools (https://github.com/x56/airpyrt-tools), Copyright (c) 2016 Vince Cali,
MIT License. The admin password is only lightly obfuscated in the header (XOR against a static
keystream), so use this over a trusted direct cable, never across an untrusted network.
"""
import os
import socket
import struct
import zlib

from . import cfl

ACP_PORT = 5009
STATIC_KEY = bytes.fromhex('5b6faf5d9d5b0e1351f2da1de7e8d673')
# magic, version, header checksum, body checksum, body size, flags, unused, command, error code, key
HDR = struct.Struct('!4s8i12x32s48x')
# property element: name (fourcc), flags, value size (value bytes follow)
ELEM = struct.Struct('!4s2I')
CMD_GETPROP = 0x14
CMD_SETPROP = 0x15
CMD_RPC = 0x19
ERR_WRONG_PASSWORD = 0xfffffff0


def _s32(x):
    return x - (1 << 32) if x >= (1 << 31) else x


def _keystream(n):
    return bytes((((i + 0x55) & 0xFF) ^ STATIC_KEY[i % len(STATIC_KEY)]) for i in range(n))


def _header_key(password):
    pw = password.encode()[:32].ljust(32, b'\0')
    return bytes(a ^ b for a, b in zip(_keystream(32), pw))


def _compose(command, flags, password, body):
    fields = [b'acpp', 0x00030001, 0, _s32(zlib.adler32(body)), len(body), flags, 0, command, 0,
              _header_key(password)]
    fields[2] = _s32(zlib.adler32(HDR.pack(*fields)))
    return HDR.pack(*fields) + body


def _recv_exact(sock, n):
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(f'connection closed after {len(buf)}/{n} bytes')
        buf += chunk
    return buf


def default_password():
    """Admin password when none is given: $AIRPORT_PW, else @$AIRPORT_PW_FILE or
    @~/.config/airport-express/admin-pw if it exists, else the factory `public`.
    Same lookup as tools/askpass.sh, so every tool and the SSH helper agree."""
    if os.environ.get('AIRPORT_PW'):
        return os.environ['AIRPORT_PW']
    f = os.environ.get('AIRPORT_PW_FILE') or os.path.expanduser('~/.config/airport-express/admin-pw')
    return '@' + f if os.path.isfile(f) else 'public'


def read_password(arg):
    """Admin/Wi-Fi password from the command line; @FILE reads the first line of FILE."""
    if arg.startswith('@'):
        with open(os.path.expanduser(arg[1:])) as f:
            return f.readline().rstrip('\r\n')
    return arg


def get_props(host, password, names, timeout=10):
    """Return (error_code, [(name, flags, raw)]); flags & 1 => value is a 4-byte error code."""
    body = b''.join(ELEM.pack(n.encode('latin1'), 0, 4) + b'\0\0\0\0' for n in names)
    with socket.create_connection((host, ACP_PORT), timeout=timeout) as s:
        s.sendall(_compose(CMD_GETPROP, 4, password, body))
        fields = HDR.unpack(_recv_exact(s, HDR.size))
        if fields[0] != b'acpp':
            raise ValueError(f'bad reply magic {fields[0]!r}')
        err = fields[8] & 0xFFFFFFFF
        if err:
            return err, []
        props = []
        while True:
            name, flags, size = ELEM.unpack(_recv_exact(s, ELEM.size))
            data = _recv_exact(s, size)
            if name == b'\0\0\0\0':
                break
            props.append((name.decode('latin1'), flags, data))
        return 0, props


def get_raw(host, password, name, timeout=10):
    """Return the raw bytes of a single property, raising a clear error on failure."""
    err, props = get_props(host, password, [name], timeout)
    if err:
        hint = ' (wrong admin password)' if err == ERR_WRONG_PASSWORD else ''
        raise RuntimeError(f'getprop {name} failed: ACP error 0x{err:08x}{hint}')
    _n, flags, data = props[0]
    if flags & 1:
        raise RuntimeError(f'getprop {name} failed: error 0x{struct.unpack(">I", data[:4])[0]:08x}')
    return data


def set_props(host, password, props, timeout=15):
    """Set (name, raw bytes) pairs; return [(name, error_code)] for any the device rejected."""
    body = b''.join(ELEM.pack(n.encode('latin1'), 0, len(v)) + v for n, v in props)
    failures = []
    with socket.create_connection((host, ACP_PORT), timeout=timeout) as s:
        s.sendall(_compose(CMD_SETPROP, 0, password, body))
        fields = HDR.unpack(_recv_exact(s, HDR.size))
        if fields[0] != b'acpp':
            raise ValueError(f'bad reply magic {fields[0]!r}')
        if fields[8]:
            raise RuntimeError(f'setprop rejected: ACP error 0x{fields[8] & 0xFFFFFFFF:08x}')
        try:
            while True:
                name, flags, size = ELEM.unpack(_recv_exact(s, ELEM.size))
                data = _recv_exact(s, size)
                if flags & 1:
                    failures.append((name.decode('latin1'), struct.unpack('>I', data[:4])[0]))
                elif name == b'\0\0\0\0':
                    break
        except (socket.timeout, ConnectionError):
            pass  # some firmware ends the reply without the end marker
    return failures


def rpc(host, password, function, inputs=None, timeout=10):
    """Call an ACP RPC function; return the parsed reply dict ({'status':..., 'outputs':...})."""
    body = cfl.compose({'function': function, 'inputs': inputs or {}})
    with socket.create_connection((host, ACP_PORT), timeout=timeout) as s:
        s.sendall(_compose(CMD_RPC, 0, password, body))
        fields = HDR.unpack(_recv_exact(s, HDR.size))
        size, err = fields[4], fields[8] & 0xFFFFFFFF
        if err:
            raise RuntimeError(f'RPC {function} failed: ACP error 0x{err:08x}')
        return cfl.parse(_recv_exact(s, size))


def reboot(host, password, timeout=10):
    """Ask the base station to reboot (acRB); the connection dropping is expected."""
    try:
        return set_props(host, password, [('acRB', struct.pack('>I', 0))], timeout)
    except OSError:
        return []
