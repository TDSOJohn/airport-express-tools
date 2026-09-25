/* dhcpc: a one-shot DHCPv4 client over raw /dev/bpf that only *reports* the lease.
 *
 * It never touches the interface: no address, no route, no resolv.conf. The caller
 * (airportctl/payload/autorun.sh) applies the lease itself, because on the Express
 * setting an address re-inits the station vap and drops the WPA keys, so the address
 * must go on before a fresh 4-way handshake (docs/join-mode.md). The stock
 * /sbin/dhclient can't be used for this: it registers its RPCs with ACPd and reports
 * every lease to ACPd's WAN state machine (`dhcp.client.lease.accept`).
 *
 * Usage: dhcpc [-t SECS] [-h HOSTNAME] [-r IP | -c IP [-s SERVER -m MAC]] IFACE
 *   (none)   INIT: DISCOVER, OFFER, REQUEST, ACK
 *   -r IP    INIT-REBOOT: ask for IP again (after a reboot), broadcast
 *   -c IP    renew IP: ciaddr=IP; unicast to SERVER at MAC with -s/-m (RENEWING),
 *            otherwise broadcast (REBINDING)
 *   -t SECS  give up after SECS (default 30); retransmits at 2, 4, 8, 8 ... s
 *   -h NAME  hostname option (default: gethostname() up to the first dot; -h '' = none)
 * On ACK prints shell assignments (DHCP_IP= DHCP_MASK= DHCP_ROUTER= DHCP_DNS= DHCP_SERVER=
 * DHCP_SERVER_MAC= DHCP_LEASE= DHCP_T1= DHCP_T2=) and exits 0; exits 2 on NAK, 1 otherwise.
 *
 * Build: ./build.sh src/dhcpc.c build/dhcpc -Iwpa-build/compat -Os
 * (compat/net/if.h: this kernel's if_msghdr is 152 bytes, see wpa-build/README.md).
 * No ARP conflict check (no DHCPDECLINE); the router's own check is relied on.
 */
#include <sys/types.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <net/if.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define BOOTP_MIN	300
#define MAGIC		0x63825363

enum { DISCOVER = 1, OFFER, REQUEST, DECLINE, ACK, NAK, RELEASE };

static unsigned char mac[6], bcast[6] = { 0xff, 0xff, 0xff, 0xff, 0xff, 0xff };
static u_int32_t xid;
static const char *ifname;

struct lease {
	int type;
	u_int32_t yiaddr, mask, router, server, dns[3];
	int ndns;
	long lease, t1, t2;
	unsigned char smac[6];
};

static void die(const char *what)
{
	fprintf(stderr, "dhcpc: %s: %s\n", what, strerror(errno));
	exit(1);
}

static int parse(const unsigned char *f, int n, struct lease *l);

/* Keep a reply of a wanted type (bitmask of 1 << type); ignore useless offers. */
static int keep(const unsigned char *f, int n, int want, struct lease *l)
{
	struct lease t;

	if (!parse(f, n, &t) || !(want & 1 << t.type) ||
	    (t.type == OFFER && (!t.yiaddr || !t.server)))
		return 0;
	*l = t;
	return 1;
}

#ifdef DHCPC_TEST
/* tests/dhcpc_linux.h: the same three functions over AF_PACKET, for a Linux test run */
#include DHCPC_TEST
#else
#include <sys/sysctl.h>
#include <net/if_dl.h>
#include <net/route.h>
#include <net/bpf.h>

static unsigned char *rbuf;
static u_int rlen;

/* The link-level address from the routing sysctl (getifaddrs() in libc.a misparses this
 * kernel's if_msghdr; compat/net/if.h has the right size). */
