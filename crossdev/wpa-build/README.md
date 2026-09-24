# Replacement wpa_supplicant for the AirPort Express (minimal WPA2-PSK)

The stock firmware's `/sbin/wpa_supplicant` (Apple's crunched 0.6.5) segfaults at startup,
so client / "join a wireless network" mode can't work from configuration. The kernel's
station datapath is fine, so we run our own supplicant instead. This directory builds one.

**Status: works on hardware (2026-09-23).** On a managed vap on `ath0` it scans, associates,
completes the WPA2-PSK 4-way handshake with a third-party AP (an ISP router), installs
PTK+GTK (CCMP), and carries traffic both ways: Express -> gateway 0% loss, Express -> 1.1.1.1
4/4 at ~21 ms, and a LAN laptop -> the Express's Wi-Fi address.

## Build

```sh
./build-wpa.sh
```

Fetches stock **wpa_supplicant 0.7.3** and NetBSD 4's `getifaddrs.c` (both sha256-checked),
drops in a minimal `.config`, and cross-compiles with the crossdev toolchain + `../sysroot`:

```
wpa_supplicant-0.7.3/wpa_supplicant/wpa_supplicant       static NetBSD 4.0 mipseb ELF, ~958 KB stripped
wpa_supplicant-0.7.3/wpa_supplicant/wpa_supplicant.dbg   unstripped, with symbols
```

## Run

```sh
./join-test.sh SSID NM-CONNECTION-UUID STATIC-IP GATEWAY
```

It takes the 2.4 GHz radio (ACPd is frozen only for the takeover, then resumed), joins,
pings, and restarts `airtunesd -i wlan2` so AirPlay is advertised and served on the joined
network. The 5 GHz AP stays up. It takes ~70 s. Nothing persists: `/sbin/reboot` on the Express
restores the stock setup, and no stored configuration is touched.

Two things to know when changing it:
- **Start the supplicant with the interface down.** 0.7.3's `driver_bsd` downs the interface
  during init, then reads its own `RTM_IFINFO` (IFF_UP clear) as "interface removed" and drops
  its EAPOL socket. It then associates but never hears 4-way message 1/4. So the harness
  assigns the address, runs `ifconfig wlan2 down`, and then starts the supplicant.
- **airtunesd only registers `_raop`/`_airplay` on its `-i` interface** (default `bridge0`).

## Why 0.7.3, and the kernel ABI

Apple's kernel is NetBSD 4.0_STABLE, but its net80211 is **FreeBSD 8-era** (vaps, 802.11n).
0.6.5 (Apple's version) associates but can't scan or hand its RSN IE to the kernel. 0.7.3's
`driver_bsd.c` has the FreeBSD 8 code paths, and it picks them from header defines. So the
fix is in headers, with **no edits to upstream source**:

| mismatch (found on-device / in Apple's own ifconfig) | fix |
|---|---|
| `struct if_msghdr` is 152 bytes, not 144, so libc's `getifaddrs()` returns empty names and `if_nametoindex()` fails | `compat/net/if.h` + NetBSD 4 `getifaddrs.c` rebuilt against it (`compat/libc/`) |
| `SIOCS80211`/`SIOCG80211` are FreeBSD's `'i'` 234/235; NetBSD's 244/245 give ENOTTY (NetBSD's private `SIOC*80211POWER` collide with 234/235) | `compat/net80211/ieee80211_ioctl.h` |
| `IEEE80211_IOC_SCAN_RESULTS`=76, `SCAN_REQ`=103 + `struct ieee80211_scan_req`, `OPTIE` replaced by `APPIE`=95 | same header |
| scan-result record is the 38-byte FreeBSD 7 layout (`isr_ie_off`, no `isr_meshid_len`) | same header (size-checked) |
| libc.a's `__setjmp14` saves FPU registers (no FPU here: CpU trap); libpcap's `pcap_compile()` calls it | `compat/libc/setjmp_softfloat.S` |
| `IFM_IEEE80211_IBSS` spelled `IFM_IEEE80211_ADHOC` (IBSS path only) | `compat/net/if_media.h` |

Unchanged between the two and used as-is: `ieee80211req`, `_key`, `_del_key`, `_mlme`, and the
`RTM_IEEE80211_*` events.

## The minimal config

| switch | why |
|---|---|
| `CONFIG_DRIVER_BSD=y` | net80211 ioctls + a PF_ROUTE socket for events |
| `CONFIG_L2_PACKET=freebsd` | EAPOL over libpcap/BPF (`../sysroot` ships `libpcap.a`) |
| `CONFIG_TLS=internal` + `CONFIG_INTERNAL_LIBTOMMATH=y` | with no EAP: just `tls_none` + internal AES/SHA1/MD5/RC4, no OpenSSL |
| `CONFIG_CTRL_IFACE=y`, `CONFIG_BACKEND=file` | control socket, read `wpa_supplicant.conf` |

On-device test vectors (SHA-1, HMAC-SHA1, the 802.11i PBKDF2 vector) pass with this build.

## Other port details

- **`-U__linux__` &co.**: the Debian cross-gcc predefines `__linux__`.
- **`-isystem <gcc include>` before the sysroot**: use gcc 14's `stdarg.h`.
- **`-std=gnu89 -fcommon`**: build 2008–2010-era C under gcc 14.
- **`ldnetbsd.sh`**: static link against the sysroot's NetBSD crt objects and `libc.a`/`libpcap.a`,
  with the compat objects placed first so they override the libc copies.
- Only float formatting/parsing code (`dtoa`, `strtod`, `%f`) still contains FPU instructions,
  and wpa_supplicant never calls it.
