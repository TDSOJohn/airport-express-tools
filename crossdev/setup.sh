#!/bin/sh
# Fetches the NetBSD 4.0 sysroot that build.sh links against, into sysroot/ (no root needed):
# headers and static libraries from the sgimips (big-endian MIPS) comp set, plus <dev/usb/usb.h>,
# which that set leaves out. The compiler itself comes from Debian: sudo apt install gcc-mips-linux-gnu
set -eu
D=$(cd "$(dirname "$0")" && pwd)
cd "$D"

command -v mips-linux-gnu-gcc >/dev/null ||
	echo "note: build.sh also needs the cross compiler: sudo apt install gcc-mips-linux-gnu" >&2

if [ ! -f sysroot/usr/lib/libc.a ]; then
	mkdir -p dl sysroot
	[ -f dl/comp.tgz ] || curl -fL -o dl/comp.tgz \
	    https://archive.netbsd.org/pub/NetBSD-archive/NetBSD-4.0/sgimips/binary/sets/comp.tgz
	echo "7d9f7e877131fa0842976862ad570014683ceb7c8a9b44ec657825be18356dd9  dl/comp.tgz" | sha256sum -c -
	tar xzf dl/comp.tgz -C sysroot ./usr/include ./usr/lib
fi
# Created at install time on a real NetBSD system, not shipped in the set.
[ -e sysroot/usr/include/machine ] || ln -s sgimips sysroot/usr/include/machine
# USB ioctls (src/usbdevs.c), from the netbsd-4 branch that the Express's 4.0_STABLE kernel tracks.
H=sysroot/usr/include/dev/usb/usb.h
if [ ! -f $H ]; then
	curl -fL -o $H.tmp https://raw.githubusercontent.com/NetBSD/src/netbsd-4/sys/dev/usb/usb.h
	echo "46c7c3e74c1989a8b801b0d42c88b8e47fe67e359ccb645d10488b2aa57257b1  $H.tmp" | sha256sum -c -
	mv $H.tmp $H
fi

echo "sysroot ready"