static int get_mac(const char *dev)
{
	int mib[] = { CTL_NET, AF_ROUTE, 0, AF_LINK, NET_RT_IFLIST, 0 };
	struct if_msghdr *ifm;
	struct sockaddr_dl *sdl;
	unsigned char *buf, *p;
	size_t len;
	int found = 0;

	if (sysctl(mib, 6, NULL, &len, NULL, 0) < 0 || !(buf = malloc(len)))
		return -1;
	if (sysctl(mib, 6, buf, &len, NULL, 0) < 0) {
		free(buf);
		return -1;
	}
	for (p = buf; p < buf + len; p += ifm->ifm_msglen) {
		ifm = (struct if_msghdr *)p;
		sdl = (struct sockaddr_dl *)(ifm + 1);
		if (ifm->ifm_msglen == 0)
			break;
		if (ifm->ifm_type != RTM_IFINFO || !(ifm->ifm_addrs & RTA_IFP) ||
		    sdl->sdl_family != AF_LINK || sdl->sdl_alen != 6 ||
		    sdl->sdl_nlen != strlen(dev) || memcmp(sdl->sdl_data, dev, sdl->sdl_nlen))
			continue;
		memcpy(mac, LLADDR(sdl), 6);
		found = 1;
		break;
	}
	free(buf);
	return found ? 0 : -1;
}

static int open_bpf(const char *dev)
{
	/* ip, udp, not a fragment, udp dst port 68 */
	struct bpf_insn insns[] = {
		BPF_STMT(BPF_LD + BPF_H + BPF_ABS, 12),
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 0x0800, 0, 8),
		BPF_STMT(BPF_LD + BPF_B + BPF_ABS, 23),
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 17, 0, 6),
		BPF_STMT(BPF_LD + BPF_H + BPF_ABS, 20),
		BPF_JUMP(BPF_JMP + BPF_JSET + BPF_K, 0x1fff, 4, 0),
		BPF_STMT(BPF_LDX + BPF_B + BPF_MSH, 14),
		BPF_STMT(BPF_LD + BPF_H + BPF_IND, 16),
		BPF_JUMP(BPF_JMP + BPF_JEQ + BPF_K, 68, 0, 1),
		BPF_STMT(BPF_RET + BPF_K, (u_int)-1),
		BPF_STMT(BPF_RET + BPF_K, 0),
	};
	struct bpf_program prog = { sizeof(insns) / sizeof(insns[0]), insns };
	struct ifreq ifr;
	u_int on = 1, dlt;
	int fd, i;

	fd = open("/dev/bpf", O_RDWR);
	for (i = 0; fd < 0 && i < 16; i++) {
		char name[16];
		snprintf(name, sizeof(name), "/dev/bpf%d", i);
		fd = open(name, O_RDWR);
	}
	if (fd < 0)
		die("open /dev/bpf");
	if (ioctl(fd, BIOCGBLEN, &rlen) < 0 || !(rbuf = malloc(rlen)))
		die("BIOCGBLEN");
	memset(&ifr, 0, sizeof(ifr));
	strlcpy(ifr.ifr_name, dev, sizeof(ifr.ifr_name));
	if (ioctl(fd, BIOCSETIF, &ifr) < 0)
		die(dev);
	if (ioctl(fd, BIOCGDLT, &dlt) < 0 ||
	    (dlt != DLT_EN10MB && (dlt = DLT_EN10MB, ioctl(fd, BIOCSDLT, &dlt) < 0)))
		die("BIOCSDLT DLT_EN10MB");
	if (ioctl(fd, BIOCIMMEDIATE, &on) < 0)
		die("BIOCIMMEDIATE");
	if (ioctl(fd, BIOCSHDRCMPLT, &on) < 0)
		die("BIOCSHDRCMPLT");
	if (ioctl(fd, BIOCSETF, &prog) < 0)
		die("BIOCSETF");
	return fd;
}

/* One read(); it can return several frames, each behind a bpf_hdr. */
static int read_frames(int fd, int want, struct lease *l)
{
	unsigned char *p = rbuf, *end;
	int n;

	if ((n = read(fd, rbuf, rlen)) <= 0)
		return 0;
	for (end = rbuf + n; p + sizeof(struct bpf_hdr) <= end;) {
		struct bpf_hdr *bh = (struct bpf_hdr *)p;
		if (p + bh->bh_hdrlen + bh->bh_caplen > end)
			break;
		if (keep(p + bh->bh_hdrlen, bh->bh_caplen, want, l))
			return 1;
		p += BPF_WORDALIGN(bh->bh_hdrlen + bh->bh_caplen);
	}
	return 0;
}
#endif

