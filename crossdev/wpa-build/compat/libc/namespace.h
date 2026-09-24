/* Stand-in for libc's private namespace.h when building getifaddrs.c outside libc:
 * define the _-prefixed names that libc's own callers (if_nametoindex.o ...) reference,
 * so this object replaces libc.a's getifaddrs.o at link time. */
#define getifaddrs _getifaddrs
#define freeifaddrs _freeifaddrs
