/* libc.a's getgrnam() drags in NIS, hesiod, the DNS resolver, SunRPC and Berkeley DB
 * (~350 KB). wpa_supplicant calls it only for ctrl_interface_group, which we never set. */
#include <stddef.h>
struct group;
struct group *getgrnam(const char *name) { (void)name; return NULL; }
