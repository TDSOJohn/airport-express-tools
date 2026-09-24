# Security profile of the AirPort Express (A1392, firmware 7.8.1)

A consolidated, evidence-backed look at the security posture of the last A1392 firmware
(**7.8.1**, released 2018). It is written for people studying the platform or building on it,
not as an owner's hardening checklist — the point is *what the trust boundaries actually are*
and *where the evidence for each claim comes from*, so the findings can be cited and re-checked.

Every claim below is anchored to one of the other pages in this repo (the live control-plane
sweep, the `dbug` decompile, the boot/flash map, the offline firmware unpack) or to two
first-hand measurements taken on 2026-09-24:

* a **read-only TCP connect scan** of a live A1392 in AP mode (ports 1–1024 plus the
  AirPlay/Apple high ports; one `connect()` per port, no service fuzzing), and
* **string/library inventory** of the 7.8.1 root filesystem extracted offline (see
  [firmware.md](firmware.md) — the extract is byte-identical to the live device).

Nothing here required a code path that writes to the device.

## TL;DR

7.8.1 is a **2018 firmware on a 2007 operating system**. NetBSD 4.0, OpenSSL 0.9.8e (2007) and
libcurl 7.17.1 (2007) are frozen; the one large change Apple shipped in six years was a
*feature* — the AirPlay 2 receiver — not a security refresh. The device has **no secure boot**
on its local flash/boot path, its control plane hands back stored secrets in cleartext to any
authenticated client, and its only credential is the admin password (which is also root's when
SSH is turned on). None of this is remotely exploitable *by default* — the exposures are gated
behind the admin password, an opt-in debug flag, or physical access — but there is no defence in
depth: one credential, one obfuscation layer, and a crypto stack that stopped moving in 2007.

## Network attack surface (live, AP mode)

Read-only connect scan of the unit at its default `10.0.1.1`, acting as router/AP for its own
DHCP subnet:

| Port | Service | Banner / identity | Notes |
|---|---|---|---|
| 22/tcp | SSH | `SSH-1.99-OpenSSH_4.4 NetBSD_Secure_Shell-20061114` | **Off by default.** Gated by `dbug` bit `0x200`; open on this unit only because `dbug=0x3000` was set for the R4 flash dump. See [dbug.md](dbug.md). |
| 53/tcp | DNS | — | Forwarder for the stations it serves DHCP; present because the box is the router for its subnet. |
| 5009/tcp | ACP | `_airport._tcp` | The **admin/control plane**. Always on. See [rpc-surface.md](rpc-surface.md), [properties.md](properties.md). |
| 7000/tcp | RTSP | `AirTunes/366.0` | AirPlay 2 audio receiver (`_raop._tcp` / `_airplay._tcp`). `OPTIONS` returns `ANNOUNCE, SETUP, RECORD, PAUSE, FLUSH, FLUSHBUFFERED, TEARDOWN, OPTIONS, POST, GET, PUT`. |
| 10000/tcp | AirPlay 2 (binary) | — | Second AirPlay-2 listener; accepts TCP but closes on both HTTP and RTSP text, so it is a binary-framed channel, not a text protocol. Appears with the AirPlay 2 back-port. |

So the **default** exposed surface is `{53, 5009, 7000, 10000}`; SSH (22) is added only when the
`dbug` SSH bit is cleared. Bonjour advertises more service *types* than there are open TCP
listeners — `_hap._tcp` (HomeKit pairing), `_dacp._tcp`, `_mfi-config._tcp`, `_acp-sync._tcp`,
`_autotunnel._udp` (Back to My Mac / IPsec — `/etc/racoon/` is present and configured), and the
legacy `_printer`/`_pdl-datastream`/`_riousbprint` print types — most of which are dormant unless
the corresponding feature is configured.

## Crypto inventory — frozen, with two exceptions

Pulled from the 7.8.1 megabinary. The system TLS/SSH stack is **2007-vintage and unchanged**
across the last several releases (confirmed by diffing 7.6.2 ↔ 7.8.1 in [firmware.md](firmware.md)):

| Component | Version | Age | State |
|---|---|---|---|
| OpenSSL | **0.9.8e (23 Feb 2007)** | ~19 yr | frozen |
| libcurl | **7.17.1 (2007)** | ~19 yr | frozen |
| OpenSSH | **4.4 (2006)**, banner `SSH-1.99` | ~20 yr | frozen; **offers SSH protocol 1** (`RSA1` keys, `do_ssh1_kex`) |
| Kernel/OS | **NetBSD 4.0 (2007)** | ~19 yr | frozen |

