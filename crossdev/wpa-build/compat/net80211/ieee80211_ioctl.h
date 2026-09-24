/*
 * Apple's AirPort Express kernel is NetBSD 4.0_STABLE underneath but carries
 * FreeBSD 8-era (vap, 802.11n) net80211, so the 802.11 ioctl ABI is FreeBSD 8's,
 * not the one in the NetBSD 4.0 sysroot header. Found from Apple's own ifconfig
 * in /sbin/ACPd (the crunched userland) and verified on-device (2026-09-23):
 *
 *  - SIOCS80211/SIOCG80211 are FreeBSD's _IOW/_IOWR('i', 234/235) =
 *    0x801c69ea/0xc01c69eb; NetBSD's 244/245 get ENOTTY. NetBSD's private
 *    SIOC[SG]80211{NWID,NWKEY,POWER,CHANNEL,BSSID} don't exist there (and POWER
 *    collides with 234/235), so they are removed: callers then use the generic ops.
 *  - IEEE80211_IOC_SCAN_RESULTS is 76 (Apple's ifconfig: get80211len(s, 76, buf,
 *    24576, ...)); 24 gets EINVAL. SCAN_REQ is 103 with struct ieee80211_scan_req.
 *  - IEEE80211_IOC_OPTIE (22) is gone; the WPA/RSN IE goes via IEEE80211_IOC_APPIE.
 *  - The scan result record is FreeBSD 7.x's (isr_ie_off, no isr_meshid_len):
 *    Apple's ifconfig reads ssid_len at byte 37 and rejects records < 38 bytes,
 *    and wpa_supplicant finds the SSID at (sr + 1), so sizeof must be 38.
 *
 * Everything else wpa_supplicant uses (ieee80211req, _key, _del_key, _mlme, the
 * RTM_IEEE80211_* events and their structs) is byte-identical between the two.
 * Definitions below are from FreeBSD stable/8 sys/net80211/ieee80211_ioctl.h
 * (scan result: stable/7).
 */
#ifndef _APPLE_COMPAT_NET80211_IEEE80211_IOCTL_H_
#define _APPLE_COMPAT_NET80211_IEEE80211_IOCTL_H_

#define ieee80211req_scan_result ieee80211req_scan_result_netbsd40
#include_next <net80211/ieee80211_ioctl.h>
#undef ieee80211req_scan_result

#undef SIOCS80211
#undef SIOCG80211
#undef SIOCG80211STATS
#define	SIOCS80211		 _IOW('i', 234, struct ieee80211req)
#define	SIOCG80211		_IOWR('i', 235, struct ieee80211req)
#define	SIOCG80211STATS		_IOWR('i', 236, struct ifreq)

#undef SIOCS80211NWID
#undef SIOCG80211NWID
#undef SIOCS80211NWKEY
#undef SIOCG80211NWKEY
#undef SIOCS80211POWER
#undef SIOCG80211POWER
#undef SIOCS80211CHANNEL
#undef SIOCG80211CHANNEL
#undef SIOCS80211BSSID
#undef SIOCG80211BSSID

#undef IEEE80211_IOC_OPTIE
#define	IEEE80211_IOC_APPIE		95	/* application IE's */
#define	IEEE80211_MAX_APPIE		1024	/* max app IE data */
#define	IEEE80211_APPIE_WPA \
	(IEEE80211_FC0_TYPE_MGT | IEEE80211_FC0_SUBTYPE_BEACON | \
	 IEEE80211_FC0_SUBTYPE_PROBE_RESP)

#undef IEEE80211_IOC_SCAN_REQ
#undef IEEE80211_IOC_SCAN_RESULTS
#define	IEEE80211_IOC_SCAN_RESULTS	76	/* get scan results */
#define	IEEE80211_IOC_SCAN_REQ		103	/* scan w/ specified params */
#define	IEEE80211_IOC_SCAN_CANCEL	104	/* cancel ongoing scan */

struct ieee80211_scan_req {
	int		sr_flags;
#define	IEEE80211_IOC_SCAN_NOPICK	0x00001	/* scan only, no selection */
#define	IEEE80211_IOC_SCAN_ACTIVE	0x00002	/* active scan (probe req) */
#define	IEEE80211_IOC_SCAN_PICK1ST	0x00004	/* ``hey sailor'' mode */
#define	IEEE80211_IOC_SCAN_BGSCAN	0x00008	/* bg scan, exit ps at end */
#define	IEEE80211_IOC_SCAN_ONCE		0x00010	/* do one complete pass */
#define	IEEE80211_IOC_SCAN_NOBCAST	0x00020	/* don't send bcast probe req */
#define	IEEE80211_IOC_SCAN_NOJOIN	0x00040	/* no auto-sequencing */
#define	IEEE80211_IOC_SCAN_FLUSH	0x10000	/* flush scan cache first */
#define	IEEE80211_IOC_SCAN_CHECK	0x20000	/* check scan cache first */
	u_int		sr_duration;		/* duration (ms) */
#define	IEEE80211_IOC_SCAN_DURATION_MIN	1
#define	IEEE80211_IOC_SCAN_DURATION_MAX	0x7fffffff
#define	IEEE80211_IOC_SCAN_FOREVER	IEEE80211_IOC_SCAN_DURATION_MAX
	u_int		sr_mindwell;		/* min channel dwelltime (ms) */
	u_int		sr_maxdwell;		/* max channel dwelltime (ms) */
	int		sr_nssid;
#define	IEEE80211_IOC_SCAN_MAX_SSID	3
	struct {
		int	 len;				/* length in bytes */
		u_int8_t ssid[IEEE80211_NWID_LEN];	/* ssid contents */
	} sr_ssid[IEEE80211_IOC_SCAN_MAX_SSID];
};

struct ieee80211req_scan_result {
	u_int16_t	isr_len;		/* total length (mult of 4) */
	u_int16_t	isr_ie_off;		/* offset to SSID+IE data */
	u_int16_t	isr_ie_len;		/* IE length */
	u_int16_t	isr_freq;		/* MHz */
	u_int16_t	isr_flags;		/* channel flags */
	int8_t		isr_noise;
	int8_t		isr_rssi;
	u_int8_t	isr_intval;		/* beacon interval */
	u_int8_t	isr_capinfo;		/* capabilities */
	u_int8_t	isr_erp;		/* ERP element */
	u_int8_t	isr_bssid[IEEE80211_ADDR_LEN];
	u_int8_t	isr_nrates;
	u_int8_t	isr_rates[IEEE80211_RATE_MAXSIZE];
	u_int8_t	isr_ssid_len;		/* SSID length */
	/* variable length SSID followed by IE data (at isr_ie_off) */
};
typedef char __apple_scan_result_size_check[sizeof(struct ieee80211req_scan_result) == 38 ? 1 : -1];

#endif /* _APPLE_COMPAT_NET80211_IEEE80211_IOCTL_H_ */
