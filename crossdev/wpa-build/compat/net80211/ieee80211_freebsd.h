/* compat shim: NetBSD's routing-event 802.11 defs live in ieee80211_netbsd.h.
 * Provides RTM_IEEE80211_*, struct ieee80211_michael_event for driver_bsd.c. */
#ifndef _COMPAT_NET80211_IEEE80211_FREEBSD_H
#define _COMPAT_NET80211_IEEE80211_FREEBSD_H
#include <net80211/ieee80211_netbsd.h>
#endif
