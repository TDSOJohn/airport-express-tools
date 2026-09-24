"""airportctl - configure a 2nd-gen AirPort Express (A1392) over the ACP admin protocol.

A small, safety-first CLI built on the reverse-engineering in ../docs/:
  cfl    binary CFL-plist parse/compose (the `WiFi` blob format)
  acp    ACP protocol: header-key auth, getprop/setprop/rpc, reboot
  props  human-readable maps (raWM security modes, radio fields)
  wifi   WiFi-blob model: load w/ roundtrip guard, per-radio secure()/ssid()/hidden(), write w/ backup
  cli    argparse subcommands

Run:  python3 -m airportctl ...   (or ./airportctl ... from this folder)
"""
__version__ = '0.1.0'
