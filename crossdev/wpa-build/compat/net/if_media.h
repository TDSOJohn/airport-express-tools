/* compat shim: NetBSD 4.0 spells FreeBSD's IFM_IEEE80211_IBSS as IFM_IEEE80211_ADHOC.
 * Only driver_bsd.c's IBSS (ad-hoc) branch uses it; STA mode passes 0. */
#ifndef _APPLE_COMPAT_NET_IF_MEDIA_H_
#define _APPLE_COMPAT_NET_IF_MEDIA_H_
#include_next <net/if_media.h>
#ifndef IFM_IEEE80211_IBSS
#define IFM_IEEE80211_IBSS IFM_IEEE80211_ADHOC
#endif
#endif
