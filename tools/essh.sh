#!/bin/sh
# Non-interactive SSH to the AirPort Express debug shell (root, admin password via askpass.sh).
# Needs dbug=0x3000 on the Express and the airport-probe profile up.
# Usage: ./essh.sh 'command'      Env: AIRPORT_HOST (default 10.0.1.1), AIRPORT_PW (default public)
D=$(cd "$(dirname "$0")" && pwd)
exec env SSH_ASKPASS="$D/askpass.sh" SSH_ASKPASS_REQUIRE=force DISPLAY=none \
  ssh -o HostKeyAlgorithms=+ssh-rsa \
      -o KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1,diffie-hellman-group-exchange-sha1 \
      -o Ciphers=+aes128-cbc,aes256-cbc,3des-cbc -o MACs=+hmac-sha1,hmac-md5 \
      -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$D/.airport_known_hosts" \
      -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive \
      -o ConnectTimeout=10 -o LogLevel=ERROR "root@${AIRPORT_HOST:-10.0.1.1}" "$@"
