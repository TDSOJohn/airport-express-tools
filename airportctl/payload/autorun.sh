#!/bin/sh
# /mnt/Flash/autorun.sh: started at boot by the /etc/rc hook (docs/autorun.md), or by
# `airportctl join start`. Installed by `airportctl join install` (airportctl/join.py).
#
# Joins the 2.4 GHz radio to the WPA2 network in autorun/wpa.conf with our own
# wpa_supplicant and moves AirPlay onto it: the same steps as
# crossdev/wpa-build/join-test.sh, where each one is explained. The 5 GHz AP stays up.
# Log goes to RAM (/mnt/Memory/autorun.log): sustained Flash writes stall sshd logins.
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
. $D/join.conf			# IP=, GW=, optional MASK=
MASK=${MASK:-255.255.255.0}

pids() { /bin/ps ax | while read pid rest; do case "$rest" in *$1*) echo $pid;; esac; done; }
finish() { echo "$1 $(date)"; rm -f /mnt/Flash/autorun.try; exit 0; }
led() { acp -q LEDc=$1; }	# 0 ACPd's status, 1 amber, 2 green

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
/sbin/ifconfig wlan2 inet $IP netmask $MASK	# before the supplicant: SIOCSIFADDR drops keys
/sbin/ifconfig wlan2 down			# and down: 0.7.3 would take IFF_UP clear as removal
$D/wpa_supplicant -t -D bsd -i wlan2 -c $D/wpa.conf > $M/wpa.log 2>&1 &
echo $! > $M/wpa.pid
sleep 3
kill -CONT $ACPD

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

for p in $(pids /sbin/airtunesd); do kill $p; done
sleep 3
/sbin/airtunesd -i wlan2 < /dev/null > $M/airtunesd.out 2>&1 &
led 2
finish "joined, $IP via wlan2, AirPlay moved"
