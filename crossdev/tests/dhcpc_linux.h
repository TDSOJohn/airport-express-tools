/* Linux stand-ins for dhcpc.c's three BSD-only functions, so the protocol code can be
 * tested on the build machine against a real DHCP server (tests/dhcpc-test.sh).
 * Included by src/dhcpc.c when built with -DDHCPC_TEST='"<this file>"'. */
#include <linux/if_packet.h>
#include <net/ethernet.h>

static int get_mac(const char *dev)
{
	struct ifreq ifr;
	int s = socket(AF_INET, SOCK_DGRAM, 0);

	memset(&ifr, 0, sizeof(ifr));
	strncpy(ifr.ifr_name, dev, sizeof(ifr.ifr_name) - 1);
	if (s < 0 || ioctl(s, SIOCGIFHWADDR, &ifr) < 0)
		return -1;
	close(s);
	memcpy(mac, ifr.ifr_hwaddr.sa_data, 6);
	return 0;
}

static int open_bpf(const char *dev)
{
	struct sockaddr_ll sll;
	int fd = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_IP));

	if (fd < 0)
		die("socket(AF_PACKET)");
	memset(&sll, 0, sizeof(sll));
	sll.sll_family = AF_PACKET;
	sll.sll_protocol = htons(ETH_P_IP);
	if (!(sll.sll_ifindex = if_nametoindex(dev)) ||
	    bind(fd, (struct sockaddr *)&sll, sizeof(sll)) < 0)
		die(dev);
	return fd;
}

static int read_frames(int fd, int want, struct lease *l)
{
	unsigned char f[2048];
	int n = recv(fd, f, sizeof(f), 0);

	return n > 0 && keep(f, n, want, l);
}
