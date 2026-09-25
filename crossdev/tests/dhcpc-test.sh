#!/bin/sh
# Offline test of src/dhcpc.c's DHCP logic: builds it for this Linux machine (the BSD
# /dev/bpf parts swapped for tests/dhcpc_linux.h) and runs it against busybox udhcpd over a
# veth pair, inside a throwaway user+network namespace (no root, no real network touched).
# Checks INIT, INIT-REBOOT, RENEWING (unicast), REBINDING (broadcast), a NAK and a timeout.
# Needs: cc, busybox (with udhcpd), unshare, ip.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
if [ "${1:-}" != --inside ]; then
	T=$(mktemp -d)
	trap 'rm -rf "$T"' EXIT
	cc -O2 -Wall -DDHCPC_TEST="\"$HERE/dhcpc_linux.h\"" -o "$T/dhcpc" "$HERE/../src/dhcpc.c"
	unshare -rn sh "$0" --inside "$T"
	exit
fi
T=$2
# The client end gets its own namespace: with both ends in one, the kernel would deliver
# unicast between them locally instead of over the veth.
unshare -n sleep 600 &
CNS=$!
sleep 0.2
C="nsenter -t $CNS -n"
ip link add srv type veth peer name cli
ip link set cli netns $CNS
ip addr add 192.168.77.1/24 dev srv
ip link set srv up
$C ip link set cli up
cat > "$T/udhcpd.conf" <<EOF
start 192.168.77.100
end 192.168.77.110
interface srv
lease_file $T/leases
pidfile $T/udhcpd.pid
option subnet 255.255.255.0
option router 192.168.77.1
option dns 192.168.77.1 9.9.9.9
option lease 600
EOF
: > "$T/leases"
busybox udhcpd -f "$T/udhcpd.conf" > "$T/udhcpd.log" 2>&1 &
UD=$!
trap 'kill $UD $CNS 2>/dev/null || true' EXIT
sleep 1

fail=0
check() {	# name, expected exit, command...
	name=$1 want=$2
	shift 2
	set +e
	"$@" > "$T/out" 2> "$T/err"
	got=$?
	set -e
	if [ $got = $want ]; then echo "ok   $name"; else echo "FAIL $name (exit $got, want $want)"; fail=1; fi
	sed 's/^/     /' "$T/out" "$T/err"
}

check "INIT (discover/offer/request/ack)" 0 $C "$T/dhcpc" -t 10 -h test-express cli
. "$T/out"
[ "$DHCP_MASK" = 255.255.255.0 ] && [ "$DHCP_ROUTER" = 192.168.77.1 ] &&
	[ "$DHCP_SERVER" = 192.168.77.1 ] && [ "$DHCP_LEASE" = 600 ] &&
	[ "$DHCP_DNS" = "192.168.77.1 9.9.9.9" ] &&
	[ "$DHCP_SERVER_MAC" = "$(ip -o link show srv | sed 's/.*link.ether \([^ ]*\).*/\1/')" ] ||
	{ echo "FAIL lease fields"; fail=1; }
LEASED=$DHCP_IP

check "INIT-REBOOT for the same address" 0 $C "$T/dhcpc" -t 10 -r "$LEASED" cli
. "$T/out"; [ "$DHCP_IP" = "$LEASED" ] || { echo "FAIL reboot address"; fail=1; }

# Renewals come from the leased address, as on the Express after the re-key.
$C ip addr add "$LEASED/24" dev cli
check "RENEWING (unicast to the server)" 0 \
	$C "$T/dhcpc" -t 10 -c "$LEASED" -s "$DHCP_SERVER" -m "$DHCP_SERVER_MAC" cli
. "$T/out"; [ "$DHCP_IP" = "$LEASED" ] || { echo "FAIL renew address"; fail=1; }
check "REBINDING (broadcast)" 0 $C "$T/dhcpc" -t 10 -c "$LEASED" cli
check "INIT-REBOOT for a foreign address -> NAK" 2 $C "$T/dhcpc" -t 10 -r 10.9.9.9 cli
kill $UD; wait $UD 2>/dev/null || true
check "no server -> timeout" 1 $C "$T/dhcpc" -t 3 cli

[ $fail = 0 ] && echo "all passed" || { echo "--- udhcpd log"; cat "$T/udhcpd.log"; exit 1; }
