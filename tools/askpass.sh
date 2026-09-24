#!/bin/sh
# SSH_ASKPASS helper for essh.sh: prints the Express admin password.
# $AIRPORT_PW, else the first line of $AIRPORT_PW_FILE (default ~/.config/airport-express/admin-pw,
# written by you, mode 600), else the factory default `public`.
f=${AIRPORT_PW_FILE:-$HOME/.config/airport-express/admin-pw}
if [ -n "${AIRPORT_PW:-}" ]; then echo "$AIRPORT_PW"
elif [ -r "$f" ]; then head -n 1 "$f"
else echo public; fi
