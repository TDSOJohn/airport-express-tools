/*
 * Soft-float __setjmp14 for the AirPort Express (no FPU, no kernel FPU emulation).
 * The NetBSD 4.0 sgimips libc.a copy saves $f20-$f31 and FCSR with cfc1/swc1,
 * which traps (CpU, CE=1) here; libpcap's pcap_compile() calls setjmp, so every
 * supplicant start died. This is lib/libc/arch/mips/gen/setjmp.S (netbsd-4, 1.17)
 * with the FP block dropped and sc_fpused = 0. Offsets are the ones libc.a's own
 * __setjmp14 uses (struct sigcontext, o32): sc_onstack 0, sc_pc 8, sc_regs 12,
 * sc_fpused 148, sc_mask 320. libc's __longjmp14 is untouched (no FP code).
 */
	.abicalls
	.text
	.align	2
	.globl	__setjmp14
	.ent	__setjmp14
__setjmp14:
	.frame	$sp, 36, $31
	.set	noreorder
	.cpload	$25
	.set	reorder
	subu	$sp, $sp, 36
	.cprestore 16
	sw	$31, 20($sp)
	sw	$4, 36($sp)		# squirrel away sc

	addu	$6, $4, 320		# &sc.sc_mask
	move	$5, $0
	move	$4, $0			# SIG_BLOCK, NULL: just read the mask
	jal	__sigprocmask14

	move	$4, $0
	addu	$5, $sp, 24		# struct sigaltstack on our frame
	jal	__sigaltstack14
	lw	$3, 32($sp)		# old ss_flags
	lw	$4, 36($sp)		# sc
	and	$3, $3, 1		# SS_ONSTACK
	sw	$3, 0($4)		# sc_onstack

	lw	$31, 20($sp)
	addu	$sp, $sp, 36
	bltz	$2, 1f

	sw	$31, 8($4)		# sc_pc = return address
	li	$2, 0xACEDBADE		# sigcontext magic in sc_regs[0]
	sw	$2, 12($4)
	sw	$16, 76($4)		# s0-s7
	sw	$17, 80($4)
	sw	$18, 84($4)
	sw	$19, 88($4)
	sw	$20, 92($4)
	sw	$21, 96($4)
	sw	$22, 100($4)
	sw	$23, 104($4)
	sw	$28, 124($4)		# gp
	sw	$29, 128($4)		# sp
	sw	$30, 132($4)		# s8
	sw	$0, 148($4)		# sc_fpused = 0: no FP state
	move	$2, $0
	j	$31
1:
	jal	abort
	.end	__setjmp14
