#!/bin/sh
# /mnt/Flash/autorun.sh: started at boot by the /etc/rc hook (docs/autorun.md), or by
# `airportctl join start`. Installed by `airportctl join install` (airportctl/join.py).
#
# Joins the 2.4 GHz radio to the WPA2 network in autorun/wpa.conf with our own
# wpa_supplicant and moves AirPlay onto it: the same steps as
# crossdev/wpa-build/join-test.sh, where each one is explained. The 5 GHz AP stays up.
# Log goes to RAM (/mnt/Memory/autorun.log): sustained Flash writes stall sshd logins.
#
# The address comes from DHCP (IP=dhcp in join.conf) or is fixed (IP= GW= MASK=).
# With DHCP: associate without an address, get a lease with our dhcpc (it only reports the
# lease), then set it on the live link: adding, replacing or removing an address keeps the
# WPA keys (tested 2026-09-25, docs/join-mode.md). If the router still doesn't answer, the
# supplicant is restarted with the address already on (`rekey`) as a fallback. A background
# loop renews the lease (log: /mnt/Memory/dhcp.log) and applies a changed address the same way.
# If no DHCP server answers, FALLBACK_IP (with GW, MASK) is used when join.conf has one.
#
# Clears /mnt/Flash/autorun.try when it finishes, joined or not. Only a hang or a
# reboot before that point leaves .try behind, which makes the hook disable autorun.
#
# Front LED (ACP property LEDc via the on-device `acp` tool): ACPd's own status while
# it works, then solid green once joined, solid amber if the join failed. ACPd itself
# only watches the Ethernet WAN, so without this it blinks amber even when we're joined.
PATH=/sbin:/usr/sbin:/bin:/usr/bin
D=/mnt/Flash/autorun
M=/mnt/Memory
exec > $M/autorun.log 2>&1
echo "autorun start $(date)"
. $D/join.conf			# IP=dhcp [FALLBACK_IP= GW= MASK=], or IP= GW= [MASK=]
MASK=${MASK:-255.255.255.0}

pids() { /bin/ps ax | while read pid rest; do case "$rest" in *$1*) echo $pid;; esac; done; }
finish() { echo "$1 $(date)"; rm -f /mnt/Flash/autorun.try; exit 0; }
led() { acp -q LEDc=$1; }	# 0 ACPd's status, 1 amber, 2 green
start_wpa() {
	$D/wpa_supplicant -t -D bsd -i wlan2 -c $D/wpa.conf > $M/wpa.log 2>&1 &
	echo $! > $M/wpa.pid
}
stop_wpa() {	# and wait, so the new one can take the control socket
	pid=$(cat $M/wpa.pid)
	kill $pid 2>/dev/null
	n=0
	while kill -0 $pid 2>/dev/null && [ $n -lt 10 ]; do sleep 1; n=$((n + 1)); done
	rm -f /var/run/wpa_own/wlan2
}
# Fallback when the router stays silent after an address change (not seen so far): a fresh
# handshake with the address already on. Address, then down, then the supplicant: 0.7.3
# would take the IFF_UP clear during its init as the interface going away.
rekey() {	# ADDRESS NETMASK
	kill -STOP $ACPD
	stop_wpa
	/sbin/ifconfig wlan2 inet $1 netmask $2
	/sbin/ifconfig wlan2 down
	start_wpa
	sleep 3
	kill -CONT $ACPD
}
apply() {	# ADDRESS NETMASK ROUTER: set it on the live link; re-key only if the router is silent
	/sbin/ifconfig wlan2 inet $1 netmask $2
	n=0
	until /sbin/ping -c 1 -w 2 $3 > /dev/null 2>&1; do
		n=$((n + 1))
		[ $n -ge 5 ] && { echo "no reply from $3 after setting $1, re-keying"; rekey $1 $2; return; }
		sleep 2
	done
}
associated() { case "$(/sbin/ifconfig wlan2)" in *'status: associated'*) return 0;; esac; return 1; }
lease() { t=$1; shift; $D/dhcpc -t $t "$@" wlan2 > $M/lease.new; }	# TIMEOUT [ARGS]; 0 on ACK
move_airplay() {
	for p in $(pids /sbin/airtunesd); do kill $p; done
	sleep 3
	/sbin/airtunesd -i wlan2 < /dev/null > $M/airtunesd.out 2>&1 &
}
renew_loop() {
	exec > $M/dhcp.log 2>&1
	while :; do
		echo "$(date) $DHCP_IP from $DHCP_SERVER, lease $DHCP_LEASE s, renewing in $DHCP_T1 s"
		sleep $DHCP_T1
		# unicast to our server, then broadcast to any, then start over; the address
		# stays on wlan2 while this fails, and it retries every minute
		until lease 20 -c $DHCP_IP -s $DHCP_SERVER -m $DHCP_SERVER_MAC ||
		    lease 20 -c $DHCP_IP || lease 30; do
			sleep 60
		done
		old="$DHCP_IP/$DHCP_MASK"
		mv $M/lease.new $M/lease
		. $M/lease
		if [ "$old" != "$DHCP_IP/$DHCP_MASK" ]; then
			echo "$(date) address changed from $old"
			apply $DHCP_IP $DHCP_MASK ${DHCP_ROUTER:-$DHCP_SERVER}
			move_airplay
		fi
	done
}

