#!/bin/sh
# Offline run of airportctl/payload/autorun.sh with every device command stubbed, checking
# the order of operations that matters on the Express: no address before the first join in
# DHCP mode, the lease set on the live link, the re-key fallback (address -> down ->
# supplicant) when the router stays silent, one supplicant at a time, renewals, the
# fallback address, and the static path unchanged.
# Usage: tests/autorun-mock.sh   (needs sh, setsid, sed; takes ~15 s)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$HERE/../airportctl/payload/autorun.sh
fail=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }
has() { grep -qF -- "$2" "$R/calls" && ok "$1" || bad "$1"; }
hasnt() { grep -qF -- "$2" "$R/calls" && bad "$1" || ok "$1"; }
before() {	# name, first, second: first call's first line < second call's first line
	a=$(grep -nF -- "$2" "$R/calls" | head -1 | cut -d: -f1)
	b=$(grep -nF -- "$3" "$R/calls" | head -1 | cut -d: -f1)
	[ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ] && ok "$1" || bad "$1"
}

setup() {	# DHCP-MODE (ok|fail|change), join.conf content, [pings that fail first]
	R=$(mktemp -d)
	mkdir -p "$R/stub" "$R/Flash/autorun" "$R/Memory" "$R/wpa_own"
	echo "$1" > "$R/dhcp_mode"
	echo "${3:-0}" > "$R/ping_fail"
	printf '%s' "$2" > "$R/Flash/autorun/join.conf"
	: > "$R/calls"
	: > "$R/procs"
	: > "$R/Flash/autorun.try"
	sleep 1000 & echo $! > "$R/ACPd.pid"
	sleep 1000 & echo "$! /sbin/hostapd -t -F /var/log/hostap_wlan0.log" >> "$R/procs"
	sleep 1000 & echo "$! /sbin/airtunesd" >> "$R/procs"
	S=$R/stub
	printf '#!/bin/sh\necho "acp $*" >> %s/calls\n' "$R" > "$S/acp"
	cat > "$S/ping" <<EOF
#!/bin/sh
echo "ping \$*" >> $R/calls
[ \$(grep -c '^ping' $R/calls) -gt \$(cat $R/ping_fail) ]
EOF
	cat > "$S/ifconfig" <<EOF
#!/bin/sh
echo "ifconfig \$*" >> $R/calls
[ "\$*" = wlan2 ] && printf 'wlan2: flags=8843<UP>\n\tstatus: associated\n'
exit 0
EOF
	cat > "$S/ps" <<EOF
#!/bin/sh
echo "  PID COMMAND"
while read pid cmd; do kill -0 \$pid 2>/dev/null && echo "\$pid \$cmd"; done < $R/procs
EOF
	cat > "$S/airtunesd" <<EOF
#!/bin/sh
echo "airtunesd \$*" >> $R/calls
exec /bin/sleep 1000
EOF
	cat > "$S/sleep" <<'EOF'
#!/bin/sh
exec /bin/sleep 0.02
EOF
	cat > "$R/Flash/autorun/wpa_supplicant" <<EOF
#!/bin/sh
echo "wpa start" >> $R/calls
/bin/sleep 1000	# no exec: pgrep finds the supplicant by this script's path
EOF
	# dhcpc: "ok" leases .23; "change" leases .23, then .42 from the second renewal on
	cat > "$R/Flash/autorun/dhcpc" <<EOF
#!/bin/sh
echo "dhcpc \$*" >> $R/calls
n=\$(grep -c '^dhcpc' $R/calls)
mode=\$(cat $R/dhcp_mode)
[ \$mode = fail ] && exit 1
ip=192.168.1.23
[ \$mode = change ] && [ \$n -ge 3 ] && ip=192.168.1.42
echo DHCP_IP=\$ip; echo DHCP_MASK=255.255.255.0; echo DHCP_ROUTER=192.168.1.1
echo 'DHCP_DNS="192.168.1.1"'; echo DHCP_SERVER=192.168.1.1
echo DHCP_SERVER_MAC=aa:bb:cc:dd:ee:ff; echo DHCP_LEASE=600; echo DHCP_T1=300; echo DHCP_T2=525
EOF
	chmod +x "$S"/* "$R/Flash/autorun/wpa_supplicant" "$R/Flash/autorun/dhcpc"
	sed -e "s#^PATH=.*#PATH=$S:\$PATH#" \
	    -e "s#/mnt/Flash#$R/Flash#g" -e "s#/mnt/Memory#$R/Memory#g" \
	    -e "s#/var/run/ACPd.pid#$R/ACPd.pid#" -e "s#/var/run/wpa_own#$R/wpa_own#" \
	    -e "s#/sbin/ifconfig#$S/ifconfig#g" -e "s#/sbin/ping#$S/ping#g" \
	    -e "s#/sbin/airtunesd -i#$S/airtunesd -i#" -e "s#/bin/ps#$S/ps#" \
	    "$SRC" > "$R/autorun.sh"
}

run() {	# run the script in its own session; stop everything after $1 seconds
	setsid sh "$R/autorun.sh" < /dev/null > /dev/null 2>&1 &
	sid=$!
	/bin/sleep "$1"
	kill -- -$sid 2>/dev/null || true
	for f in "$R/ACPd.pid"; do kill $(cat $f) 2>/dev/null || true; done
	while read pid rest; do kill $pid 2>/dev/null || true; done < "$R/procs"
	pkill -f "$R/" 2>/dev/null || true
}

log_last() { tail -1 "$R/Memory/autorun.log"; }
wpa_live() { pgrep -f "$R/Flash/autorun/wpa_supplicant" | wc -l; }

echo "== DHCP, lease on the first try, then renewals that change the address"
setup change 'IP=dhcp
'
run 4
has    "joins, then asks for a lease" "dhcpc -t 30 wlan2"
hasnt  "no address before the first join" "ifconfig wlan2 inet 0"
before "no address before the lease" "dhcpc -t 30 wlan2" "ifconfig wlan2 inet"
before "leased address set, then the router pinged" "ifconfig wlan2 inet 192.168.1.23 netmask 255.255.255.0" "ping -c 1 -w 2 192.168.1.1"
[ "$(grep -c '^wpa start' "$R/calls")" = 1 ] && ok "router answers: no re-key" || bad "router answers: no re-key"
case "$(log_last)" in "joined, 192.168.1.23 via wlan2"*) ok "log: joined";; *) bad "log: $(log_last)";; esac
grep -q 'acp -q LEDc=2' "$R/calls" && ok "LED green" || bad "LED green"
[ ! -e "$R/Flash/autorun.try" ] && ok "autorun.try cleared" || bad "autorun.try cleared"
has    "renews by unicast to the server" "dhcpc -t 20 -c 192.168.1.23 -s 192.168.1.1 -m aa:bb:cc:dd:ee:ff wlan2"
has    "new address applied" "ifconfig wlan2 inet 192.168.1.42 netmask 255.255.255.0"
grep -q 'address changed from 192.168.1.23/255.255.255.0' "$R/Memory/dhcp.log" &&
	ok "dhcp.log records the change" || bad "dhcp.log records the change"
grep -q 'DHCP_IP=192.168.1.42' "$R/Memory/lease" && ok "lease file updated" || bad "lease file updated"
rm -rf "$R"

echo "== DHCP, router silent after the address -> re-key fallback"
setup ok 'IP=dhcp
' 5
run 3
[ "$(grep -c '^wpa start' "$R/calls")" = 2 ] && ok "supplicant restarted once" || bad "supplicant restarts: $(grep -c '^wpa start' "$R/calls")"
[ "$(grep -c 'ifconfig wlan2 inet 192.168.1.23' "$R/calls")" = 2 ] && ok "address set, then again in the re-key" || bad "address set count"
grep -A1 'inet 192.168.1.23' "$R/calls" | tail -1 | grep -qx 'ifconfig wlan2 down' &&
	ok "re-key: down right after the address" || bad "re-key: down right after the address"
grep -q 're-keying' "$R/Memory/autorun.log" && ok "log: re-keying" || bad "log: re-keying"
case "$(log_last)" in "joined, 192.168.1.23 via wlan2"*) ok "log: joined";; *) bad "log: $(log_last)";; esac
rm -rf "$R"

echo "== DHCP, one supplicant at a time, also after a renewal changes the address"
setup change 'IP=dhcp
'
setsid sh "$R/autorun.sh" < /dev/null > /dev/null 2>&1 &
sid=$!
/bin/sleep 2
grep -q 'inet 192.168.1.42' "$R/calls" && ok "new address applied" || bad "new address applied"
[ "$(wpa_live)" = 1 ] && ok "exactly one supplicant running" || bad "supplicants running: $(wpa_live)"
kill -- -$sid 2>/dev/null || true
run 0
rm -rf "$R"

echo "== DHCP fails, fallback address"
setup fail 'IP=dhcp
FALLBACK_IP=192.168.1.250
GW=192.168.1.1
MASK=255.255.255.0
'
run 2
has    "uses the fallback" "ifconfig wlan2 inet 192.168.1.250 netmask 255.255.255.0"
case "$(log_last)" in "joined, 192.168.1.250 via wlan2"*) ok "log: joined";; *) bad "log: $(log_last)";; esac
grep -q 'using the fallback address 192.168.1.250' "$R/Memory/autorun.log" && ok "log: fallback" || bad "log: fallback"
[ ! -e "$R/Memory/dhcp.log" ] && ok "no renew loop" || bad "no renew loop"
rm -rf "$R"

echo "== DHCP fails, no fallback"
setup fail 'IP=dhcp
'
run 2
case "$(log_last)" in "no DHCP lease on wlan2"*) ok "log: gave up";; *) bad "log: $(log_last)";; esac
grep -q 'acp -q LEDc=1' "$R/calls" && ok "LED amber" || bad "LED amber"
hasnt  "never pings" "ping"
rm -rf "$R"

echo "== fixed address (unchanged path)"
setup ok 'IP=192.168.1.250
GW=192.168.1.1
MASK=255.255.255.0
'
run 2
before "address before the only supplicant" "ifconfig wlan2 inet 192.168.1.250" "wpa start"
hasnt  "no DHCP" "dhcpc"
[ "$(grep -c '^wpa start' "$R/calls")" = 1 ] && ok "one supplicant start" || bad "one supplicant start"
case "$(log_last)" in "joined, 192.168.1.250 via wlan2"*) ok "log: joined";; *) bad "log: $(log_last)";; esac
rm -rf "$R"

[ $fail = 0 ] && echo "all passed" || exit 1
