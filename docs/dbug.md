# `dbug`

The debug bitfield: fourcc `0x64627567`, uint32, flags `0x00` (table entry `0xc5bd78`).
Settable over ACP with the admin password; read at boot. Advertised by the `feat` code `UsDb`.

## Values

| Value | sshd | iperf servers |
|---|---|---|
| unset (factory) | off | |
| `0x3000` (community "SSH value") | **on** | not started |
| `0` | **on** | started if `/usr/bin/iperf` exists (not on the stock image) |
| any value with `0x200` set, e.g. `0x3200` | off | |

SSH is on whenever bit `0x200` is clear; `0x1000` / `0x2000` only suppress iperf. Turning
SSH on or off takes a reboot. Setting it: [extracting-acpd.md](extracting-acpd.md#enable-ssh).
Seen live: `0x3000` → TCP 22 open on the A1392, A1254 and A1301 ([models.md](models.md#acp-and-access)).

## Bits

| Bit | Set | Clear (default) | Consumer |
|---|---|---|---|
| `0x40` | log every ACP lock acquire/release (`+++ ACPLock locked/unlocked by …`) | quiet | `FUN_00673718`, `FUN_0067396c` |
| `0x80` | log ACP lock contention (`### ACPLock … CONTENTION …`) | quiet | `FUN_00673718` |
| `0x100` | ACP internal locking disabled | locking on | `FUN_00673718`, `FUN_0067396c` |
| `0x200` | **sshd off** | **sshd on** | `FUN_0065b7c0` |
| `0x400` | trace every RPC dispatch (`RPC Dispatch` / `RPC Dispatch Raw`), ACPd and IPC registrars | quiet | `FUN_006720c4`, `FUN_00809cc4` |
| `0x800` | trace the IPC client-RPC transport (`Client RPC`) | quiet | `FUN_0080da10` |
| `0x1000` | no TCP iperf server | `iperf -s -w 192k` if `/usr/bin/iperf` exists | `FUN_0065746c` |
| `0x2000` | no UDP iperf server | `iperf -s -u -l 192k -w 192k` if `/usr/bin/iperf` exists | `FUN_0065746c` |
| `0x4000` | force an interface up (`FUN_006530dc` → `FUN_006538cc(…, 1)`) | normal | `FUN_0065746c` |

No ACPd consumer reads bits below `0x40` or above `0x4000`. The `0x10000` tested in
`FUN_0065746c` belongs to a different word (`DAT_00e46ec0`, the network-mode bitfield).
`0x1000` / `0x2000` also gate the WAN-side iperf port ([security.md](security.md#wan-side)).

ACPd keeps four copies of `dbug`:

| Copy | Set by | Read by | Bits |
|---|---|---|---|
| `DAT_00d602ec` | `FUN_0067a744` (button/message dispatcher init) | `FUN_00673718` (ACPLock), `FUN_0067396c` (ACPUnlock) | `0x40`, `0x80`, `0x100` |
| `DAT_00e47130` | `FUN_00672ab4` (registers `acprpc.show`) | `FUN_006720c4` (RPC dispatch) | `0x400` |
| `DAT_00fb6f80` | `FUN_0080ab9c` (`/tmp/ACPIPC` connect) | `FUN_00809cc4` (IPC RPC dispatch), `FUN_0080da10` (IPC client RPC) | `0x400`, `0x800` |
| stack + `DAT_00e46ec4` | `FUN_0065b7c0` (main event loop) → `FUN_0065746c` (network bring-up) | same | `0x200`, `0x1000`, `0x2000`, `0x4000` |

## SSH

In `FUN_0065b7c0`, after `Initialized (firmware 7.8.1)`:

```c
FUN_00675684(0x64627567, 0x10000, 4, &dbug, 0);   // read dbug
if ((dbug & 0x200) != 0) goto after_ssh;           // bit set: no sshd
    // host keys: if /mnt/Flash/ssh_host_key[.pub] absent: ssh-keygen rsa1/dsa/rsa, copy to /mnt/Flash
    //            else copy from /mnt/Flash to /etc/ssh
    fp = fopen("/etc/ssh/sshd_config", "w");
    fputs("PermitRootLogin yes\n", fp);            // rewritten every boot
    fclose(fp);
    spawn("/usr/sbin/sshd", "-D", "-e");
after_ssh:
```

On every config apply, regardless of `dbug` (`FUN_0065746c`):

```c
FUN_00675684(0x73795057 /* syPW */, 0x10000, 0x1f, pw, &len);
pwent = getpwnam("root");
if (pwent) spawn("/usr/sbin/user", "mod", "-p", crypt(pw, salt), "root");
```

| | |
|---|---|
| Login | `root`, password = admin password (`syPW`); no separate root credential |
| Server | `SSH-1.99-OpenSSH_4.4 NetBSD_Secure_Shell-20061114`; offers SSHv1; needs legacy KEX/host-key/cipher options on a modern client (`tools/essh.sh`) |
| Persisted | only the host keys (`/mnt/Flash/ssh_host_*`); no other run-at-boot hook behind any bit |
| Password change | ACP uses the new admin password at once; root's password follows at the next reboot |
| First boot with SSH | A1301: banner after ~3–4 min (host-key generation) |
