# Autorun image

A 7.8.1 image for the A1392 with one change: a hook at the end of `/etc/rc` that starts
`/mnt/Flash/autorun.sh`. Stock firmware never runs anything from `/mnt/Flash`: `/etc/rc`,
`rc.d`, `crontab` and svscan's `/var/sv` all live in the md0 RAM disk
([boot.md](boot.md#flash-partitions)).

| | |
|---|---|
| Status | image built and checked offline; payload verified on stock firmware (started by hand); **image not flashed yet** |
| Without `autorun.sh` | behaves like stock |
| Flash it | ACP command 3, or `fupp` + `fust`, then reboot ([boot.md § Update paths](boot.md#update-paths-acpd)); bank A only |
| Undo | upload stock `7.8.1.basebinary` the same way; if the unit doesn't boot, the [CFE console](boot.md#cfe-console) (an image that passes its checksum but hangs does not fall back to bank B) |

## The hook

[`autorun/rc`](../autorun/rc) = stock `/etc/rc` (some comments trimmed) plus, after the
`rc.d` loop (`/mnt/Flash` mounted, ACPd running):

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

| File | Meaning |
|---|---|
| `autorun.sh` | the script; runs in the background, so it must wait for what it needs itself (e.g. ACPd's interfaces) |
| `autorun.try` | created before each run; the script must `rm` it once healthy. Found at boot → the last run never got there (hang, crash, reboot loop, power cut) → renamed to `autorun.off` |
| `autorun.off` | autorun disabled. `rm` it to re-enable; `touch` it to disable by hand |

A power cycle of a stuck unit therefore always disables autorun on the next boot.

## Building

```sh
tools/repack_basebinary.py roundtrip 7.8.1.basebinary      # must print IDENTICAL
tools/repack_basebinary.py replace 7.8.1.basebinary /etc/rc autorun/rc 7.8.1-autorun.basebinary
```

| Check | Result |
|---|---|
| Round trip | repacking unmodified 7.8.1 reproduces Apple's file byte for byte ([firmware.md](firmware.md#basebinary-format)) |
| `/etc/rc` fit | 1024 bytes allocated, stock 945, ours 989: only file data and `di_size` change, no FFS allocation |
| Result | containers re-parse with valid Adler-32s; all 1664 ramdisk entries match stock except `/etc/rc`; same length, 876 bytes differ |
| Hook commands | `sh`, `mv`: both in the ramdisk |
| `fupp` acceptance | not evidence: `fupp` also accepts a one-byte-corrupted image |

## Payload: join Wi-Fi at boot

[`airportctl/payload/autorun.sh`](../airportctl/payload/autorun.sh), installed by
`airportctl join install` ([join-mode.md](join-mode.md#join-sequence)):

| | |
|---|---|
| Start | waits for ACPd to start the 2.4 GHz hostapd, then 20 s more |
| Steps | the [join sequence](join-mode.md#join-sequence) + [DHCP](join-mode.md#addressing-dhcp); clears `autorun.try` when done |
| Failure | stops the supplicant and exits; 5 GHz AP and Ethernet stay up |
| Log | `/mnt/Memory/autorun.log` (RAM) |
| LED | `acp -q LEDc=N` on the device: ACPd status while working, solid green once joined, solid amber on failure. Set once; doesn't follow later link loss. `LEDc` doesn't rewrite `ACPData.bin` |
| Why the LED is forced | ACPd judges only the Ethernet WAN: with nothing there it posts `waCF;waNI;nDNS` and blinks amber even while joined |

Files on `/mnt/Flash` (each skipped if the copy there already matches):

| File | Contents |
|---|---|
| `wpa_supplicant` | prebuilt 0.7.3, ~295 KB (`airportctl/payload/`, licence in `NOTICE.txt`) |
| `dhcpc` | the DHCP client, ~120 KB |
| `wpa.conf` | SSID in hex, PMK only |
| `join.conf` | `IP=dhcp` (optionally `FALLBACK_IP` / `GW` / `MASK`) or a fixed `IP` / `GW` / `MASK` |
| `autorun.sh` | the payload |
