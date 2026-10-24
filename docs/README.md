# Docs

Reference data for Apple AirPort base stations and Time Capsules on the NetBSD-based 7.x
firmware, and for the tools in this repo.

| Page | Contents |
|---|---|
| [models](models.md) | Per-model data side by side: platform, flash, ACP surface, airportctl support, firmware keys |
| [hardware](hardware.md) | Board components, debug header (UART, EJTAG), flash chip, recovery paths |
| [boot](boot.md) | Flash partitions, boot chain, bank checksum, CFE console, update paths, factory nvram |
| [firmware](firmware.md) | Apple's firmware catalog, the `.basebinary` format and encryption, image contents, 7.6.2 → 7.8.1 diff |
| [properties](properties.md) | The 520 ACP properties: types, flags, read results, status problem codes |
| [rpc-surface](rpc-surface.md) | The 88 ACP RPCs: inputs, outputs, classification |
| [wifi-blob](wifi-blob.md) | The `WiFi` property: per-radio keys, security modes, the generated hostapd config |
| [join-mode](join-mode.md) | Client mode: the firmware gate, the bundled supplicant crash, the replacement supplicant, DHCP |
| [dbug](dbug.md) | The `dbug` debug bitfield and the SSH login |
| [autorun](autorun.md) | A custom firmware image that runs `/mnt/Flash/autorun.sh` at boot |
| [security](security.md) | Open ports, crypto versions, trust boundaries, threat model |
| [extracting-acpd](extracting-acpd.md) | Getting `ACPd` from a unit or a firmware image, and into Ghidra |

Tools: [airportctl](../airportctl/README.md) · [crossdev](../crossdev/README.md) ·
[wpa-build](../crossdev/wpa-build/README.md) · [ghidra_scripts](../ghidra_scripts/README.md)

## Conventions

| | |
|---|---|
| Source tags | **L** read from a live unit · **F** from a firmware image or binary (static analysis) · **E** external publication (teardowns, other projects) |
| Default scope | Data not marked otherwise is from an A1392 (AirPort Express 2012, `syAP` 115) on firmware 7.8.1. Other models: [models.md](models.md) |
| Addresses | `FUN_…`, `DAT_…` and VMAs refer to `/sbin/ACPd` from 7.8.1 for `syAP` 115 (10 295 088 bytes, SHA-256 `f7730dab…d27b38be`, image base `0x00400000`). They move on other builds; [extracting-acpd.md](extracting-acpd.md#anchors) lists how to re-find them |
| Model names | A-numbers, `syAP` IDs and codenames as in the [compatibility table](../README.md#compatibility) |
| Withheld | Serial numbers, MACs, SSIDs, PMKs, passwords and Apple binaries/firmware are kept out of the repo |
