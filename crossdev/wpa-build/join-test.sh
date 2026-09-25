#!/bin/sh
# Joins the AirPort Express to a WPA2-PSK network with our own wpa_supplicant (built by
# build-wpa.sh), gives the client vap a static address, pings through it, and moves
# AirPlay (airtunesd) onto that network. The 5 GHz AP (wlan1) stays up.
# Runs from the laptop over the Express's LAN cable (tools/essh.sh). Verified 2026-09-23.
#
# Usage: ./join-test.sh SSID NM-CONNECTION-UUID STATIC-IP GATEWAY
#   (WPA_BIN=path overrides the binary to upload)
#   e.g. ./join-test.sh HomeWiFi "$(nmcli -g connection.uuid c show HomeWiFi)" 192.168.1.250 192.168.1.1
#   (pick an address outside the router's DHCP pool)
#
# The PSK comes from that NetworkManager profile (by UUID: two profiles can share an SSID
# name, and nmcli then prints both PSKs) and is sent only as the 32-byte PMK, straight
# into the Express's RAM disk. Output lands in /mnt/Memory/join.log on the Express.
#
# Disruptive until the Express reboots: briefly freezes ACPd (SIGSTOP), kills the 2.4 GHz hostapd,
# destroys wlan0 and creates a managed vap wlan2 on ath0 (one vap per radio). No stored
# configuration is changed, so `/sbin/reboot` (or a power cycle) restores everything.
# Don't run the stock dhclient on wlan2: it reports to ACPd, and when tried sshd stalled for
# minutes before auth, which cost a power cycle. `airportctl join` has its own DHCP client
# (crossdev/src/dhcpc.c, docs/join-mode.md#addressing-dhcp).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ESSH=$HERE/../../tools/essh.sh
SSID=${1:?usage: join-test.sh SSID NM-UUID STATIC-IP GATEWAY}
UUID=${2:?}; IP=${3:?}; GW=${4:?}
BIN=${WPA_BIN:-$HERE/wpa_supplicant-0.7.3/wpa_supplicant/wpa_supplicant}
[ -x "$BIN" ] || { echo "build it first: $HERE/build-wpa.sh" >&2; exit 1; }

SSID="$SSID" UUID="$UUID" python3 - <<'EOF' | "$ESSH" 'umask 077; cat > /mnt/Memory/wpa.conf'
import os, subprocess, hashlib
ssid, uuid = os.environ["SSID"], os.environ["UUID"]
psk = subprocess.run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show",
                      "uuid", uuid], capture_output=True, text=True, check=True).stdout.rstrip("\n")
assert psk and "\n" not in psk and 8 <= len(psk) <= 63, "no single WPA passphrase in that profile"
pmk = hashlib.pbkdf2_hmac("sha1", psk.encode(), ssid.encode(), 4096, 32).hex()
print(f'ctrl_interface=/var/run/wpa_own\nap_scan=1\nnetwork={{\n\tssid="{ssid}"\n'
      f'\tkey_mgmt=WPA-PSK\n\tproto=RSN\n\tpairwise=CCMP\n\tgroup=CCMP TKIP\n\tpsk={pmk}\n}}')
EOF
"$ESSH" 'cat > /mnt/Memory/wpa_supplicant && chmod 755 /mnt/Memory/wpa_supplicant' < "$BIN"

# The device-side part runs detached, so no SSH session is open while the radio changes.
# Upload and launch are separate: a backgrounded list gets /dev/null as stdin.
"$ESSH" "cat > /mnt/Memory/join.sh && chmod 755 /mnt/Memory/join.sh" <<EOF
#!/bin/sh
cd /mnt/Memory
exec > /mnt/Memory/join.log 2>&1
kill -STOP \$(cat /var/run/ACPd.pid)
for p in \$(/bin/ps ax | while read pid rest; do case "\$rest" in *hostap_wlan0*) echo \$pid;; esac; done); do kill \$p; done
sleep 1
/sbin/ifconfig wlan0 destroy
/sbin/ifconfig wlan2 create wlandev ath0
/sbin/ifconfig wlan2 up
# The address can go on before or after the handshake: changing addresses on the keyed link
# keeps the keys (tested 2026-09-25). Setting it here, while the interface is still up, is
# just the simplest order.
/sbin/ifconfig wlan2 inet $IP netmask 255.255.255.0
# ...and then DOWN: 0.7.3's driver_bsd downs the interface during init and takes the
# resulting RTM_IFINFO (IFF_UP clear) for "interface removed", which deinits its EAPOL
# socket (l2_packet) for good: it keeps associating but never hears 4-way msg 1/4.
# Starting from a down interface avoids that; the supplicant brings it up itself.
/sbin/ifconfig wlan2 down
./wpa_supplicant -t -D bsd -i wlan2 -c /mnt/Memory/wpa.conf > /mnt/Memory/wpa.log 2>&1 &
echo \$! > wpa.pid
sleep 3
# ACPd only has to be frozen while the radio is taken; resumed, it leaves wlan2 alone
# (verified: ACP answers, 5 GHz AP on wlan1 stays up, 45/45 pings over wlan2).
kill -CONT \$(cat /var/run/ACPd.pid)
sleep 9	# "status: associated" shows before the 4-way handshake is done
/sbin/ifconfig wlan2
/sbin/ping -c 3 $GW
/sbin/route add -host 1.1.1.1 $GW
/sbin/ping -c 4 1.1.1.1
# AirPlay on the joined network: airtunesd registers _raop/_airplay only on its -i
# interface (default bridge0); ACPd doesn't respawn it. Verified: session from the LAN,
# 0 lost packets.
for p in \$(/bin/ps ax | while read pid rest; do case "\$rest" in */sbin/airtunesd*) echo \$pid;; esac; done); do kill \$p; done
sleep 3
/sbin/airtunesd -i wlan2 < /dev/null > /mnt/Memory/airtunesd.out 2>&1 &
echo DONE
EOF
"$ESSH" '/mnt/Memory/join.sh < /dev/null > /dev/null 2>&1 &'
echo "started; in ~30 s: ping $IP from the LAN, and $ESSH 'cat /mnt/Memory/join.log'"
echo "restore: $ESSH /sbin/reboot"
