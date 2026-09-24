# The `dbug` property bitfield of firmware 7.8.1

`dbug` (fourcc `0x64627567`, a plain `uint32` — table entry at VMA `0xc5bd78`, `type=5`,
`flags=0x00`) is the AirPort's debug switch. The one value everybody knows is **`0x3000`,
"the SSH value"** — it is what the airpyrt/AirPort-hacking community sets to get a root
shell. Nobody documents the other bits, or *why* `0x3000` in particular turns SSH on. This
page maps every bit that ACPd actually reads, from the decompiled consumers, and corrects
the folklore: **it is not the `0x3000` bits that enable SSH — it is that `0x3000` leaves
bit `0x200` clear.**

Read live on an A1392 (7.8.1) on 2026-09-24: `dbug = 0x00003000`, and `sshd` was indeed
listening (`SSH-1.99-OpenSSH_4.4 NetBSD_Secure_Shell-20061114`), telnet (23) closed.

## How to read it

```sh
# read-only; needs the admin password (dbug is auth-gated like any getprop)
python3 - <<'PY'
import struct; from airportctl import acp
raw = acp.get_raw('10.0.1.1', acp.read_password('@~/.config/airport-express/admin-pw'), 'dbug')
print(hex(struct.unpack('>I', raw[:4])[0]))
PY
```

## Where the value goes

ACPd reads `dbug` through `ACPGetPropertyDirect` (`FUN_00675684`) in a few places and keeps
**four** in-memory copies. The bit tests live on those copies, not on a single global — which
is why a plain string search for the fourcc only finds five sites and misses most of the
behaviour.

| copy | set by | read by | bits it gates |
|------|--------|---------|---------------|
| `DAT_00d602ec` | `FUN_0067a744` (button/msg dispatcher init) | `FUN_00673718` (ACPLock), `FUN_0067396c` (ACPUnlock) | `0x40`, `0x80`, `0x100` |
| `DAT_00e47130` | `FUN_00672ab4` (registers `acprpc.show`) | `FUN_006720c4` (ACPd RPC dispatch) | `0x400` |
| `DAT_00fb6f80` | `FUN_0080ab9c` (`/tmp/ACPIPC` connect, IPC side) | `FUN_00809cc4` (IPC RPC dispatch), `FUN_0080da10` (IPC client RPC) | `0x400`, `0x800` |
| *stack* + `DAT_00e46ec4` | `FUN_0065b7c0` (main event loop) → passed to `FUN_0065746c` (config/network bring-up) | same two functions | `0x200`, `0x1000`, `0x2000`, `0x4000` |

## The bits

| bit | effect when **set** | default (bit clear) | consumer |
|-----|---------------------|---------------------|----------|
| `0x40`  | log every ACP lock acquire/release (`+++ ACPLock locked/unlocked by …`) | quiet | `FUN_00673718` / `FUN_0067396c` |
| `0x80`  | log ACP lock **contention** (`### ACPLock … CONTENTION …`) | quiet | `FUN_00673718` |
| `0x100` | **disable ACP internal locking** — the lock/unlock bodies are skipped entirely | locking on | `FUN_00673718` / `FUN_0067396c` |
| `0x200` | **`sshd` OFF** | **`sshd` ON** (see below) | `FUN_0065b7c0` |
| `0x400` | trace every RPC dispatch (`RPC Dispatch` / `RPC Dispatch Raw`), both the ACPd and the IPC registrar | quiet | `FUN_006720c4`, `FUN_00809cc4` |
| `0x800` | trace the IPC client-RPC transport (`Client RPC`) | quiet | `FUN_0080da10` |
| `0x1000` | suppress the **TCP** iperf server | `iperf -s -w 192k` launched *if `/usr/bin/iperf` exists* | `FUN_0065746c` |
| `0x2000` | suppress the **UDP** iperf server | `iperf -s -u -l 192k -w 192k` launched *if `/usr/bin/iperf` exists* | `FUN_0065746c` |
| `0x4000` | force an interface up even when the normal bring-up logic wouldn't (`FUN_006530dc` → `FUN_006538cc(…, 1)`) | normal | `FUN_0065746c` |

