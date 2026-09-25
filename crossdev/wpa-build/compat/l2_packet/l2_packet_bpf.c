/*
 * WPA Supplicant - Layer2 packet handling over raw BPF (no libpcap)
 * Copyright (c) 2003-2005, Jouni Malinen <j@w1.fi>
 * Copyright (c) 2005, Sam Leffler <sam@errno.com>
 *
 * AirPort Express port: l2_packet_freebsd.c with libpcap replaced by direct
 * /dev/bpf calls and a fixed filter program. libpcap's filter compiler resolves
 * host/net/protocol names, which statically links libc's DNS resolver, NIS,
 * SunRPC and Berkeley DB (~500 KB with getgrnam; see build-wpa.sh).
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 *
 * Alternatively, this software may be distributed under the terms of BSD
 * license.
 *
 * See README and COPYING for more details.
 */

#include "includes.h"
#include <net/bpf.h>

#include <sys/ioctl.h>
#include <fcntl.h>
#include <sys/sysctl.h>

#include <net/if.h>
#include <net/if_dl.h>
#include <net/route.h>
#include <netinet/in.h>
#include <ifaddrs.h>

#include "common.h"
#include "eloop.h"
#include "l2_packet.h"


static const u8 pae_group_addr[ETH_ALEN] =
{ 0x01, 0x80, 0xc2, 0x00, 0x00, 0x03 };

struct l2_packet_data {
	int fd;
	u8 *rbuf;
	u_int rbuf_len;
	char ifname[100];
	u8 own_addr[ETH_ALEN];
	void (*rx_callback)(void *ctx, const u8 *src_addr,
			    const u8 *buf, size_t len);
	void *rx_callback_ctx;
	int l2_hdr; /* whether to include layer 2 (Ethernet) header data
		     * buffers */
};


int l2_packet_get_own_addr(struct l2_packet_data *l2, u8 *addr)
{
	os_memcpy(addr, l2->own_addr, ETH_ALEN);
	return 0;
}


int l2_packet_send(struct l2_packet_data *l2, const u8 *dst_addr, u16 proto,
		   const u8 *buf, size_t len)
{
	if (!l2->l2_hdr) {
		int ret;
		struct l2_ethhdr *eth = os_malloc(sizeof(*eth) + len);
		if (eth == NULL)
			return -1;
		os_memcpy(eth->h_dest, dst_addr, ETH_ALEN);
		os_memcpy(eth->h_source, l2->own_addr, ETH_ALEN);
		eth->h_proto = htons(proto);
		os_memcpy(eth + 1, buf, len);
		ret = write(l2->fd, eth, len + sizeof(*eth));
		os_free(eth);
		return ret;
	} else
		return write(l2->fd, buf, len);
}


static void l2_packet_receive(int sock, void *eloop_ctx, void *sock_ctx)
{
	struct l2_packet_data *l2 = eloop_ctx;
	struct bpf_hdr *bh;
	struct l2_ethhdr *ethhdr;
	unsigned char *buf;
	u8 *p, *end;
	ssize_t n;
	size_t len;

	n = read(sock, l2->rbuf, l2->rbuf_len);
	if (n <= 0)
		return;

	/* One read() can return several frames, each behind a bpf_hdr. */
	for (p = l2->rbuf, end = l2->rbuf + n; p + sizeof(*bh) <= end;
	     p += BPF_WORDALIGN(bh->bh_hdrlen + bh->bh_caplen)) {
		bh = (struct bpf_hdr *) p;
		if (p + bh->bh_hdrlen + bh->bh_caplen > end)
			break;
		if (bh->bh_caplen < sizeof(*ethhdr))
			continue;
		ethhdr = (struct l2_ethhdr *) (p + bh->bh_hdrlen);
		if (l2->l2_hdr) {
			buf = (unsigned char *) ethhdr;
			len = bh->bh_caplen;
		} else {
			buf = (unsigned char *) (ethhdr + 1);
			len = bh->bh_caplen - sizeof(*ethhdr);
		}
		l2->rx_callback(l2->rx_callback_ctx, ethhdr->h_source, buf,
				len);
	}
}