static u_int16_t cksum(const unsigned char *p, int n)
{
	u_int32_t s = 0;

	for (; n > 1; p += 2, n -= 2)
		s += p[0] << 8 | p[1];
	if (n)
		s += p[0] << 8;
	while (s >> 16)
		s = (s & 0xffff) + (s >> 16);
	return ~s & 0xffff;
}

static void put16(unsigned char *p, u_int v) { p[0] = v >> 8; p[1] = v; }
static void put32(unsigned char *p, u_int32_t v) { put16(p, v >> 16); put16(p + 2, v); }
static u_int get16(const unsigned char *p) { return p[0] << 8 | p[1]; }
static u_int32_t get32(const unsigned char *p) { return (u_int32_t)get16(p) << 16 | get16(p + 2); }

/* One DHCP message in Ethernet/IP/UDP. Addresses are host order; 0 = leave out. */
static void send_msg(int fd, int type, u_int32_t ciaddr, u_int32_t reqip, u_int32_t server,
		     u_int32_t ipdst, const unsigned char *ethdst, const char *host)
{
	unsigned char f[14 + 20 + 8 + 548], *ip = f + 14, *udp = ip + 20, *b = udp + 8, *o;
	int blen, len;

	memset(f, 0, sizeof(f));
	memcpy(f, ethdst, 6);
	memcpy(f + 6, mac, 6);
	put16(f + 12, 0x0800);

	b[0] = 1; b[1] = 1; b[2] = 6;		/* BOOTREQUEST, Ethernet */
	put32(b + 4, xid);
	if (!ciaddr)
		put16(b + 10, 0x8000);		/* no address yet: ask for broadcast replies */
	put32(b + 12, ciaddr);
	memcpy(b + 28, mac, 6);
	put32(b + 236, MAGIC);
	o = b + 240;
	*o++ = 53; *o++ = 1; *o++ = type;
	*o++ = 61; *o++ = 7; *o++ = 1; memcpy(o, mac, 6); o += 6;
	if (reqip) { *o++ = 50; *o++ = 4; put32(o, reqip); o += 4; }
	if (server) { *o++ = 54; *o++ = 4; put32(o, server); o += 4; }
	if (host && *host) {
		int n = strlen(host);
		*o++ = 12; *o++ = n; memcpy(o, host, n); o += n;
	}
	*o++ = 57; *o++ = 2; put16(o, 576); o += 2;
	{
		static const unsigned char want[] = { 1, 3, 6, 28, 51, 54, 58, 59 };
		*o++ = 55; *o++ = sizeof(want); memcpy(o, want, sizeof(want)); o += sizeof(want);
	}
	*o++ = 255;
	blen = o - b < BOOTP_MIN ? BOOTP_MIN : o - b;

	put16(udp, 68);
	put16(udp + 2, 67);
	put16(udp + 4, 8 + blen);		/* UDP checksum 0 = none (IPv4) */
	ip[0] = 0x45;
	put16(ip + 2, 20 + 8 + blen);
	put16(ip + 4, xid & 0xffff);
	ip[8] = 64;
	ip[9] = 17;
	put32(ip + 12, ciaddr);
	put32(ip + 16, ipdst);
	put16(ip + 10, cksum(ip, 20));

	len = 14 + 20 + 8 + blen;
	if (write(fd, f, len) != len)
		die("write");
}

