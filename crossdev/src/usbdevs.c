/*
 * usbdevs.c - lists the USB devices on the Express and which kernel driver
 * claimed each one (like NetBSD's `usbdevs -v`), via USB_DEVICEINFO on /dev/usbN.
 */
#include <sys/types.h>
#include <sys/ioctl.h>

#include <dev/usb/usb.h>

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int
main(int argc, char **argv)
{
	struct usb_device_info di;
	char path[16];
	int bus, addr, i, fd;

	for (bus = 0; bus < 4; bus++) {
		snprintf(path, sizeof(path), "/dev/usb%d", bus);
		if ((fd = open(path, O_RDONLY)) == -1) {
			printf("%s: %s\n", path, strerror(errno));
			continue;
		}
		for (addr = 1; addr < USB_MAX_DEVICES; addr++) {
			memset(&di, 0, sizeof(di));
			di.udi_addr = addr;
			if (ioctl(fd, USB_DEVICEINFO, &di) == -1)
				continue;
			printf("%s addr %d: %04x:%04x \"%s\" by \"%s\", class %u/%u/%u, "
			    "speed %u, power %d mA, ports %d\n", path, addr,
			    di.udi_vendorNo, di.udi_productNo, di.udi_product,
			    di.udi_vendor, di.udi_class, di.udi_subclass,
			    di.udi_protocol, di.udi_speed, di.udi_power, di.udi_nports);
			for (i = 0; i < USB_MAX_DEVNAMES; i++)
				if (di.udi_devnames[i][0] != '\0')
					printf("    driver: %s\n", di.udi_devnames[i]);
		}
		close(fd);
	}
	return 0;
}
