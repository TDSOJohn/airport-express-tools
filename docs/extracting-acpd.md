# Getting `ACPd` off your own base station (and into Ghidra)

Everything in `docs/` is a description of Apple's `/sbin/ACPd`. **The binary itself is Apple's
copyrighted firmware and is not distributed with this repo.** You extract it from a base station
you own; that is also the only way to be sure the addresses match *your* firmware version.

Reference build for all the addresses in these documents: **A1392 (AirPort Express 802.11n,
2nd gen), firmware 7.8.1**, `ELF 32-bit MSB, MIPS-I, statically linked, stripped`, image base
`0x00400000`, ~10 MB (the whole userland is one crunched binary).

## 1. Reach the base station

Ethernet from your machine into the Express's **LAN** port (the `‹•••›` icon), and a wired
profile that never takes the default route, so your internet stays where it is:

```sh
nmcli connection add type ethernet con-name airport-probe ifname <your-iface> \
  connection.autoconnect no \
  ipv4.method auto ipv4.never-default yes ipv4.ignore-auto-dns yes \
  ipv4.ignore-auto-routes yes ipv4.route-metric 2000 ipv6.method ignore
nmcli connection up airport-probe
```

In its factory router mode the Express is `10.0.1.1` and hands you `10.0.1.2`. If it is bridged
instead, `python3 tools/find_express.py` sweeps the subnet and the ARP table for Apple's
`20:c9:d0` OUI.

## 2. Enable the debug shell

ACPd exposes a root shell over SSH when the `dbug` property has bit `0x1000`/`0x2000` set:

```sh
python3 - <<'EOF'
import struct, sys; sys.path.insert(0, '.')
from airportctl import acp
acp.set_props('10.0.1.1', 'public', [('dbug', struct.pack('>I', 0x3000))])
acp.reboot('10.0.1.1', 'public')
EOF
```

`public` is the factory admin password; use yours. After the reboot:

```sh
AIRPORT_PW=public tools/essh.sh 'uname -a'
```

`essh.sh` re-enables the legacy KEX/ciphers that OpenSSH now refuses by default — the Express
runs a 2007-era SSH server. **Turn the shell back off when you are done** (`dbug` = 0 + reboot).

## 3. Copy the binary out

There is no `scp` on the device, so stream it over the shell (ssh does not allocate a tty for a
remote command, so stdout stays 8-bit clean):

```sh
AIRPORT_PW=public tools/essh.sh 'cat /sbin/ACPd' > ACPd.bin
file ACPd.bin       # ELF 32-bit MSB executable, MIPS, MIPS-I, statically linked, for NetBSD 4.0
sha256sum ACPd.bin
```

If anything mangles it, go through base64 instead: `tools/essh.sh 'uuencode /sbin/ACPd -'`, or
copy it to `/mnt/Memory` first with `crossdev/run.sh`'s technique in reverse.

The build these documents describe is **10 295 088 bytes**,
`f7730dab1c0016ee5fde7376ec439021410371504ca654a8f8e4211fd27b38be`. A different hash means a
different firmware and the addresses below will have moved.

Two device quirks that will bite you: `/sbin` is not in the device's `PATH`, and there is no
`grep`, `head` or `id` — filter output on your laptop.

## 4. Import into Ghidra

Any recent Ghidra; 12.1.3 on OpenJDK 21 is what these scripts were run with. Language
**MIPS:BE:32:default**, image base **0x00400000**, then a full auto-analysis (~18 600 functions;
it takes a while and a few GB of RAM).

```sh
/path/to/ghidra/support/analyzeHeadless "$PWD/ghidra_project" acpd \
  -import ACPd.bin -processor MIPS:BE:32:default
```

## 5. Get the function names back

The single highest-value step. ACPd passes its own function names to its lock/log wrappers as
`__func__` strings, so ~2310 functions can be re-identified automatically:

```sh
/path/to/ghidra/support/analyzeHeadless "$PWD/ghidra_project" acpd \
  -process ACPd.bin -readOnly -noanalysis \
  -scriptPath "$PWD/ghidra_scripts" -postScript NameFuncs.java func_names.txt
```

You get `ACPGetPropertyDirect`, `ACPSetPropertyDirectEx`, `ACPPostProblemDirect`,
`ACPClearProblemDirect`, `ACPPropertyHandlerInstallDirect`, `ACPCloud_*`, … which is enough to
navigate the rest.

## 6. Useful anchors

| what | how to find it |
|---|---|
| ACP property table | `FUN_00807418` (the lookup); table at VMA `0xc5af38`, 12-byte records, zero-terminated. `python3 tools/proptab.py ACPd.bin` |
| the join gate | `ImmScan.java 0x6374696d` (the `ctim` fourcc) |
| wpa_supplicant spawn | `FindStr.java '/sbin/wpa_supplicant'` then `Xrefs.java` on the hit |
| hostapd config writer | `FindStr.java 'wpa_psk'` / `'rsn_pairwise'` |
| the WiFi blob | `ImmScan.java 0x57694669` (`'WiFi'`) |

Note `strings -t x` prints **file** offsets: VMA = file offset + `0x400000`.
