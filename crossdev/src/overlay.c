/*
 * overlay.c - proof that the Express can bring code into memory and execute it
 * *while the program is running*, then swap it for other code in the same buffer.
 * This is the mechanism behind "streaming" a program: the bytes below could just
 * as well arrive over a socket. On MIPS the catch is the I-cache, which must be
 * synced after writing code (sysarch(MIPS_CACHEFLUSH)) or the CPU runs stale bytes.
 */
#include <sys/types.h>
#include <sys/mman.h>

#include <mips/cachectl.h>	/* ICACHE/DCACHE/BCACHE */
#include <mips/sysarch.h>	/* MIPS_CACHEFLUSH, struct mips_cacheflush_args */

#include <stdio.h>
#include <string.h>

/* Two hand-assembled MIPS-I leaf functions, big-endian machine code. */
static const unsigned char chunkA[] = {	/* int a(void)   { return 0x1234; } */
	0x34, 0x02, 0x12, 0x34,		/* ori   $v0, $zero, 0x1234 */
	0x03, 0xe0, 0x00, 0x08,		/* jr    $ra                */
	0x00, 0x00, 0x00, 0x00,		/* nop        (delay slot)  */
};
static const unsigned char chunkB[] = {	/* int b(int x)  { return x + 1; }  */
	0x24, 0x82, 0x00, 0x01,		/* addiu $v0, $a0, 1        */
	0x03, 0xe0, 0x00, 0x08,		/* jr    $ra               */
	0x00, 0x00, 0x00, 0x00,		/* nop       (delay slot)  */
};

/* Copy code into the buffer, sync the caches over it, and make it executable. */
static void
load(void *slot, const void *code, unsigned len)
{
	struct mips_cacheflush_args ca;

	memcpy(slot, code, len);
	ca.va = (vaddr_t)slot;
	ca.nbytes = len;
	ca.whichcache = BCACHE;		/* flush D-cache to RAM, invalidate I-cache */
	if (sysarch(MIPS_CACHEFLUSH, &ca) == -1)
		perror("cacheflush");
	if (mprotect(slot, len, PROT_READ | PROT_EXEC) == -1)
		perror("mprotect");
}

int
main(void)
{
	void *slot;
	int (*a)(void);
	int (*b)(int);

	/* One page, writable now so we can drop code in, then flipped to exec per load. */
	slot = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
	if (slot == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	printf("code buffer mapped at %p\n", slot);

	load(slot, chunkA, sizeof chunkA);
	a = (int (*)(void))slot;
	printf("chunk A -> 0x%x  (expect 0x1234)\n", a());

	/* Same buffer, different code streamed in over the top. */
	if (mprotect(slot, 4096, PROT_READ | PROT_WRITE) == -1)
		perror("mprotect back to rw");
	load(slot, chunkB, sizeof chunkB);
	b = (int (*)(int))slot;
	printf("chunk B(41) -> %d  (expect 42)\n", b(41));

	munmap(slot, 4096);
	return 0;
}
