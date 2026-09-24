/*
 * hello_raw.c - freestanding "hello world" for the AirPort Express A1392
 * (NetBSD 4.0_STABLE, Atheros AR7240 = MIPS 24Kc, big-endian, o32 ABI).
 *
 * No libc, no startup files: a static ELF that talks to the kernel through
 * raw NetBSD syscalls. Build with ../build.sh.
 */

/* NetBSD refuses to exec a native ELF binary that lacks this note. */
__asm__(
"	.section .note.netbsd.ident,\"a\",@note\n"
"	.p2align 2\n"
"	.long	7, 4, 1\n"		/* namesz, descsz, NT_NETBSD_IDENT */
"	.ascii	\"NetBSD\\0\\0\"\n"
"	.long	400000003\n"		/* __NetBSD_Version__ 4.0, as the device's own binaries */
"	.previous\n"
);

/*
 * long nb_syscall(long num, long a0, long a1, long a2)
 * NetBSD/mips: number in v0, arguments in a0-a2, then `syscall`.
 * The kernel clears a3 on success, or sets it and puts errno in v0.
 * Returns the result, or -errno.
 */
__asm__(
"	.text\n"
"	.set	noreorder\n"
"	.globl	nb_syscall\n"
"nb_syscall:\n"
"	move	$2, $4\n"
"	move	$4, $5\n"
"	move	$5, $6\n"
"	move	$6, $7\n"
"	syscall\n"
"	bnez	$7, 1f\n"
"	nop\n"
"	jr	$31\n"
"	nop\n"
"1:	jr	$31\n"
"	subu	$2, $0, $2\n"
"	.set	reorder\n"
);

/*
 * Entry point. The kernel puts the initial stack pointer (argc, argv..., 0,
 * envp..., 0) in both sp and a0.
 */
__asm__(
"	.text\n"
"	.set	noreorder\n"
"	.globl	__start\n"
"__start:\n"
"	move	$9, $4\n"
"	lw	$4, 0($9)\n"		/* argc */
"	addiu	$5, $9, 4\n"		/* argv */
"	li	$8, -8\n"
"	and	$29, $29, $8\n"		/* 8-byte stack alignment */
"	jal	main\n"
"	addiu	$29, $29, -16\n"	/* o32 home space for main's arguments */
"	move	$5, $2\n"
"	jal	nb_syscall\n"
"	li	$4, 1\n"		/* SYS_exit */
"	.set	reorder\n"
);

enum { SYS_exit = 1, SYS_write = 4 };

long nb_syscall(long num, long a0, long a1, long a2);

static unsigned long
slen(const char *s)
{
	const char *p = s;

	while (*p)
		p++;
	return p - s;
}

static void
say(const char *s)
{
	nb_syscall(SYS_write, 1, (long)s, (long)slen(s));
}

int
main(int argc, char **argv)
{
	int i;

	say("Hello from the AirPort Express! (freestanding, raw syscalls)\n");
	for (i = 0; i < argc; i++) {
		say("  arg: ");
		say(argv[i]);
		say("\n");
	}
	return 0;
}
