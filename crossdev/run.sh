#!/bin/sh
# Copies a binary to the Express's RAM disk (/mnt/Memory, 15 MB, wiped on reboot) and runs it there.
# Usage: ./run.sh BINARY [ARGS...]      Exit status is the program's.
set -eu
D=$(cd "$(dirname "$0")" && pwd)
bin=${1:?usage: run.sh BINARY [ARGS...]}
shift
name=$(basename "$bin")
args=""
for a in "$@"; do
	args="$args '$(printf %s "$a" | sed "s/'/'\\\\''/g")'"
done
exec "$D/../tools/essh.sh" "cat > /mnt/Memory/$name && chmod 755 /mnt/Memory/$name &&
    cd /mnt/Memory && ulimit -c 0 && ./$name$args" < "$bin"
