# Getting `ACPd`

`/sbin/ACPd` is Apple's and is not in this repo. Two ways to get your own copy:

| Source | Needs | How |
|---|---|---|
| Firmware image | the model's AES key ([models.md](models.md#firmware-images)) | `tools/decrypt_basebinary.py X.basebinary X.img && tools/ufs1.py X.img cat /sbin/ACPd > ACPd.bin` ([firmware.md](firmware.md#tools)) |
| A unit | the debug SSH login ([below](#enable-ssh)) | `tools/essh.sh 'cat /sbin/ACPd' > ACPd.bin` |

Both give the same file (checked on `syAP` 115 / 7.8.1 and 108 / 7.6.9).

| Build | Bytes | SHA-256 | Format |
|---|---:|---|---|
| `syAP` 115, 7.8.1 (the [reference build](README.md#conventions)) | 10 295 088 | `f7730dab1c0016ee5fde7376ec439021410371504ca654a8f8e4211fd27b38be` | ELF 32-bit MSB, MIPS-I, static, stripped, NetBSD 4.0; image base `0x00400000` |

`/sbin/ACPd` is the crunched megabinary: the whole userland in one file.

## Enable SSH

Connect to the LAN port ([README § Install](../README.md#install--run)), then set `dbug` to a
value with bit `0x200` clear ([dbug.md](dbug.md)) and reboot:

```sh
python3 - <<'EOF'
import struct, sys; sys.path.insert(0, '.')
from airportctl import acp
acp.set_props('10.0.1.1', 'public', [('dbug', struct.pack('>I', 0x3000))])
acp.reboot('10.0.1.1', 'public')
EOF
AIRPORT_PW=public tools/essh.sh 'uname -a'
```

`public` = factory admin password; use yours. To turn SSH off: a value with `0x200` set
(e.g. `0x3200`) and reboot; `0` keeps SSH on.

| `tools/essh.sh` | |
|---|---|
| Password | `$AIRPORT_PW`, else the first line of `$AIRPORT_PW_FILE` (default `~/.config/airport-express/admin-pw`), else `public` |
| Host | `$AIRPORT_HOST` (default `10.0.1.1`) |
| Known hosts | `tools/.airport_known_hosts` |
| Algorithms | re-enables the legacy KEX / host-key / ciphers OpenSSH 4.4 needs |
| Binary output | stdout is 8-bit clean (no tty for a remote command); fallback `uuencode /sbin/ACPd -` |

Device shell: no `grep`, `head`, `id` or `scp`; `/sbin` is not in `PATH`.

## Ghidra

| | |
|---|---|
| Version | Ghidra 12.1.3 on OpenJDK 21 |
| Language | `MIPS:BE:32:default`, image base `0x00400000` |
| Analysis | full auto-analysis, ~18 600 functions, a few GB of RAM |
| File offsets | `strings -t x` prints file offsets: VMA = offset + `0x400000` |

```sh
/path/to/ghidra/support/analyzeHeadless "$PWD/ghidra_project" acpd \
  -import ACPd.bin -processor MIPS:BE:32:default
/path/to/ghidra/support/analyzeHeadless "$PWD/ghidra_project" acpd \
  -process ACPd.bin -readOnly -noanalysis \
  -scriptPath "$PWD/ghidra_scripts" -postScript NameFuncs.java func_names.txt
```

`NameFuncs.java` recovers ~2310 function names from the `__func__` strings ACPd passes to its
lock/log wrappers (`ACPGetPropertyDirect`, `ACPSetPropertyDirectEx`, `ACPPostProblemDirect`,
`ACPClearProblemDirect`, `ACPPropertyHandlerInstallDirect`, `ACPCloud_*`, …). Other scripts:
[ghidra_scripts](../ghidra_scripts/README.md).

## Anchors

For re-finding the addresses in these docs on another build.

| Target | Find with |
|---|---|
| ACP property table | `python3 tools/proptab.py ACPd.bin`; lookup `FUN_00807418`, table `0xc5af38` |
| Client-mode gate | `ImmScan.java 0x6374696d` (`ctim`) |
| wpa_supplicant spawn | `FindStr.java '/sbin/wpa_supplicant -K -M %s -F %s -D net80211 -i %s -c %s'`, then `Xrefs.java` |
| hostapd config writer | `FindStr.java 'wpa_psk'` / `'rsn_pairwise'` |
| `WiFi` blob | `ImmScan.java 0x57694669` (`WiFi`) |
| `dbug` consumers | `ImmScan.java 0x64627567` (`dbug`) |
| RPC registrars | `RpcMap.java 0x6717dc`, `RpcMap.java 0x80b058` |
