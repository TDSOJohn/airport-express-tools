# Security

Security-relevant data for the 7.x firmware. Measured on an A1392 on 7.8.1 (read-only TCP
connect scans, banners; string inventory of the extracted 7.8.1 root filesystem) unless
noted.

| | |
|---|---|
| Firmware age | 7.8.1 (2018) on NetBSD 4.0 with OpenSSL 0.9.8e and libcurl 7.17.1 (2007) |
| Credential | one: the admin password (default `public`), also root's when SSH is on |
| Secrets over ACP | WPA PMK and all stored passwords returned in cleartext to an authenticated client |
| Secure boot | none on the local flash/boot path; Apple's update catalog is signed |
| Unauthenticated remote code path | none found |

## Network surface

### LAN side (default NAT/AP role)

| Port | Service | Identity | Notes |
|---|---|---|---|
| 22/tcp | SSH | `SSH-1.99-OpenSSH_4.4 NetBSD_Secure_Shell-20061114` | only with `dbug` bit `0x200` clear ([dbug.md](dbug.md)); off by default |
| 53/tcp | DNS | | forwarder for its DHCP clients |
| 5009/tcp | ACP | `_airport._tcp` | admin/control plane, always on |
| 7000/tcp | RTSP | `AirTunes/366.0` | AirPlay 2 receiver (`_raop._tcp`, `_airplay._tcp`). `OPTIONS`: `ANNOUNCE, SETUP, RECORD, PAUSE, FLUSH, FLUSHBUFFERED, TEARDOWN, OPTIONS, POST, GET, PUT` |
| 10000/tcp | AirPlay 2 | | binary-framed; closes on HTTP and RTSP text |

Other Bonjour types advertised (mostly dormant unless the feature is configured):
`_hap._tcp` (HomeKit pairing), `_dacp._tcp`, `_mfi-config._tcp`, `_acp-sync._tcp`,
`_autotunnel._udp` (Back to My Mac / IPsec; `/etc/racoon/` present and configured),
`_printer`, `_pdl-datastream`, `_riousbprint`.

### WAN side

Wired WAN behind a home router, default NAT role (full TCP 1–65535 + UDP probes from the
upstream network, L):

| | |
|---|---|
| Open (measured) | udp/192, tcp/5009 (ACP), tcp/22 (SSH was on); `airportctl --host <wan-ip>` works |
| Opened by the rules | the above (22 only with `dbug` `0x200` clear), plus tcp+udp/5001 (iperf) unless `dbug` `0x1000` / `0x2000` |
| Closed | everything else: TCP dropped, UDP answered with ICMP unreachable |
| Rules | ACPd's pf ruleset (`pfctl -s rules`): `pass in on eth0 proto {udp 192, tcp 5009, tcp ssh} to (eth0)` + matching `no rdr` exemptions |
| Gate | `FUN_0065e958` opens these ports only while byte `0xe46edc` is 0; `FUN_0065746c` sets it at boot to 1 when NAT is off, else to the stored bool `waNM` |
| Default | `waNM = False` on a unit never set up in AirPort Utility → **ACP open on the WAN**; tell-tale: problem `waCF` ([properties.md](properties.md#status-problems-syst)) |
| Bridge mode | no WAN side: the unit is a host on the upstream subnet, ACP (and SSH) reachable from all of it |

### Known bugs

| Bug | Trigger | Effect |
|---|---|---|
| ACPd crash on misaligned `setprop` | a multi-property `setprop` with a value length not a multiple of 4 (e.g. three 1-byte bools); the next element header is read with `lw` at an odd offset | SIGSEGV at `pc 0x678718` (AdEL, `badvaddr` = body + 13 + 8). Not respawned: ACP and the `_airport` mDNS records stay down until reboot; hostapd, AirPlay and sshd keep running; nothing saved. Needs the admin password (authenticated DoS). airportctl sends one property per request |

## Crypto inventory

| Component | Version | State |
|---|---|---|
| OpenSSL | 0.9.8e (23 Feb 2007) | unchanged 7.6.2 → 7.8.1 |
| libcurl | 7.17.1 (2007) | unchanged |
| OpenSSH | 4.4 (2006), banner `SSH-1.99` | unchanged; offers SSH protocol 1 (`RSA1` keys, `do_ssh1_kex`) |
| Kernel / OS | NetBSD 4.0 (2007) | unchanged |
| mDNSResponder | 397.32 (2019 build) | refreshed with AirPlay 2 |
| HAP / AirPlay 2 pairing | ChaCha20-Poly1305, Curve25519, RSA-SHA256 | added in 7.8.1; pairing channel only, not used for system TLS or SSH |
| Wi-Fi | WPA2-PSK; no 802.11w (PMF) in NetBSD 4.0 / hostapd | deauth / disassoc frames unauthenticated |

## Trust boundaries

| Boundary | Protection | Gap |
|---|---|---|
| Update catalog | `version.xml` + `version.xml.signature`: RSA (`EVP_VerifyFinal` / `eay_rsa_verify`) chained to a bundled Apple Root CA | catalog and `.basebinary` payloads fetched over plain HTTP |
| Local flash / boot | Adler-32, model ID, `minS` version floor ([boot.md](boot.md#verification)) | no signature: any well-formed image pushed over ACP or the CFE console boots. AES with a public per-model key, flag-gated, no integrity ([firmware.md](firmware.md#encryption)) |
| ACP (5009) | admin password per connection (wrong → `0xfffffff0`) | legacy login uses a public static keystream (obfuscation); 7.8.1 still accepts it and airportctl uses it. SRP login + AES-CTR session encryption exist ([Embedded Ideation 2016](https://www.embeddedideation.com/2016/04/24/airport-hacking-update/), node-acp) but are optional. Reads return `syPW` / `syPR` / `syGP` and the PMK in cleartext. Reboot, flash write, factory reset behind the same password |
| SSH | off by default (`dbug` `0x200`) | when on: `PermitRootLogin yes`, root password = admin password, SSHv1 and 2006-era KEX/ciphers |
| Wi-Fi | WPA2-PSK | no PMF; PMK readable over ACP with the admin password |
| Soft reset | physical button (1 s) | for 5 minutes the literal `public` is accepted in place of `syPW` (auth check `FUN_006768c0`); set only by the button, never by ACP |
| Physical | none | UART root shell without authentication, `CFE>` console, EJTAG ([hardware.md](hardware.md#debug-header)) |

## Threat model

Capabilities are cumulative downward.

| Attacker position | Can | Gate / evidence |
|---|---|---|
| Same LAN, no credential | enumerate services; force Wi-Fi disconnects (no PMF); evil twin; observe obfuscated ACP traffic (admin password recoverable from a legacy login); reach the AirPlay/RTSP receiver | mDNS + scan; no PMF; ACP obfuscation is public |
| Same LAN, admin password (default `public`) | read the PMK and all passwords; change config; reboot; reflash or brick; push unsigned firmware | [properties.md](properties.md), [rpc-surface.md](rpc-surface.md); unsigned local flash path |
| WAN | same as the previous row on a NAT unit with `waNM` unset (ACP and udp/192 face the WAN; SSH when on); closed in bridge mode or with `waNM` set | [WAN side](#wan-side) |
| RF range | deauth / evil twin; offline attack on captured WPA2 handshakes | no 802.11w |
| Physical | unauthenticated root over the UART; interrupt boot at `CFE>`; persistent reflash | no secure boot |

Property dumps and `WiFi` backups contain the PMK and the passwords; this repo keeps them
out of the tree (`.gitignore`).
