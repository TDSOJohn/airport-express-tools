/*
 * fptest.c - checks whether floating-point code runs on the Express.
 * Apple's userland contains no FPU instructions (built soft-float) and the
 * AR7240 has no FPU, while the NetBSD 4.0 sgimips libc is hard-float: this
 * only works if the kernel emulates the FPU.
 *
 * Result (2026-09-15, built hard-float with -mfp32): SIGSEGV at the first FPU
 * instruction (cause 0x1000002C = coprocessor 1 unusable), so the kernel has no
 * FPU emulation. build.sh now compiles soft-float, so this fails to link instead.
 */
#include <stdio.h>

int
main(int argc, char **argv)
{
	volatile double x = 1.5;

	printf("before FP\n");
	fflush(stdout);
	x = x * (argc + 1) / 3.0;
	printf("fp: %f (expect %f)\n", x, (double)(argc + 1) / 2.0);
	return 0;
}