static int l2_packet_init_bpf(struct l2_packet_data *l2,
			      unsigned short protocol)
{
	/*
	 * Same frames as the pcap filter in l2_packet_freebsd.c:
	 *   not ether src OWN and (ether dst OWN or ether dst PAE)
	 *   and ether proto PROTOCOL
	 * MACs are compared as a 16-bit + 32-bit load; the k values are
	 * filled in below.
	 */
	struct bpf_insn insns[] = {
		BPF_STMT(BPF_LD + BPF_H + BPF_ABS, 12),		/* 0 type */
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 0, 0, 13),	/* 1 ->15 */
		BPF_STMT(BPF_LD + BPF_H + BPF_ABS, 6),		/* 2 src */
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 0, 0, 2),	/* 3 ->6 */
		BPF_STMT(BPF_LD + BPF_W + BPF_ABS, 8),		/* 4 */
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 0, 9, 0),	/* 5 own->15 */
		BPF_STMT(BPF_LD + BPF_H + BPF_ABS, 0),		/* 6 dst */
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 0, 0, 2),	/* 7 ->10 */
		BPF_STMT(BPF_LD + BPF_W + BPF_ABS, 2),		/* 8 */
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 0, 4, 0),	/* 9 own->14 */
		BPF_STMT(BPF_LD + BPF_H + BPF_ABS, 0),		/* 10 dst */
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 0, 0, 3),	/* 11 ->15 */
		BPF_STMT(BPF_LD + BPF_W + BPF_ABS, 2),		/* 12 */
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 0, 0, 1),	/* 13 ->15 */
		BPF_STMT(BPF_RET + BPF_K, (u_int) -1),		/* 14 accept */
		BPF_STMT(BPF_RET + BPF_K, 0),			/* 15 drop */
	};
	struct bpf_program prog;
	struct ifreq ifr;
	u_int own_hi, own_lo, on = 1, dlt;
	int i;

	own_hi = WPA_GET_BE16(l2->own_addr);
	own_lo = WPA_GET_BE32(l2->own_addr + 2);
	insns[1].k = protocol;
	insns[3].k = insns[7].k = own_hi;
	insns[5].k = insns[9].k = own_lo;
	insns[11].k = WPA_GET_BE16(pae_group_addr);
	insns[13].k = WPA_GET_BE32(pae_group_addr + 2);

	/* NetBSD's /dev/bpf clones; fall back to numbered nodes. */
	l2->fd = open("/dev/bpf", O_RDWR);
	for (i = 0; l2->fd < 0 && i < 16; i++) {
		char dev[16];
		os_snprintf(dev, sizeof(dev), "/dev/bpf%d", i);
		l2->fd = open(dev, O_RDWR);
	}
	if (l2->fd < 0) {
		perror("open(/dev/bpf)");
		return -1;
	}

	if (ioctl(l2->fd, BIOCGBLEN, &l2->rbuf_len) < 0) {
		perror("ioctl[BIOCGBLEN]");
		return -1;
	}
	l2->rbuf = os_malloc(l2->rbuf_len);
	if (l2->rbuf == NULL)
		return -1;

	os_memset(&ifr, 0, sizeof(ifr));
	os_strlcpy(ifr.ifr_name, l2->ifname, sizeof(ifr.ifr_name));
	if (ioctl(l2->fd, BIOCSETIF, &ifr) < 0) {
		fprintf(stderr, "ioctl[BIOCSETIF] %s: %s\n", l2->ifname,
			strerror(errno));
		return -1;
	}
	if (ioctl(l2->fd, BIOCGDLT, &dlt) < 0 ||
	    (dlt != DLT_EN10MB &&
	     (dlt = DLT_EN10MB, ioctl(l2->fd, BIOCSDLT, &dlt) < 0))) {
		perror("ioctl[BIOCSDLT DLT_EN10MB]");
		return -1;
	}
	/* Deliver frames at once instead of when the buffer fills. */
	if (ioctl(l2->fd, BIOCIMMEDIATE, &on) < 0)
		perror("ioctl[BIOCIMMEDIATE]");
	/* We write whole frames, source address included. */
	if (ioctl(l2->fd, BIOCSHDRCMPLT, &on) < 0)
		perror("ioctl[BIOCSHDRCMPLT]");
	if (ioctl(l2->fd, FIONBIO, &on) < 0)
		perror("ioctl[FIONBIO]");

	prog.bf_len = sizeof(insns) / sizeof(insns[0]);
	prog.bf_insns = insns;
	if (ioctl(l2->fd, BIOCSETF, &prog) < 0) {
		perror("ioctl[BIOCSETF]");
		return -1;
	}

	eloop_register_read_sock(l2->fd, l2_packet_receive, l2, NULL);

	return 0;
}


