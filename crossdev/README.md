# crossdev: C for the AirPort Express (A1392)

Cross-compile static NetBSD 4.0 / mipseb binaries on Linux and run them on the A1392.
armeb models (A1254, A1301) are not covered yet.

```sh
sudo apt install gcc-mips-linux-gnu   # once: the cross compiler
./setup.sh                            # once: NetBSD 4.0 headers and libraries into sysroot/
./build.sh src/hello.c                # static NetBSD 4.0 binary -> build/hello
./run.sh build/hello foo "bar baz"    # copy to the Express's RAM disk over SSH and run it
```

Needs the debug SSH login ([dbug.md](../docs/dbug.md)) and a cable to the LAN port.

## Target

| | |
|---|---|
| OS | NetBSD 4.0_STABLE (Apple build, May 2019), `kern.osrevision` 400000003 |
| CPU | Atheros AR9344, MIPS 74Kc (kernel reports `ar7240`), big-endian `mipseb`; **no FPU and no FPU emulation** |
| Memory | 64 MB RAM, ~15 MB free; per-process limits: memory ~46 MB, stack 2 MB |
| Userland | one 10 MB static crunched binary (`sh`, `ls`, `ACPd`, … are hard links); ELF32 MIPS-I o32, non-PIC, soft-float |
| Dynamic linking | none (no `ld.elf_so`, no shared libraries): **binaries must be static** |
| ELF note | the kernel refuses an executable without a `.note.netbsd.ident` note |
| Kernel | filesystems `mfs ffs procfs kernfs fdesc`; USB drivers: host controller, hub, printer only; no module loader |
| Writable space | `/mnt/Memory` ~15 MB RAM disk, wiped at reboot (used by `run.sh`); `/` RAM disk, 732 KB free; `/mnt/Flash` ~988 KB free, persistent ([below](#storage-usb-and-persistence)) |
| On-device tools | `sh cat chmod sed tail sort curl scp tcpdump iperf openssl`; no `grep` / `head`; `/sbin` not in `PATH` |

## Toolchain options

| Option | Result |
|---|---|
| **Debian `gcc-mips-linux-gnu` + NetBSD 4.0 sgimips libc, static** | **used**: full libc with the kernel's exact syscall ABI; hello world 100 KB |
| same compiler, freestanding (`build.sh --raw`) | works, no libc; hello world 2 KB |
| NetBSD 4.0 `evbmips` sets | wrong endianness (4.0 `evbmips` is little-endian; `sgimips` is big-endian) |
| libc from NetBSD ≥ 5.0 | not tried; uses versioned syscalls (64-bit `time_t`) a 4.0 kernel lacks |
| glibc, musl, uClibc | Linux syscall ABI: don't run |
| zig, clang + lld | not tried; GNU ld is safer for NetBSD 4.0's old PIC `libc.a` |
| NetBSD `build.sh tools` (`mipseb--netbsd`) | heavier; for C++ or large ports. Recipe: [Embedded Ideation 2016](https://www.embeddedideation.com/2016/04/24/airport-hacking-update/) (easiest from an old host, e.g. an Ubuntu 7.04 VM) |
| on the device | no compiler, 732 KB free on `/` |

## Storage, USB and persistence

| | |
|---|---|
| USB storage | impossible with this kernel: attach functions only for EHCI, hub and `ulpt`; no `umass`/`sd`/`scsibus`, `ugen`, `uhid`, `ucom`; no module loader; no FAT/NFS. (`sysctl kern.drivers` lists more, but that is the reserved device-number table.) `src/usbdevs.c`: one EHCI root hub, one port |
| USB data path | `ulpt` only: a two-way pipe to anything that enumerates as a printer (e.g. a Linux printer gadget → `/dev/ulpt0`). Not tried; Apple's `printd` also uses it |
| Network | full sockets in libc, `curl` on the device: keep data on another host, fetch into `/mnt/Memory` |
| `/mnt/Flash` (`/dev/flash2a`, FFS, `rw,noatime,sync`) | ~988 KB free next to `ACPData.bin` and the sshd host keys. Files survive soft reboots and power cuts, including mid-write (the file being written comes back empty; filesystem consistent, nothing else changed) (L) |
| `/mnt/Flash` failure mode | at boot `rc.d/flash` runs `fsck -y`; if the mount still fails it **erases and reformats** the partition: all settings (Wi-Fi, admin password, `dbug` → SSH off) and host keys lost. Back up its files first |
| `/mnt/Flash` writes | sustained writes block SSH logins for minutes (sshd reads the host keys from it per login; ping and ACP unaffected). Write rarely and small; leave headroom for ACPd. ACPd rewrites `ACPData.bin` at boot (header checksum + a few bytes): compare settings, not hashes. No `gzip` / `zcat` on the device |
| Autostart | none: boot runs `/etc/rc.d/*` and cron from the firmware image only. Start programs over SSH, or use the [autorun image](../docs/autorun.md) |

### Running more code than fits in RAM

| Approach | Notes |
|---|---|
| Kernel demand paging | pages only from a local file; the only writable filesystems are RAM-backed or the 1 MB flash, and there is no NFS |
| Stream data | a small static program with data flowing through a socket (how AirPlay works) |
| Exec-chain stages | fetch a stage into `/mnt/Memory`, run, exit, fetch the next; one stage resident at a time |
| Code overlays (`src/overlay.c`, verified) | `mmap` a buffer, load a chunk, `sysarch(MIPS_CACHEFLUSH)` (mandatory on MIPS), `mprotect` executable, call it; relocations to libc/globals are your job. `mmap(PROT_EXEC)`, `mprotect`, cache flush all work |

## Scripts

| Script | Does |
|---|---|
| `setup.sh` | fetches NetBSD 4.0 sgimips `comp.tgz` (sha256-checked), extracts `usr/include` + `usr/lib` into `sysroot/`; adds the `machine -> sgimips` symlink and `dev/usb/usb.h` from the `netbsd-4` branch (sha256-pinned; the 4.0 release tag's copy differs) |
| `build.sh SRC.c [OUT] [EXTRA CC ARGS]` | `mips-linux-gnu-gcc -EB -mabi=32 -march=mips1 -static -no-pie -Wl,--build-id=none` |
| `run.sh BINARY [ARGS]` | `cat` the binary over SSH into `/mnt/Memory/<name>`, `chmod`, run with `ulimit -c 0`; returns the program's exit status; the file stays until reboot |
| `build-dhcpc.sh` | builds `src/dhcpc.c` |
| `../tools/essh.sh 'cmd'` | one command over SSH with the legacy algorithms ([extracting-acpd.md](../docs/extracting-acpd.md#enable-ssh)) |

| `build.sh` mode | Flags | Link |
|---|---|---|
| libc (default) | `-mabicalls -fPIC -msoft-float -nostdinc -isystem sysroot/usr/include` | `crt0.o crti.o crtbeginT.o <code> -lc -lgcc crtend.o crtn.o` (`crt0.o` carries the NetBSD note); extra libs (`-lutil`, `-lpthread`) after `OUT` |
| `--raw` | `-ffreestanding -nostdlib -mno-abicalls -fno-pic -G0 -msoft-float` | none: provide the NetBSD note, syscall stubs (number in `v0`, args `a0`–`a2`, `syscall`; `a3 != 0` → `v0` is errno) and `__start` (initial stack pointer in `sp` and `a0`); see `src/hello_raw.c` |

## Floating point

| | |
|---|---|
| Hard float | crashes: first FPU instruction → "coprocessor 1 unusable" (exception 11, `cause 0x1000002c`). Apple's userland has no FPU instructions (soft-float) |
| Soft-float helpers | none available: Debian's `libgcc` `__adddf3`, `__muldf3`, … use FPU opcodes; NetBSD 4.0's `libgcc` lacks them |
| `build.sh` | compiles with `-msoft-float`: float arithmetic **fails to link** (`undefined reference to '__muldf3'`) instead of crashing. libc's `printf("%f")`, `strtod`, `libm` are hard-float and still crash if reached |
| To enable | build a soft-float runtime (e.g. LLVM compiler-rt builtins `adddf3.c`, `muldf3.c`, …) with `-msoft-float`; avoid or replace libc's float functions |

## Layout

| Path | Contents |
|---|---|
| `setup.sh`, `build.sh`, `run.sh` | the scripts above |
| `src/hello.c`, `src/hello_raw.c`, `src/usbdevs.c` | libc, freestanding and USB-listing examples (all verified on the device) |
| `src/overlay.c` | runtime code loading into an `mmap`'d buffer (verified) |
| `src/fptest.c` | the floating-point test (no longer links) |
| `src/ifstat.c` | per-interface packet counters (no `netstat` on the device); needs `wpa-build`'s `getifaddrs` fix |
| `src/dhcpc.c`, `build-dhcpc.sh` | the one-shot DHCP client used by `airportctl join` ([join-mode.md](../docs/join-mode.md#addressing-dhcp)) |
| `tests/dhcpc-test.sh`, `tests/dhcpc_linux.h` | `dhcpc` logic against busybox `udhcpd` in a user + network namespace (no root) |
| `wpa-build/` | the replacement `wpa_supplicant` ([README](wpa-build/README.md)) |
| `sysroot/`, `dl/comp.tgz`, `build/` | fetched / built, not in git |