/* Parse one frame; returns 1 if it is a reply to us, filling *l. */
static int parse(const unsigned char *f, int n, struct lease *l)
{
	const unsigned char *ip = f + 14, *udp, *b, *o, *end;
	int hl, ulen;

	if (n < 14 + 20 || get16(f + 12) != 0x0800 || ip[9] != 17)
		return 0;
	hl = (ip[0] & 15) * 4;
	udp = ip + hl;
	if (udp + 8 > f + n || get16(udp + 2) != 68)
		return 0;
	ulen = get16(udp + 4);
	b = udp + 8;
	end = udp + ulen < f + n ? udp + ulen : f + n;
	if (b + 240 > end || b[0] != 2 || get32(b + 4) != xid || memcmp(b + 28, mac, 6) ||
	    get32(b + 236) != MAGIC)
		return 0;
	memset(l, 0, sizeof(*l));
	l->yiaddr = get32(b + 16);
	memcpy(l->smac, f + 6, 6);
	for (o = b + 240; o < end && *o != 255;) {
		int c = *o++, len;
		if (c == 0)
			continue;
		if (o >= end || o + 1 + *o > end)
			break;
		len = *o++;
		switch (c) {
		case 53: if (len >= 1) l->type = o[0]; break;
		case 1:  if (len >= 4) l->mask = get32(o); break;
		case 3:  if (len >= 4) l->router = get32(o); break;
		case 54: if (len >= 4) l->server = get32(o); break;
		case 51: if (len >= 4) l->lease = get32(o); break;
		case 58: if (len >= 4) l->t1 = get32(o); break;
		case 59: if (len >= 4) l->t2 = get32(o); break;
		case 6:
			for (l->ndns = 0; l->ndns < 3 && (l->ndns + 1) * 4 <= len; l->ndns++)
				l->dns[l->ndns] = get32(o + l->ndns * 4);
			break;
		}
		o += len;
	}
	return l->type != 0;
}

/* Wait up to secs for a reply of one of the wanted types. */
static int wait_reply(int fd, int secs, int want, struct lease *l)
{
	struct timeval start, now, tv;
	fd_set rs;
	long left;
	int n;

	gettimeofday(&start, NULL);
	for (;;) {
		gettimeofday(&now, NULL);
		left = secs * 1000L - ((now.tv_sec - start.tv_sec) * 1000L +
				       (now.tv_usec - start.tv_usec) / 1000);
		if (left <= 0 || left > secs * 1000L)	/* timeout, or the clock jumped */
			return 0;
		tv.tv_sec = left / 1000;
		tv.tv_usec = left % 1000 * 1000;
		FD_ZERO(&rs);
		FD_SET(fd, &rs);
		if ((n = select(fd + 1, &rs, NULL, NULL, &tv)) < 0) {
			if (errno == EINTR)
				continue;
			die("select");
		}
		if (n == 0)
			return 0;
		if (read_frames(fd, want, l))
			return 1;
	}
}

static const char *ip4(u_int32_t a)
{
	static char s[4][16];
	static int i;
	i = (i + 1) & 3;
	snprintf(s[i], sizeof(s[i]), "%u.%u.%u.%u", a >> 24, a >> 16 & 255, a >> 8 & 255, a & 255);
	return s[i];
}

static u_int32_t parse_ip(const char *s)
{
	struct in_addr a;
	if (!inet_aton(s, &a)) {
		fprintf(stderr, "dhcpc: bad address %s\n", s);
		exit(1);
	}
	return ntohl(a.s_addr);
}

/* aa:bb:cc:dd:ee:ff (no sscanf: it drags in libc's hard-float strtod) */
static int parse_mac(const char *s, unsigned char *m)
{
	int i, d, v;

	for (i = 0; i < 6; i++) {
		for (v = 0, d = 0; d < 2; d++, s++) {
			int c = *s;
			if (c >= '0' && c <= '9') v = v * 16 + c - '0';
			else if (c >= 'a' && c <= 'f') v = v * 16 + c - 'a' + 10;
			else if (c >= 'A' && c <= 'F') v = v * 16 + c - 'A' + 10;
			else return -1;
		}
		m[i] = v;
		if (*s != (i < 5 ? ':' : 0))
			return -1;
		s++;
	}
	return 0;
}

static void usage(void)
{
	fprintf(stderr, "usage: dhcpc [-t SECS] [-h HOSTNAME] [-r IP | -c IP [-s SERVER -m MAC]] "
		"IFACE\n");
	exit(1);
}

