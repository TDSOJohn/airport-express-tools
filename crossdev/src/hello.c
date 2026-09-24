/*
 * hello.c - "hello world" for the AirPort Express A1392, linked statically
 * against the NetBSD 4.0 libc from the sgimips (big-endian MIPS) release sets.
 * Build with ../build.sh.
 */
#include <sys/utsname.h>

#include <stdio.h>
#include <unistd.h>

int
main(int argc, char **argv)
{
	struct utsname u;
	int i;

	printf("Hello from the AirPort Express! (static NetBSD 4.0 libc)\n");
	if (uname(&u) == 0)
		printf("  %s %s on %s, pid %d\n", u.sysname, u.release,
		    u.machine, (int)getpid());
	for (i = 0; i < argc; i++)
		printf("  argv[%d] = %s\n", i, argv[i]);
	return 0;
}
