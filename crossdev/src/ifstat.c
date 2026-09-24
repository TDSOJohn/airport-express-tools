/* Prints per-interface packet counters (netstat -i is missing on the Express).
 * Build with wpa-build/compat on the include path and its getifaddrs.o: the stock
 * libc getifaddrs() misparses this kernel's 152-byte if_msghdr. */
#include <sys/types.h>
#include <sys/socket.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <ifaddrs.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
	struct ifaddrs *ifa, *p;

	if (getifaddrs(&ifa) != 0) { perror("getifaddrs"); return 1; }
	for (p = ifa; p; p = p->ifa_next) {
		struct if_data *d = p->ifa_data;
		if (!p->ifa_addr || p->ifa_addr->sa_family != AF_LINK || !d) continue;
		if (argc > 1 && strcmp(argv[1], p->ifa_name) != 0) continue;
		printf("%-8s ipkts %llu ierrs %llu opkts %llu oerrs %llu ibytes %llu obytes %llu oqdrops? %llu\n",
		    p->ifa_name, (unsigned long long)d->ifi_ipackets, (unsigned long long)d->ifi_ierrors,
		    (unsigned long long)d->ifi_opackets, (unsigned long long)d->ifi_oerrors,
		    (unsigned long long)d->ifi_ibytes, (unsigned long long)d->ifi_obytes,
		    (unsigned long long)d->ifi_iqdrops);
	}
	return 0;
}
