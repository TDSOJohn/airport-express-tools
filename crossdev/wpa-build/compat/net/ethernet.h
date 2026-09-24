/* compat shim: NetBSD 4.0 has no <net/ethernet.h>; forward to its native header.
 * Supplies struct ether_header, ETHER_ADDR_LEN, ETHERTYPE_PAE for driver_bsd.c. */
#ifndef _COMPAT_NET_ETHERNET_H
#define _COMPAT_NET_ETHERNET_H
#include <sys/types.h>
#include <net/if.h>
#include <net/if_ether.h>
#endif
