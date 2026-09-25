#!/bin/sh
# LDO wrapper: link objects into a static NetBSD 4.0 mipseb ELF using the crossdev
# sysroot crt files + libc.a (like crossdev/build.sh). Passes -l libs into the group.
set -eu
SR=$(cd "$(dirname "$0")/../sysroot" && pwd)
L=$SR/usr/lib
COMMON="-EB -mabi=32 -march=mips1 -mtune=24kc -static -no-pie -Wl,--build-id=none -Wl,--gc-sections -Wl,-e,__start -msoft-float -mabicalls -fPIC"
out=""; objs=""; libs=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out=$2; shift 2 ;;
    *.o) objs="$objs $1"; shift ;;
    -l*) libs="$libs $1"; shift ;;
    *) shift ;;                       # drop -L/-Wl/other LDFLAGS: we supply our own
  esac
done
[ -n "$out" ] || { echo "ldnetbsd: no -o target" >&2; exit 2; }
set -x
exec mips-linux-gnu-gcc $COMMON -nostdlib -o "$out" \
  "$L/crt0.o" "$L/crti.o" "$L/crtbeginT.o" $objs \
  -L"$L" -Wl,--start-group -lc -lgcc $libs -Wl,--end-group "$L/crtend.o" "$L/crtn.o"
