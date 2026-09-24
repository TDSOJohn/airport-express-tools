"""Human-readable maps for the WiFi-blob fields airportctl touches.

Decoded from the hostapd-config generator FUN_00682190 and the blob->struct consumers
(FUN_00686384 / FUN_006896a0 / FUN_00689ab8); see ../docs/wifi-blob.md.
"""

# raWM (per-radio security mode int) -> label.
RAWM_MODES = {
    0: 'open',
    1: 'WEP',
    2: 'WEP (shared key)',
    3: 'WPA (TKIP)',
    4: 'WPA/WPA2 (TKIP + CCMP)',
    5: 'WPA2 (CCMP)',
    6: 'WPA/WPA2 (TKIP + CCMP)',
    7: 'WPA/WPA2 (CCMP + TKIP)',
    8: 'WPA (TKIP + CCMP)',
}

# Named security levels the CLI can set -> raWM value. WPA-family modes derive raWE from a PMK;
# 'wep' takes a raw hex key; 'open' clears the key.
SECURITY_RAWM = {
    'open': 0,
    'wep': 1,
    'wpa': 3,
    'wpa2': 5,
    'mixed': 7,
}

WPA_MODES = {'wpa', 'wpa2', 'mixed'}

# raWM values whose key (raWE) is an SSID-derived WPA PMK -> renaming the SSID invalidates it.
WPA_RAWM_VALUES = {3, 4, 5, 6, 7, 8}


def rawm_label(v):
    return RAWM_MODES.get(v, f'mode {v}')


# raSt (per-radio station role), confirmed in the loader FUN_00689ab8: raSt==1 sets the STA/join
# flag, raSt==0 the AP/create flag. 3 = radio off (per ../readme.md).
STATION_MODES = {'create': 0, 'join': 1, 'off': 3}
STATION_LABELS = {0: 'create a network (AP)', 1: 'join a network (client/STA)', 3: 'Wi-Fi off'}


def station_label(v):
    return STATION_LABELS.get(v, f'raSt {v}')


# Front status LED, the 'LEDc' property. Verified live on-device 2026-09-15: change is immediate
# (no reboot) and only 0-3 stick (higher values are silently ignored, keeping the previous value).
LED_MODES = {'auto': 0, 'amber': 1, 'green': 2}
LED_LABELS = {
    0: 'auto (default status behaviour)',
    1: 'solid amber',
    2: 'solid green',
    3: 'solid green (both drive lines)',
}


def led_label(v):
    return LED_LABELS.get(v, f'0x{v:08x} (unknown; only 0-3 are accepted)')


# syAP (product ID) -> model, from the AirPort wiki's ACP-properties page. 115 is the only one
# airportctl has been run against.
PRODUCTS = {
    102: 'AirPort Express (802.11g, 1st gen)',
    104: 'AirPort Extreme 802.11n (Fast Ethernet)',
    105: 'AirPort Extreme 802.11n (Gigabit Ethernet)',
    115: 'AirPort Express 2nd generation (A1392)',
    120: 'AirPort Extreme 802.11ac (6th gen)',
}

# (syAP, syVs) combinations verified end to end; see "Compatibility" in ../README.md.
TESTED = {(115, '7.8.1')}


def product_label(v):
    return PRODUCTS.get(v, f'unknown product {v}')