int main(int argc, char **argv)
{
	static char hostbuf[64];
	const char *host = NULL;
	u_int32_t reboot = 0, renew = 0, server = 0;
	unsigned char smac[6];
	int have_smac = 0, timeout = 30, fd, c, waited, step, type, want;
	struct lease l = { 0 };

	while ((c = getopt(argc, argv, "t:h:r:c:s:m:")) != -1) {
		switch (c) {
		case 't': timeout = atoi(optarg); break;
		case 'h': host = optarg; break;
		case 'r': reboot = parse_ip(optarg); break;
		case 'c': renew = parse_ip(optarg); break;
		case 's': server = parse_ip(optarg); break;
		case 'm':
			if (parse_mac(optarg, smac) < 0)
				usage();
			have_smac = 1;
			break;
		default: usage();
		}
	}
	if (optind != argc - 1 || timeout < 1 || (reboot && renew) ||
	    ((server || have_smac) && !renew) || (server && !have_smac) || (have_smac && !server))
		usage();
	ifname = argv[optind];
	if (!host) {	/* hostname up to the first dot, letters/digits/hyphens only */
		char *p;
		if (gethostname(hostbuf, sizeof(hostbuf) - 1) == 0) {
			for (p = hostbuf; *p && *p != '.'; p++)
				if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
				      (*p >= '0' && *p <= '9') || *p == '-'))
					*p = '-';
			*p = 0;
		}
		host = hostbuf;
	}
	if (get_mac(ifname) < 0) {
		fprintf(stderr, "dhcpc: no link-level address for %s\n", ifname);
		return 1;
	}
	fd = open_bpf(ifname);
	xid = arc4random();

	/* INIT goes through an OFFER first; INIT-REBOOT and renewals go straight to REQUEST. */
	type = reboot || renew ? REQUEST : DISCOVER;
	for (waited = 0, step = 2;;) {
		if (type == DISCOVER)
			send_msg(fd, DISCOVER, 0, 0, 0, 0xffffffff, bcast, host);
		else if (reboot)
			send_msg(fd, REQUEST, 0, reboot, 0, 0xffffffff, bcast, host);
		else if (renew && server)
			send_msg(fd, REQUEST, renew, 0, 0, server, smac, host);
		else if (renew)
			send_msg(fd, REQUEST, renew, 0, 0, 0xffffffff, bcast, host);
		else	/* REQUEST for the OFFER in l */
			send_msg(fd, REQUEST, 0, l.yiaddr, l.server, 0xffffffff, bcast, host);
		if (step > timeout - waited)
			step = timeout - waited;
		want = type == DISCOVER ? 1 << OFFER : 1 << ACK | 1 << NAK;
		if (wait_reply(fd, step, want, &l)) {
			if (l.type == OFFER) {
				type = REQUEST;		/* keep the clock running for the whole exchange */
				continue;
			}
			if (l.type == NAK) {
				fprintf(stderr, "dhcpc: NAK from %s\n", ip4(l.server));
				return 2;
			}
			break;	/* ACK */
		}
		waited += step;
		if (waited >= timeout) {
			fprintf(stderr, "dhcpc: no %s on %s after %d s\n",
				type == DISCOVER ? "offer" : "answer", ifname, timeout);
			return 1;
		}
		if (step < 8)
			step *= 2;
	}
	if (!l.yiaddr) {
		fprintf(stderr, "dhcpc: ACK without an address\n");
		return 1;
	}
	if (!l.mask)	/* classful default, as dhclient does */
		l.mask = l.yiaddr >> 31 == 0 ? 0xff000000 : l.yiaddr >> 30 == 2 ? 0xffff0000 :
			 0xffffff00;
	if (!l.lease)
		l.lease = 3600;
	if (!l.t1 || l.t1 >= l.lease)
		l.t1 = l.lease / 2;
	if (!l.t2 || l.t2 >= l.lease || l.t2 <= l.t1)
		l.t2 = l.lease * 7 / 8;
	printf("DHCP_IP=%s\nDHCP_MASK=%s\n", ip4(l.yiaddr), ip4(l.mask));
	printf("DHCP_ROUTER=%s\n", l.router ? ip4(l.router) : "");
	printf("DHCP_DNS=\"");
	for (c = 0; c < l.ndns; c++)
		printf("%s%s", c ? " " : "", ip4(l.dns[c]));
	printf("\"\nDHCP_SERVER=%s\n", ip4(l.server));
	printf("DHCP_SERVER_MAC=%02x:%02x:%02x:%02x:%02x:%02x\n", l.smac[0], l.smac[1], l.smac[2],
	       l.smac[3], l.smac[4], l.smac[5]);
	printf("DHCP_LEASE=%ld\nDHCP_T1=%ld\nDHCP_T2=%ld\n", l.lease, l.t1, l.t2);
	return 0;
}
