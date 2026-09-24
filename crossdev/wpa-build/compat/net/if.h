/*
 * Apple's NetBSD 4.0_STABLE kernel on the AirPort Express sends 152-byte
 * struct if_msghdr (RTM_IFINFO), 8 bytes more than the stock NetBSD 4.0
 * header (144): same fields at the same offsets, then 8 extra bytes after
 * ifm_data, before the trailing sockaddrs. Code that finds the sockaddr_dl
 * at (ifm + 1) --- getifaddrs(), l2_packet_freebsd's eth_get() --- must use
 * the kernel's size. Measured on-device from NET_RT_IFLIST (2026-09-23).
 */
#ifndef _APPLE_COMPAT_NET_IF_H_
#define _APPLE_COMPAT_NET_IF_H_

#define if_msghdr if_msghdr_netbsd40
#include_next <net/if.h>
#undef if_msghdr

struct if_msghdr {
	u_short	ifm_msglen;
	u_char	ifm_version;
	u_char	ifm_type;
	int	ifm_addrs;
	int	ifm_flags;
	u_short	ifm_index;
	struct	if_data ifm_data;
	u_int32_t ifm_apple_pad[2];	/* kernel extension, always 0 seen */
};

typedef char __apple_if_msghdr_size_check[sizeof(struct if_msghdr) == 152 ? 1 : -1];

#endif /* _APPLE_COMPAT_NET_IF_H_ */