Two things were *not* frozen — both belong to the AirPlay 2 back-port, not to system TLS:

* **mDNSResponder** was refreshed to **397.32 (2019 build)**.
* **HAP / AirPlay 2 pairing crypto** (ChaCha20-Poly1305, Curve25519, RSA-SHA256) was added.
  This is the AirPlay 2 / HomeKit pairing channel; it does not carry, replace, or modernise the
  system's TLS (OpenSSL) or SSH.

The practical read: **SSH protocol 1 is cryptographically broken** and should never be relied on;
any TLS the box terminates or initiates runs through a 2007 OpenSSL with two decades of unpatched
CVEs. Reachability of those CVEs is bounded by how little TLS the device actually speaks (next
section).

## Trust boundary 1 — firmware and boot

This is the most nuanced finding, and it splits cleanly in two:

**Apple's update feed *is* signed.** The device fetches `http://apsu.apple.com/version.xml`
(plaintext) together with `version.xml.signature`, and verifies an **RSA signature chained to a
bundled Apple Root CA** (`EVP_VerifyFinal` / `eay_rsa_verify`, Apple Root CA certificate present
in the image). The firmware payloads themselves are plain `http://…/*.basebinary` downloads, so
the *transport* is unauthenticated, but the *catalog* that names them is signature-protected.

**The device's own flash/boot path is not signed.** Neither CFE at boot nor `ACPd`'s flash
writer verifies a signature — both check only an **Adler-32 checksum plus the `minS`
anti-rollback version** (see [boot.md](boot.md), and `FUN_00699a84`). So a correctly-checksummed
image pushed **locally** — over ACP (`.basebinary`) or via the CFE TFTP/serial console — is
accepted and booted regardless of who made it. The payload "encryption" (AES-128-CBC, per-model
key that is **public**; see [firmware.md](firmware.md)) is **flag-gated and provides no
integrity** — an *unencrypted* bank with a valid Adler-32 is accepted just the same.

Net: the *supply chain* (device ← Apple) has a signature gate; the *device itself* has none. An
attacker who can push firmware locally (physical, or an authenticated ACP session) owns the box
persistently; a network attacker cannot ride Apple's official update flow past the catalog
signature, but can serve the plaintext-HTTP payloads freely once the signed catalog points at
them.

## Trust boundary 2 — the ACP control plane (TCP 5009)

* **Single credential, authenticated per connection.** `getprop`/`setprop`/RPC are gated by the
  admin password (wrong password → `0xfffffff0`; there is no unauthenticated read path). See
  [properties.md](properties.md), [rpc-surface.md](rpc-surface.md).
* **Secrets are returned in cleartext** to an authenticated client: the WPA **PMK** (in the
  `WiFi` blob), and the admin/guest passwords `syPW`/`syPR`/`syGP`. Reading a property reads the
  stored secret, not a redaction.
* **The transport is obfuscated, not encrypted.** ACP's framing uses a *public, static*
  keystream (documented by node-acp / airpyrt-tools) — it is not a confidentiality control
  against an on-path observer, and it is not a second factor.
* **Destructive operations exist** behind the same single gate: reboot, flash write, factory
  reset (all `type 10` action properties; deliberately not exercised in our sweeps).

The default admin password is `public`. Consequence: on a shared or untrusted LAN, anyone who
knows or guesses one password can read the Wi-Fi PMK and every stored credential, and can reflash
or brick the unit.

## Trust boundary 3 — SSH (when enabled)

SSH is **opt-in and off by default**, gated by `dbug` bit `0x200` (the community "`0x3000`"
recipe simply leaves that bit clear; see [dbug.md](dbug.md)). When it is on:

* `sshd` is (re)configured on **every boot** with `PermitRootLogin yes`, and root's Unix
  password is synced to the admin password. So enabling SSH yields **`root@express` with the
  admin password** — there is no separate root credential.
* The server offers **SSH protocol 1** and 2006-era key exchange and ciphers; a modern client
  must explicitly re-enable `diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`/`3des-cbc` to
  connect at all.

There is **no arbitrary run-at-boot hook** behind any `dbug` bit — the only persistence `dbug`
introduces is `sshd` itself plus its host keys in `/mnt/Flash`.

## Trust boundary 4 — Wi-Fi / RF

