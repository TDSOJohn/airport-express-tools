# Autorun: starting your own code at boot

Files on `/mnt/Flash` survive reboots and power cuts
([crossdev § Storage](../crossdev/README.md#storage-usb-and-persistence)), but stock firmware
never runs anything from there. `/etc/rc`, the `rc.d` scripts, `crontab` and svscan's
`/var/sv` all live in the md0 RAM disk, which is rebuilt from the firmware bank on every
boot ([boot.md](boot.md)). Only ACPd (`ACPData.bin`) and sshd (host keys) read `/mnt/Flash`.

So autorun needs one change to the firmware: a hook at the end of `/etc/rc` that starts
`/mnt/Flash/autorun.sh`. Everything else stays on Flash, where it can be changed without
reflashing.

> **Status (2026-09-25):** the image is built and checked **offline only**. It has not
> been flashed yet. The plan is below.

## The hook

[`autorun/rc`](../autorun/rc) is the stock 7.8.1 `/etc/rc` with some comments trimmed and
this block added after the `rc.d` loop (so `/mnt/Flash` is mounted and ACPd is running):

```sh
A=/mnt/Flash/autorun
if [ -f $A.sh -a ! -f $A.off ]; then
	if [ -f $A.try ]; then
		mv $A.try $A.off
	else
		: > $A.try
		sh $A.sh </dev/null >/dev/null 2>&1 &
	fi
fi
```

With no `autorun.sh` on Flash, the image behaves exactly like stock.

**Rules for `autorun.sh`:**

* It runs in the background, so boot does not wait for it. It should wait for whatever
  it needs itself, e.g. poll until ACPd has brought up the interfaces.
* It must **`rm /mnt/Flash/autorun.try` once it is healthy.** If a boot finds `.try`
  still there, the previous run never got that far (hang, crash or reboot loop), so the
  hook renames it to `autorun.off` and stops running the script. Power-cycling a stuck
  unit therefore always disables autorun on the next boot.
* To re-enable it, `rm /mnt/Flash/autorun.off`. To disable it by hand,
  `touch /mnt/Flash/autorun.off`.
* A power cut before the script clears `.try` also counts as a failure, so autorun turns
  off. That's the safe side to err on.

## Building the image

```sh
tools/repack_basebinary.py roundtrip 7.8.1.basebinary      # must print IDENTICAL
tools/repack_basebinary.py replace 7.8.1.basebinary /etc/rc autorun/rc 7.8.1-autorun.basebinary
```

`repack_basebinary.py` reverses [firmware.md](firmware.md)'s unpacking. The inner
plaintext is a 22,432-byte gzboot loader, then the gzip'd kernel with the md0 RAM disk,
then zero padding to 4 bytes. The loader stores no lengths. zlib level 9 (window 15,
memLevel 8) reproduces Apple's deflate stream **byte for byte**, so repacking an unmodified
7.8.1 image gives back Apple's file exactly. That is the round-trip test.

`replace` rewrites a file in place inside its already-allocated fragments. `/etc/rc` has
1024 bytes allocated, the stock file uses 945 and ours 989. Only the file data and
`di_size` change, with no FFS allocation. Checked on the result: the containers
re-parse with valid Adler-32 checksums, all 1664 ramdisk entries match stock except
`/etc/rc`, and the image length is unchanged (876 bytes differ). Every command the hook
uses (`sh`, `mv`) is in the ramdisk.

## How updates land on the banks (from ACPd)

There are two ways in, both gated by the admin password and the `updateROM` permission:

| ACP request | What it does |
|---|---|
| command 3 | synchronous "flash primary": `FUN_00699e90` → bank A (the airpyrt-tools way) |
| command 4 | stub, returns -1 |
| commands 5 / 6 | bank B / bootloader, only if the `diag` property is set (`FUN_0067f05c`, which is also the `acp.setStaticConfig` gate) |
| `setProperties` (0x15), streaming, pseudo-property `fupp` | **upload**: basic checks, then the image is kept in RAM (AirPort Utility's way) |
| same, `fust` | **start**: writes the kept image to bank A in a thread (`FUN_00675504`); no reboot |
| same, `fuca` / `fugp` | always return an error |

The writer `FUN_00699a84` peels the containers, decrypts flagged ones in place
(`FUN_00699324`), and requires model `0x73`, a 3–7 MB bank and version ≥ `minS`. For a real
write it then writes the bank with a checksum trailer and **reads bank A back to verify
it** (returns -6 on mismatch). `fupp` runs it with target `0x80000001`, which stops before
writing.

That check is **not a useful dry run.** Tried live on 2026-09-25: `fupp` alone (no `fust`)
returned 0 for our image, but also for a copy with one byte flipped. Nothing is written
without `fust`, but "accepted by `fupp`" says little. Our evidence that the image is
well-formed is offline: the byte-identical round trip plus valid checksums.

After an update:

* ACPd's A→B clone (`FUN_00698ae8`) is **compiled out** on this model: its gate
  `FUN_00649e48` returns 0. **Bank B keeps the previous (stock) image.**
* At boot ACPd verifies bank A (`FUN_00698dac`: length plus checksum trailer at the end of
  the bank). If A is bad and B is good, it copies B over A (`FUN_0069908c`).
* CFE boots A and falls back to B **only when A fails its checksum**. An image that
  passes the checksum but doesn't come up will **not** fall back automatically.

## The payload: joining Wi-Fi at boot

[`airportctl/payload/autorun.sh`](../airportctl/payload/autorun.sh) runs the same steps as
[join-test.sh](../crossdev/wpa-build/join-test.sh). It waits for ACPd to start the 2.4 GHz
hostapd, then 20 s more. It logs to `/mnt/Memory/autorun.log` (RAM), and it clears
`autorun.try` when it finishes. If the join fails, it stops the supplicant and exits
cleanly, and the 5 GHz AP and Ethernet stay up.

It also sets the front LED through the on-device `acp` tool (`acp -q LEDc=N`: 0 = ACPd's
own status, 1 = amber, 2 = green). The LED shows ACPd's status while the script works,
then solid green once joined, or solid amber if the join failed. ACPd judges only the
Ethernet WAN: with nothing upstream there, its mDNS record carries
`prob=waCF;waNI;nDNS;` and the LED blinks amber even while we're joined. The LED is set
once and doesn't track later link loss. `LEDc` changes live (solid green confirmed by eye on
2026-09-25) and doesn't rewrite `ACPData.bin`.

**Installing it:** `airportctl join` (or the "Join a Wi-Fi network" card in `airportctl ui`)
does it over the debug SSH login, which you turn on by hand first ([dbug.md](dbug.md)):

```sh
airportctl join install MyWiFi --wifi-password @~/.wifipw     # DHCP; or --ip A --gateway G
airportctl join status      # installed files, rejoin at boot or not, the last run's log
airportctl join start       # join again: after every reboot on stock firmware
airportctl join remove      # delete it all from /mnt/Flash
```

It copies the prebuilt supplicant and DHCP client shipped in the package (`airportctl/payload/`,
see `NOTICE.txt`; each skipped if the copy on Flash already matches), a `wpa.conf` with the SSID
in hex and only the PMK, `join.conf` (`IP=dhcp`, optionally with `FALLBACK_IP`/`GW`/`MASK`, or a
fixed `IP`/`GW`/`MASK`) and `autorun.sh`, then starts the join. How the DHCP address is applied
without losing the WPA keys is in [join-mode.md](join-mode.md#addressing-dhcp).
On stock firmware that lasts until the next reboot. With the autorun image it is redone at
every boot.

## Plan

1. ✅ Offline repacker, byte-identical round trip.
2. ✅ Hook with failsafe, simulated on a PC across boots (no script, healthy script,
   script that hangs, then disabled).
2b. ✅ Payload tested by hand on stock firmware (2026-09-25): started right after a reboot
   the way the hook would, it joined in 44 s (GTK installed), ran the supplicant from
   Flash, moved AirPlay (advertised on the joined network) and cleared `autorun.try`.
3. ☐ **Serial console first** (debug header, 115200 8N1, see [hardware.md](hardware.md)).
   It's the only way back in if the new bank A passes its checksum but fails to boot.
4. ☐ Confirm A and B are identical stock 7.8.1. Then upload to **bank A** (command 3,
   or `fupp` + `fust`, then reboot). B stays stock.
5. ☐ Boot test: no `autorun.sh` (should behave like stock), then a script that writes a
   timestamp, then the Wi-Fi join ([join-mode.md](join-mode.md)).

**Going back:** upload stock `7.8.1.basebinary` the same way. If the unit won't boot,
use the serial console.