led 0

# At boot ACPd brings the radios up after rc finishes: wait for the 2.4 GHz hostapd,
# then let the rest of the bring-up settle so ACPd doesn't redo wlan0 after us.
n=0
while [ -z "$(pids hostap_wlan0)" ]; do
	n=$((n + 1))
	[ $n -gt 90 ] && { led 1; finish "no hostapd on wlan0 after 180 s, not joining"; }
	sleep 2
done
sleep 20

ACPD=$(cat /var/run/ACPd.pid)
kill -STOP $ACPD
for p in $(pids hostap_wlan0); do kill $p; done
sleep 1
/sbin/ifconfig wlan0 destroy
/sbin/ifconfig wlan2 create wlandev ath0
/sbin/ifconfig wlan2 up
[ "$IP" = dhcp ] || /sbin/ifconfig wlan2 inet $IP netmask $MASK	# before the supplicant
/sbin/ifconfig wlan2 down
start_wpa
sleep 3
kill -CONT $ACPD

if [ "$IP" = dhcp ]; then
	n=0
	until associated; do
		n=$((n + 1))
		[ $n -gt 20 ] && break	# dhcpc then times out too and reports it
		sleep 2
	done
	# "associated" shows before the 4-way handshake is done: dhcpc's retransmits cover it
	if lease 30; then
		mv $M/lease.new $M/lease
		. $M/lease
		IP=$DHCP_IP MASK=$DHCP_MASK GW=${DHCP_ROUTER:-$DHCP_SERVER}
		echo "lease $IP/$MASK from $DHCP_SERVER, router $GW, $DHCP_LEASE s"
	elif [ -n "${FALLBACK_IP:-}" ]; then
		IP=$FALLBACK_IP DHCP_IP=
		echo "no DHCP lease, using the fallback address $IP"
	else
		kill $(cat $M/wpa.pid)
		/sbin/ifconfig wlan2
		led 1
		finish "no DHCP lease on wlan2, gave up (5 GHz AP and Ethernet still up)"
	fi
	apply $IP $MASK $GW
fi

n=0
until /sbin/ping -c 1 -w 2 $GW > /dev/null 2>&1; do
	n=$((n + 1))
	if [ $n -gt 20 ]; then
		kill $(cat $M/wpa.pid)
		/sbin/ifconfig wlan2
		led 1
		finish "no reply from $GW, gave up (5 GHz AP and Ethernet still up)"
	fi
	sleep 2
done
/sbin/ifconfig wlan2

move_airplay
[ -n "${DHCP_IP:-}" ] && renew_loop < /dev/null &
led 2
finish "joined, $IP via wlan2, AirPlay moved"