Bits above `0x4000` and below `0x40` are not read by any ACPd `dbug` consumer. The shipping
`0x10000` seen elsewhere in `FUN_0065746c` belongs to a **different** word (`DAT_00e46ec0`,
the network-mode bitfield built from the `ra**`/`BUwa`/… props) that happens to reuse the
same numeric masks — don't confuse the two.

## The SSH path (bit `0x200`), decompiled

In the event loop `FUN_0065b7c0`, right after `Initialized (firmware 7.8.1)`:

```c
FUN_00675684(0x64627567, 0x10000, 4, &dbug, 0);   // read dbug (0x10000 is a mode flag, not a default)
if ((dbug & 0x200) != 0) goto after_ssh;           // bit 0x200 SET -> no sshd
    // else, on every boot:
    //   - if /mnt/Flash/ssh_host_key[.pub] absent: ssh-keygen rsa1/dsa/rsa, copy to /mnt/Flash
    //   - if present: copy from /mnt/Flash back to /etc/ssh
    fp = fopen("/etc/ssh/sshd_config", "w");
    fputs("PermitRootLogin yes\n", fp);            // written fresh each boot
    fclose(fp);
    spawn("/usr/sbin/sshd", "-D", "-e");
after_ssh:
    ...
```

So:

* **SSH is on unless bit `0x200` is set.** `0x3000` works because `0x3000 & 0x200 == 0`; so
  would `0x0`, `0x1000`, `0x2000`, … The community's `0x3000` additionally sets `0x1000|0x2000`,
  which only matters as "don't also start the iperf test servers" — cosmetic on a stock image
  where `/usr/bin/iperf` isn't present. **`0x200` alone is enough to keep SSH off; `0x3000`
  is not a magic SSH key.**
* Host keys are the only thing `dbug` persists to Flash (`/mnt/Flash/ssh_host_*`). There is
  **no general run-at-boot / arbitrary-command hook** behind any `dbug` bit — the answer to
  "is there a persistence hook here" is: only `sshd` itself, plus its keys in Flash.
* `sshd` advertises **`SSH-1.99`** (SSHv1 still offered) and `PermitRootLogin yes`.

### Why root login matters: the password sync

The top of `FUN_0065746c` (runs on every config apply) is unconditional — not gated by `dbug`:

```c
FUN_00675684(0x73795057, 0x10000, 0x1f, pw, &len);   // 0x73795057 = 'syPW' = the ADMIN password
pw[len] = 0;
pwent = getpwnam("root");
if (pwent) {
    hash = crypt(pw, localcipher_salt);               // hash the admin password
    spawn("/usr/sbin/user", "mod", "-p", hash, "root");   // root's password := admin password
}
```

Root's Unix password is kept equal to the base-station admin password on every boot.
Combined with `PermitRootLogin yes` and `sshd` (when `0x200` is clear), **enabling SSH gives
`root@<express>` with the admin password** — no separate root credential exists. This is the
mechanism behind the well-known "root password = admin password" fact; it is set here, in
ACPd, via `user mod`.

## Security summary (for the owner-facing write-up, R6)

* `dbug` with bit `0x200` clear ⇒ `sshd` on ⇒ `root` reachable over the network with the
  admin password, on a 2006-era OpenSSH that still offers SSHv1.
* The setting is auth-gated (you need the admin password to *set* `dbug`), so it is not a
  remote-unauth hole by itself — but a device left with `dbug & 0x200 == 0` is a root box on
  the LAN, and the "debug" framing undersells that. If you enabled SSH to poke at one, set
  `dbug` back to a value with `0x200` set (e.g. `0x3200`) when you're done.
* iperf (`0x1000`/`0x2000`) and the lock/RPC tracing bits (`0x40`–`0x800`) are diagnostics
  with no security weight on a stock image; `0x100` (locking off) is only interesting as a
  way to destabilise ACPd.

## Live confirmation (A1392, 7.8.1, 2026-09-24)

* `getprop dbug` → `0x00003000` (bits `0x1000|0x2000` set, `0x200` clear).
* TCP/22 open, banner `SSH-1.99-OpenSSH_4.4 NetBSD_Secure_Shell-20061114`; TCP/23 refused.
* Matches the decompiled model exactly: `0x200` clear ⇒ `sshd` running; `0x1000|0x2000` set
  ⇒ no iperf servers (and `/usr/bin/iperf` isn't on the stock image anyway).
