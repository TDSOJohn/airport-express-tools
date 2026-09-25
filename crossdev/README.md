# Cross-compiling C for the AirPort Express (A1392)

Compile on this laptop, run on the Express. Set up and verified on the device on 2026-09-15.

```sh
sudo apt install gcc-mips-linux-gnu   # once: the cross compiler
./setup.sh                            # once: NetBSD 4.0 headers and libraries into sysroot/
./build.sh src/hello.c                # static NetBSD 4.0 binary -> build/hello
./run.sh build/hello foo "bar baz"    # copy to the Express's RAM disk over SSH and run it
```

Needs the Express powered on, `nmcli c up airport-probe`, and its debug SSH on (`dbug=0x3000`,
root / `public` — a root shell for anyone on its network, so turn it off when done).

Verified output:

```
Hello from the AirPort Express! (static NetBSD 4.0 libc)
  NetBSD 4.0_STABLE on ar7240, pid 669
```

## The target

| | |
|---|---|
| OS | NetBSD 4.0_STABLE (Apple build, May 2019), `kern.osrevision` 400000003 |
| CPU | Atheros AR7240 (MIPS 24Kc), big-endian `mipseb`, **no FPU and no FPU emulation in the kernel** |
| Memory | 64 MB RAM, about 15 MB free; per-process limits: memory ~46 MB, stack 2 MB |
| Userland | a single 10 MB static crunched binary (`sh`, `ls`, `ACPd`, … are hard links), ELF32 MIPS-I o32, non-PIC, soft-float |
| Dynamic linking | none: no `ld.elf_so`, no shared libraries, so **binaries must be static** |
| Kernel | filesystems `mfs ffs procfs kernfs fdesc` only; USB drivers for the host controller, hub and printers only; no module loader |
| Writable space | `/mnt/Memory`: ~15 MB RAM disk, wiped on reboot (`run.sh` uses it). `/`: RAM disk, 732 KB free, rebuilt at every boot. `/mnt/Flash`: 1 MB flash that survives power-off (see [Storage](#storage-usb-and-persistence)) |
| On-device tools | `sh cat chmod sed tail sort curl scp tcpdump iperf openssl`; no `grep`/`head`; `/sbin` isn't in `PATH` |

The kernel also refuses a native ELF executable unless it carries a `.note.netbsd.ident` note.

## Options considered

| Option | Verdict |
|---|---|
| **Debian's `gcc-mips-linux-gnu` + NetBSD 4.0 libc** (sgimips `comp.tgz`), static | **Used.** Full libc (stdio, sockets, …) with the exact syscall ABI of the device's kernel. Hello world is 100 KB. |
| Same compiler, freestanding (`build.sh --raw`) | Works. Hello world is 2 KB. No libc: raw syscalls and your own `__start`. For tiny tools. |
| NetBSD 4.0 `evbmips` sets | Wrong endianness: the 4.0 `evbmips` release is little-endian. `sgimips` is the big-endian one. |
| libc from a newer NetBSD | Not tried. From 5.0 on, libc calls versioned syscalls (e.g. the 64-bit `time_t` ones) that a 4.0 kernel lacks. |
| Linux toolchain libcs (glibc, musl, uClibc) | Linux syscall ABI, so they don't run. Only the compiler is useful, for freestanding code. |
| zig or clang + lld | Not tried. Fine for freestanding code in principle; GNU ld is the safer linker for NetBSD 4.0's old PIC `libc.a`. |
| A real `mipseb--netbsd` toolchain via NetBSD's `build.sh tools` | Heavier (full NetBSD source tree). Only worth it for C++ or large ports. |
| Compiling on the device | No compiler, 732 KB free on `/`, 64 MB RAM. |

## Storage, USB and persistence

Checked on 2026-09-15. Re-check on your own unit with `../tools/essh.sh`; the useful source is the running kernel's
symbol table (`ksyms.bin`, read from `/dev/ksyms`).

- **USB storage is impossible with this kernel.** Its symbol table has attach functions for only three
  USB drivers: the EHCI host controller, the hub and the printer driver (`ulpt`). There's nothing for
  mass storage (`umass`, `sd`, `scsibus`), generic USB access (`ugen`, which would allow a userspace
  driver), HID (`uhid`) or USB serial (`ucom`). There's no module loader to add one, and the only
  filesystems are `mfs ffs procfs kernfs fdesc`: no FAT, no NFS. `sysctl kern.drivers` does list `ugen`,
  `sd` and so on, but that's only the table of reserved device numbers (it lists PCI RAID cards too).
  `src/usbdevs.c` lists what's on the port: one EHCI root hub with one port, nothing attached.
- **The only USB data path is `ulpt`**, which is a two-way pipe to anything that identifies itself as a
  printer. A board running as a USB printer gadget (for example a Raspberry Pi Zero with Linux's printer
  gadget) would show up as `/dev/ulpt0`. A small protocol over it could then serve files from the board's
  SD card. Not tried; Apple's print server `printd` also uses the device.
- **The network is the practical store.** Programs get full sockets from libc, and `curl` is on the
  Express. Data can live on the laptop or a NAS and be fetched into `/mnt/Memory` when needed. Free RAM
  (~15 MB) limits how much can be held at once.
- **`/mnt/Flash` keeps your files, even through power cuts.** It's FFS on `/dev/flash2a`, mounted
  `rw,noatime,sync`, with ~988 KB free next to `ACPData.bin` (ACPd's saved settings) and the `sshd` host
  keys. Tested on 2026-09-25: files written there came back byte-identical after a soft reboot, after
  pulling the plug while idle, and after pulling it during a loop that kept rewriting a 512 KB file. That
  file came back empty (the write in progress was lost), but the filesystem was consistent, nothing else
  changed and the partition wasn't reformatted. Things to know:
  - At boot `rc.d/flash` runs `fsck -y`, and if the mount still fails it **erases and reformats the
    partition**, losing all settings (Wi-Fi, admin password, `dbug`, so SSH goes off) and the host keys.
    It didn't happen in testing, but back up the files first (`cat` each one over `../tools/essh.sh`).
  - **Sustained writes block SSH logins.** While the 512 KB rewrite loop ran, `sshd` sent its banner but
    hung before authentication for minutes (it reads the host keys from `/mnt/Flash` for every login);
    ping and ACP kept working. Write rarely, and keep writes small.
  - ACPd rewrites `ACPData.bin` at boot (a header checksum and a few bytes change), so check it by
    reading the settings back, not by comparing hashes.
  - Leave headroom so ACPd can keep saving. There is no `gzip`/`zcat` on the device to unpack a
    compressed payload.
- **Nothing starts automatically.** Boot runs `/etc/rc.d/*` and cron from the firmware image; no script
  touches `/mnt/Flash` except to check and mount it. After every reboot a program has to be started over
  SSH (for example with `run.sh`).

### Streaming code at runtime, to beat the ~15 MB ceiling

"Streaming a program" splits two ways:

- **The kernel already demand-pages code, but only from a local file.** `exec` faults a binary's text in page
  by page from its backing file and can drop and re-read clean pages, so a running program's code is not all
  resident. But the file must be on a filesystem the kernel can page from, and the only writable ones here are
  RAM-backed (paging from RAM saves nothing) or the 1 MB flash. There is **no NFS**, so the kernel cannot page
  code across the cable — the diskless "exec off a network share" trick is unavailable.
- **Streaming from the network you do yourself**, at one of three granularities, cheapest first:
  1. **Stream data** through a small static program (what most useful things want; the AirPlay path works this
     way). The program stays tiny; data flows through it from a socket.
  2. **Exec-chain stages**: fetch stage into `/mnt/Memory`, run it, let it exit, fetch the next. Only one stage
     is resident at a time; each is an ordinary static binary. Simplest and most robust; the natural fit for a
     small loader in flash that pulls bigger programs from the laptop.
  3. **Code overlays** (`src/overlay.c`, verified on the device): a resident process pulls code chunks into an
     `mmap`'d buffer, syncs the caches (`sysarch(MIPS_CACHEFLUSH)` — on MIPS you *must*, or the CPU runs stale
     bytes), `mprotect`s the buffer executable, calls it, then reuses it. Only worth it for one long-lived
     process that must run more code than fits in RAM; you carve the program into self-contained chunks and
     handle relocations to libc/globals yourself. `mmap(PROT_EXEC)`/`mprotect`/`cacheflush` all work.

## How it works

**`setup.sh`** fetches NetBSD 4.0's sgimips `comp.tgz` (checked against its sha256) and extracts
`usr/include` and `usr/lib` into `sysroot/`. It then:

- creates `sysroot/usr/include/machine -> sgimips`, a symlink a real NetBSD install creates but the set
  doesn't ship;
- adds `dev/usb/usb.h`, which the set leaves out, from the NetBSD source tree's `netbsd-4` branch
  (sha256-pinned). This matches the kernel's 4.0_STABLE and is the copy that was tested; the 4.0 release
  tag's copy differs.

**`build.sh SRC.c [OUT] [EXTRA CC ARGS]`** uses Debian's `mips-linux-gnu-gcc` and always passes
`-EB -mabi=32 -march=mips1 -static -no-pie -Wl,--build-id=none`, matching Apple's own binaries.

- Default (libc): `-mabicalls -fPIC` (the NetBSD 4.0 libraries are PIC), `-msoft-float`, and
  `-nostdinc -isystem sysroot/usr/include`. It links
  `crt0.o crti.o crtbeginT.o <your code> -lc -lgcc crtend.o crtn.o`, and `crt0.o` supplies the NetBSD note.
  Extra arguments such as `-lutil` or `-lpthread` go after `OUT`.
- `--raw`: `-ffreestanding -nostdlib -mno-abicalls -fno-pic -G0 -msoft-float`. `src/hello_raw.c` shows the
  three things libc normally provides:
  - the NetBSD note;
  - a syscall stub: number in `v0`, arguments in `a0`–`a2`, then `syscall`; on return `a3 != 0` means
    `v0` holds the errno;
  - `__start`: the kernel puts the initial stack pointer (argc, argv…) in both `sp` and `a0`.

**`run.sh BINARY [ARGS]`** pipes the binary over SSH with `cat` into `/mnt/Memory/<name>`, makes it
executable, and runs it with `ulimit -c 0`. It exits with the program's status. The file stays on the
Express until it reboots.

**`../tools/essh.sh 'command'`** runs one command over SSH with the legacy algorithms the Express's
OpenSSH requires. It takes the password from `askpass.sh` (`public`, override with `AIRPORT_PW`) and the
host from `AIRPORT_HOST`. It keeps its own known-hosts file, `tools/.airport_known_hosts`. The debug
shell has to be enabled first — see [../docs/extracting-acpd.md](../docs/extracting-acpd.md).

## Floating point: not available yet

- `src/fptest.c`, built hard-float, died with SIGSEGV at its first FPU instruction. In the kernel's
  register dump, `pc` and `badvaddr` are both `0x004001a4` (`lwc1 $f0`), and `cause` is `0x1000002c`:
  exception 11, "coprocessor 1 unusable". The kernel has no FPU emulation. Apple's `ACPd` contains no
  FPU instructions at all (1.9 million disassembled lines), so Apple built the userland soft-float.
- No soft-float helpers are available. Debian's `libgcc` `__adddf3`, `__muldf3`, … are hard-float wrappers
  that use FPU opcodes themselves, and the NetBSD 4.0 `libgcc` doesn't have them.
- So `build.sh` compiles your code with `-msoft-float`. Float arithmetic then **fails to link**
  (`undefined reference to '__muldf3'`) instead of crashing on the Express. The libc's own float code
  (`printf("%f")`, `strtod`, `libm`) is hard-float and still crashes if your code reaches it.
- To enable floats: build a soft-float runtime, for example LLVM compiler-rt's builtins (`adddf3.c`,
  `muldf3.c`, … are plain C), with `-msoft-float` into a static library, and avoid or replace the
  libc's float functions.

## Layout

| Path | Contents |
|---|---|
| `setup.sh`, `build.sh`, `run.sh` | the tools above (`run.sh` uses `../tools/essh.sh`) |
| `src/hello.c`, `src/hello_raw.c`, `src/usbdevs.c` | libc, freestanding and USB-listing programs, all verified on the device |
| `src/overlay.c` | loads and runs machine code into an `mmap`'d buffer at runtime (the streaming primitive), verified |
| `src/fptest.c` | the floating-point test (kept for the record; no longer links) |
| `src/ifstat.c` | per-interface packet counters (no `netstat` on the device); needs `wpa-build`'s `getifaddrs` fix, see its header |
| `wpa-build/` | a replacement `wpa_supplicant` that joins WPA2 networks, plus the kernel-ABI shims it needed — see its [README](wpa-build/README.md) |
| `sysroot/`, `dl/comp.tgz` | NetBSD 4.0 sgimips headers and static libraries, fetched by `setup.sh` (not in git) |
| `build/` | build output (not in git) |