* **No Protected Management Frames (802.11w).** The NetBSD 4.0 / hostapd stack does not support
  PMF, so deauthentication and disassociation frames are unauthenticated → trivial forced
  disconnects and a foothold for evil-twin attacks. (We observed exactly this class of problem in
  the join work: a blocked join can leave clients latching onto a look-alike AP.)
* Wi-Fi is WPA2-PSK; the PMK is recoverable through the ACP path above by anyone with the admin
  password.

## Trust boundary 5 — physical access

Physical access is total access, by design of the era:

* The **debug header by the audio jack** exposes a UART (115200 8N1) that drops to an
  **unauthenticated root shell** and the interruptible **`CFE>`** console during the ~1 s boot
  window — no `dbug`, no SSH, no password. EJTAG pads are also present. (See
  [boot.md](boot.md) / [hardware.md](hardware.md).)
* The **soft reset** makes the admin password `public` accepted for ~1 s after the button press,
  regardless of the configured password (a deliberate recovery path; documented in the repo TODO
  / README recovery notes).
* Because the boot path has no signature check, physical or console access allows a **persistent**
  malicious reflash.

## Threat model

Positions are additive downward in capability. "Evidence" points to where each capability is
established in this repo.

| Attacker position | What they can do | Gate / evidence |
|---|---|---|
| **Same LAN, no credential** | Enumerate services; force Wi-Fi disconnects (no PMF); attempt evil-twin; observe (obfuscated, not encrypted) ACP traffic; hit the AirPlay/RTSP receiver | mDNS + scan above; no-PMF; ACP obfuscation is public |
| **Same LAN, has admin password** (default `public`) | Read the Wi-Fi PMK and all stored passwords in cleartext; change config; reboot; **reflash / brick**; push unsigned firmware over ACP | [properties.md](properties.md), [rpc-surface.md](rpc-surface.md); local flash path is unsigned |
| **Internet / WAN** | Nothing *by default* — nothing above is meant to face the WAN. Real risk is misconfiguration (port-forwarding 5009/22 to it) or the 2007 TLS stack if any outbound TLS is induced | default surface is LAN-only; update transport is plaintext HTTP with a signed catalog |
| **RF range** | Deauth/evil-twin (no PMF); WPA2-PSK offline attack on captured handshakes | no 802.11w in NetBSD 4.0/hostapd |
| **Physical / console** | Full unauthenticated root via UART; interrupt boot via CFE; **persistent** malicious reflash (no secure boot) | UART shell + `CFE>`; Adler-32/`minS`-only boot check |

## What is *not* as bad as the headline

Calibration matters for a research write-up:

* **No unauthenticated remote code path was found.** The control plane requires the admin
  password; SSH is off unless a debug flag is changed; the destructive RPCs sit behind the same
  auth.
* **No secure boot ≠ remote compromise.** It means the *owner cannot verify integrity* and a
  *local* attacker can persist — not that the network can flash it. It also means custom firmware
  is legitimately possible without defeating any signature (the basis for the community's
  replacement-firmware work and for anything built on this repo).
* **The official update channel is signature-checked** at the catalog layer, so the plaintext-HTTP
  transport is not an open door to arbitrary OTA firmware.

## Operational implications (brief)

Not a hardening guide, but the facts have obvious consequences for anyone still running one or
building tooling against it: treat it as a **LAN-only appliance on an isolated segment**, never
WAN-exposed; assume its **TLS/SSH are not trustworthy** and don't route anything sensitive through
them; remember the **admin password is the whole security model** (and is root's when SSH is on);
and treat **physical access as full compromise**. For tooling: the single-credential,
cleartext-secret design means backups and property dumps contain the PMK and passwords — never
publish them (this repo keeps all such raw captures out of the tree; see the `.gitignore`).

## Provenance

Live measurements (TCP scan, banners, RTSP `OPTIONS`) and offline string/library inventory taken
2026-09-24 on an A1392 running 7.8.1, read-only. The crypto versions, the update-signature
machinery, and the service map were read from the 7.8.1 root filesystem extracted per
[firmware.md](firmware.md). Control-plane, `dbug`, and boot findings are cross-referenced to
[rpc-surface.md](rpc-surface.md), [properties.md](properties.md), [dbug.md](dbug.md) and
[boot.md](boot.md). ACP obfuscation and the per-model firmware keys are credited to
[node-acp](https://github.com/samuelthomas2774/node-acp) and
[airpyrt-tools](https://github.com/x56/airpyrt-tools); the UART/JTAG and board details to
[Embedded Ideation](https://www.embeddedideation.com/2016/04/24/airport-hacking-update/) and the
Rogue Amoeba teardown.
