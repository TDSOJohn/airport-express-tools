#!/bin/sh
# Cross-compile a minimal WPA2-PSK wpa_supplicant for the AirPort Express
# (NetBSD 4.0_STABLE, AR7240 mipseb, o32, soft-float, static).
#
# Produces a static NetBSD-noted ELF that the device kernel will run, built from
# stock hostap 0.7.3, the first release whose driver_bsd.c speaks FreeBSD 8 (vap)
# net80211 (scan requests, APPIE) --- the 802.11 ABI Apple's kernel really has
# (0.6.5, the version Apple shipped, associates but can't scan or send its RSN IE).
# No edits to upstream source: compat/ shim headers fix the kernel ABI, compat/libc/
# replaces three libc.a objects (getifaddrs, soft-float setjmp, a getgrnam stub),
# compat/l2_packet/ adds a libpcap-free EAPOL backend, ldnetbsd.sh links.
# VERIFIED ON HARDWARE 2026-09-23: completes the WPA2-PSK 4-way handshake with a
# third-party AP (CTRL-EVENT-CONNECTED) from a managed vap on ath0. The small
# (raw-BPF) build below re-verified 2026-09-25 with join-test.sh: joins, pings, AirPlay.
#
# Prereqs: crossdev/setup.sh has populated ../sysroot (NetBSD 4.0 headers+libs),
#          Debian's gcc-mips-linux-gnu is installed.
#
# Output: wpa_supplicant-0.7.3/wpa_supplicant/wpa_supplicant  (stripped, ~295 KB)
#         .../wpa_supplicant.dbg                               (unstripped)
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
CROSSDEV=$(cd "$HERE/.." && pwd)
SR=$CROSSDEV/sysroot
DL=$CROSSDEV/dl
VER=0.7.3
TARBALL=wpa_supplicant-$VER.tar.gz
# sha256 of the official w1.fi release (fetched 2026-09-23)
SHA=d0cd50caa85346ccc376dcda5ed3c258eef19a93b3cade39d25760118ad59443
SRC=$HERE/wpa_supplicant-$VER

CC=mips-linux-gnu-gcc
command -v $CC >/dev/null || { echo "install: sudo apt install gcc-mips-linux-gnu" >&2; exit 1; }
[ -f "$SR/usr/lib/libc.a" ] || { echo "run $CROSSDEV/setup.sh first (sysroot missing)" >&2; exit 1; }

# 1. fetch + verify + extract -----------------------------------------------
mkdir -p "$DL"
if [ ! -f "$DL/$TARBALL" ]; then
	echo "fetching $TARBALL ..."
	curl -fsSL -o "$DL/$TARBALL" "https://w1.fi/releases/$TARBALL"
fi
echo "$SHA  $DL/$TARBALL" | sha256sum -c - || { echo "checksum mismatch" >&2; exit 1; }
[ -d "$SRC" ] || tar xzf "$DL/$TARBALL" -C "$HERE"
# NetBSD 4's getifaddrs.c, rebuilt below against compat/net/if.h (Apple's kernel
# if_msghdr is 8 bytes larger, so libc.a's copy returns empty names and
# if_nametoindex() fails for every interface).
GIA=$DL/getifaddrs-netbsd4.c
if [ ! -f "$GIA" ]; then
	curl -fsSL -o "$GIA" https://raw.githubusercontent.com/NetBSD/src/netbsd-4/lib/libc/net/getifaddrs.c
fi
echo "8879a0471bb5b41b120794f956bee315a2d1e2cd613280c3b84d930754767504  $GIA" | sha256sum -c - ||
	{ echo "getifaddrs.c checksum mismatch" >&2; exit 1; }

# 2. drop in the minimal PSK .config ----------------------------------------
# WPA2-PSK only: BSD net80211 driver, no 802.1X/EAP (so no eapol_sm, no OpenSSL).
# L2_PACKET=bpf is compat/l2_packet/l2_packet_bpf.c: EAPOL over raw /dev/bpf with a
# fixed filter. libpcap (L2_PACKET=freebsd) works too, but its filter compiler links
# libc's resolver, NIS, SunRPC and Berkeley DB statically: ~958 KB instead of ~295 KB.
# With no EAP, TLS=internal pulls in just tls_none + internal AES/SHA1/MD5/RC4 ---
# everything the 4-way handshake needs (0.7.3's TLS=none links no hash code at all).
cat > "$SRC/wpa_supplicant/.config" <<'EOF'
# AirPort Express (NetBSD 4.0 mipseb) minimal WPA2-PSK supplicant
CONFIG_DRIVER_BSD=y
CONFIG_L2_PACKET=bpf
CONFIG_TLS=internal
CONFIG_INTERNAL_LIBTOMMATH=y
CONFIG_CTRL_IFACE=y
CONFIG_BACKEND=file
EOF

