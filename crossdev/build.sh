#!/bin/sh
# Cross-compiles C for the AirPort Express (NetBSD 4.0_STABLE, mipseb, o32) into a static ELF.
# Usage: ./build.sh [--raw] SRC.c [OUT] [EXTRA CC ARGS...]
#   default  static NetBSD 4.0 libc (stdio, sockets, ...): ~100 KB for hello world
#   --raw    freestanding, no libc: SRC provides __start, syscalls and the NetBSD note (see src/hello_raw.c)
# OUT defaults to build/<name>. Needs the gcc-mips-linux-gnu package; run setup.sh once first.
set -eu
D=$(cd "$(dirname "$0")" && pwd)
SR=$D/sysroot
CC=mips-linux-gnu-gcc
command -v $CC >/dev/null || { echo "install the cross compiler: sudo apt install gcc-mips-linux-gnu" >&2; exit 1; }

raw=0
[ "${1:-}" = --raw ] && { raw=1; shift; }
src=${1:?usage: build.sh [--raw] SRC.c [OUT] [EXTRA CC ARGS...]}
shift
out=${1:-$D/build/$(basename "${src%.c}")}
[ $# -gt 0 ] && shift
mkdir -p "$(dirname "$out")"

# MIPS-I like Apple's own binaries; the kernel only runs NetBSD-noted ELF, and --build-id's
# extra note is left out to keep the NetBSD one easy to find.
COMMON="-EB -mabi=32 -march=mips1 -mtune=24kc -static -no-pie -Wl,--build-id=none -Wl,-e,__start"

if [ $raw = 1 ]; then
	$CC $COMMON -msoft-float -mno-abicalls -fno-pic -G0 -Os -ffreestanding -fno-builtin -nostdlib \
	    -o "$out" "$src" "$@" -lgcc
else
	[ -f "$SR/usr/lib/libc.a" ] || { echo "run $D/setup.sh first" >&2; exit 1; }
	# The NetBSD 4.0 libraries are PIC (abicalls) mips1: match that. The kernel has no FPU
	# emulation and no soft-float helpers are available, so user code is soft-float: float
	# arithmetic fails to link (undefined __muldf3 ...) instead of crashing at run time.
	# libc's own float code (printf %f, strtod, libm) is hard-float and still crashes.
	L=$SR/usr/lib
	$CC $COMMON -msoft-float -mabicalls -fPIC -O2 -nostdinc -isystem "$SR/usr/include" -nostdlib \
	    -o "$out" "$L/crt0.o" "$L/crti.o" "$L/crtbeginT.o" "$src" "$@" \
	    -L"$L" -Wl,--start-group -lc -lgcc -Wl,--end-group "$L/crtend.o" "$L/crtn.o"
fi
echo "$out: $(stat -c %s "$out") bytes"