static int eth_get(const char *device, u8 ea[ETH_ALEN])
{
	struct if_msghdr *ifm;
	struct sockaddr_dl *sdl;
	u_char *p, *buf;
	size_t len;
	int mib[] = { CTL_NET, AF_ROUTE, 0, AF_LINK, NET_RT_IFLIST, 0 };
	int found = 0;

	if (sysctl(mib, 6, NULL, &len, NULL, 0) < 0)
		return -1;
	if ((buf = os_malloc(len)) == NULL)
		return -1;
	if (sysctl(mib, 6, buf, &len, NULL, 0) < 0) {
		os_free(buf);
		return -1;
	}
	for (p = buf; p < buf + len; p += ifm->ifm_msglen) {
		ifm = (struct if_msghdr *)p;
		sdl = (struct sockaddr_dl *)(ifm + 1);
		if (ifm->ifm_type != RTM_IFINFO ||
		    (ifm->ifm_addrs & RTA_IFP) == 0)
			continue;
		if (sdl->sdl_family != AF_LINK || sdl->sdl_nlen == 0 ||
		    os_memcmp(sdl->sdl_data, device, sdl->sdl_nlen) != 0)
			continue;
		os_memcpy(ea, LLADDR(sdl), sdl->sdl_alen);
		found = 1;
		break;
	}
	os_free(buf);

	if (!found) {
		errno = ESRCH;
		return -1;
	}
	return 0;
}


struct l2_packet_data * l2_packet_init(
	const char *ifname, const u8 *own_addr, unsigned short protocol,
	void (*rx_callback)(void *ctx, const u8 *src_addr,
			    const u8 *buf, size_t len),
	void *rx_callback_ctx, int l2_hdr)
{
	struct l2_packet_data *l2;

	l2 = os_zalloc(sizeof(struct l2_packet_data));
	if (l2 == NULL)
		return NULL;
	l2->fd = -1;
	os_strlcpy(l2->ifname, ifname, sizeof(l2->ifname));
	l2->rx_callback = rx_callback;
	l2->rx_callback_ctx = rx_callback_ctx;
	l2->l2_hdr = l2_hdr;

	if (eth_get(l2->ifname, l2->own_addr) < 0) {
		fprintf(stderr, "Failed to get link-level address for "
			"interface '%s'.\n", l2->ifname);
		os_free(l2);
		return NULL;
	}

	if (l2_packet_init_bpf(l2, protocol)) {
		if (l2->fd >= 0)
			close(l2->fd);
		os_free(l2->rbuf);
		os_free(l2);
		return NULL;
	}

	return l2;
}


void l2_packet_deinit(struct l2_packet_data *l2)
{
	if (l2 != NULL) {
		if (l2->fd >= 0) {
			eloop_unregister_read_sock(l2->fd);
			close(l2->fd);
		}
		os_free(l2->rbuf);
		os_free(l2);
	}
}


int l2_packet_get_ip_addr(struct l2_packet_data *l2, char *buf, size_t len)
{
	struct ifaddrs *ifap, *ifa;
	struct sockaddr_in *saddr;
	int found = 0;

	if (getifaddrs(&ifap) < 0) {
		wpa_printf(MSG_DEBUG, "getifaddrs: %s", strerror(errno));
		return -1;
	}

	for (ifa = ifap; ifa && !found; ifa = ifa->ifa_next) {
		if (os_strcmp(ifa->ifa_name, l2->ifname) != 0)
			continue;
		saddr = (struct sockaddr_in *) ifa->ifa_addr;
		if (saddr && saddr->sin_family == AF_INET) {
			os_strlcpy(buf, inet_ntoa(saddr->sin_addr), len);
			found = 1;
		}
	}

	freeifaddrs(ifap);

	return found ? 0 : -1;
}


void l2_packet_notify_auth_start(struct l2_packet_data *l2)
{
}