# 3. compile + link ----------------------------------------------------------
# All target/sysroot flags ride in CC so the Makefile keeps building CFLAGS with its
# own -DCONFIG_* config defines and -I../src paths.
#   -U__linux__ ...  the Debian cross-gcc predefines __linux__; strip it so common.h
#                    and friends take the __NetBSD__ branch (sys/endian.h, not endian.h).
#   -D__NetBSD__     select NetBSD's SIOCS80211 etc. in net80211/ieee80211_ioctl.h.
#   -DCOMPAT_FREEBSD_NET80211  expose the FreeBSD-style IEEE80211_IOC_* the driver uses.
#   -isystem <gcc include> FIRST: use gcc 14's stdarg.h (__builtin_va_start), not
#                    NetBSD 4.0's (which calls __builtin_stdarg_start, gone from gcc 14).
#   -I compat        shim headers: net/ethernet.h -> net/if_ether.h,
#                    net80211/ieee80211_freebsd.h -> net80211/ieee80211_netbsd.h, and
#                    net/if.h, which resizes struct if_msghdr to the kernel's 152 bytes.
#                    net80211/ieee80211_ioctl.h: FreeBSD SIOC[SG]80211 numbers (Apple kernel).
#   -std=gnu89 -fcommon  let 2008-era C build under gcc 14.
GCCINC=$($CC -print-file-name=include)
XCC="$CC -EB -mabi=32 -march=mips1 -mtune=24kc -msoft-float -mabicalls -fPIC \
 -std=gnu89 -fcommon -nostdinc -I$HERE/compat -isystem $GCCINC -isystem $SR/usr/include \
 -U__linux__ -U__gnu_linux__ -U__linux -Ulinux -D__NetBSD__ -DCOMPAT_FREEBSD_NET80211"

# getifaddrs.o defines _getifaddrs/_freeifaddrs, the names libc's if_nametoindex.o
# calls, so the linker takes it instead of libc.a's getifaddrs.o.
GIAO=$HERE/compat/libc/getifaddrs.o
$XCC -O2 -I"$HERE/compat/libc" -c -o "$GIAO" "$GIA"
# libc.a's __setjmp14 saves FPU registers (traps: no FPU); libpcap's pcap_compile()
# calls it. This soft-float copy replaces it the same way. Only reached with
# L2_PACKET=freebsd; the bpf build doesn't call setjmp and --gc-sections drops it.
SJO=$HERE/compat/libc/setjmp_softfloat.o
$XCC -c -o "$SJO" "$HERE/compat/libc/setjmp_softfloat.S"
# libc.a's getgrnam() alone drags in NIS, hesiod, the resolver, SunRPC and Berkeley DB;
# the control interface calls it only for ctrl_interface_group, which we never set.
GGO=$HERE/compat/libc/getgrnam_stub.o
$XCC -Os -c -o "$GGO" "$HERE/compat/libc/getgrnam_stub.c"

# l2_packet over raw /dev/bpf: a new file, so upstream sources stay unedited.
cp "$HERE/compat/l2_packet/l2_packet_bpf.c" "$SRC/src/l2_packet/"

cd "$SRC/wpa_supplicant"
make clean >/dev/null 2>&1 || true
# CFLAGS from the environment: the Makefile sets it only if unset, then appends to it.
# -Os + per-function sections (ldnetbsd.sh links with --gc-sections) trim our own code;
# the 2007 libc.a/libpcap.a have no per-function sections, so that part stays as is.
CFLAGS="-MMD -Os -ffunction-sections -fdata-sections -Wall" \
	make -j"$(nproc)" wpa_supplicant CC="$XCC" LDO="$HERE/ldnetbsd.sh $GIAO $SJO $GGO"

cp wpa_supplicant wpa_supplicant.dbg
# .pdr/.comment/.ident are never loaded; plain strip keeps them (~100 KB).
mips-linux-gnu-strip -R .pdr -R .comment -R .ident -R .gnu.attributes wpa_supplicant
echo
echo "built: $SRC/wpa_supplicant/wpa_supplicant  ($(stat -c %s wpa_supplicant) bytes, stripped)"
file wpa_supplicant
