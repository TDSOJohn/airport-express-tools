#!/bin/sh
# Builds src/dhcpc.c (the DHCP client `airportctl join` uses) into build/dhcpc, stripped the
# same way as wpa_supplicant (.pdr/.comment/.ident are never loaded). Run setup.sh once first.
# The unstripped binary is left at build/dhcpc.dbg. The logic is tested offline by
# tests/dhcpc-test.sh.
set -eu
D=$(cd "$(dirname "$0")" && pwd)
"$D/build.sh" "$D/src/dhcpc.c" "$D/build/dhcpc.dbg" -I"$D/wpa-build/compat" -Os -Wall
mips-linux-gnu-strip -R .pdr -R .comment -R .ident -R .gnu.attributes \
	-o "$D/build/dhcpc" "$D/build/dhcpc.dbg"
echo "$D/build/dhcpc: $(stat -c %s "$D/build/dhcpc") bytes, sha256 $(sha256sum < "$D/build/dhcpc" | cut -d' ' -f1)"
