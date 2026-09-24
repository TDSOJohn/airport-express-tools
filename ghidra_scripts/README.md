# Ghidra headless scripts for ACPd

Drop-in `-scriptPath` scripts used to produce everything in [`../docs/`](../docs/). They assume
an import of `/sbin/ACPd` as described in [../docs/extracting-acpd.md](../docs/extracting-acpd.md)
(MIPS:BE:32:default, image base `0x00400000`), in a project called `acpd`.

Common invocation — note `-process ACPd.bin`, without which headless runs against no program and
every script sees `null`:

```sh
JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java)))) \
/path/to/ghidra/support/analyzeHeadless "$PWD/ghidra_project" acpd \
  -process ACPd.bin -readOnly -noanalysis \
  -scriptPath "$PWD/ghidra_scripts" -postScript <Script>.java <args...>
```

Script output arrives on stdout as `INFO  <Script>.java> …` lines; filter with
`grep -E '<Script>.java>'`.

| script | args | what it does |
|---|---|---|
| **NameFuncs** | `[outfile]` | Recovers ~2310 function names from the `__func__` strings ACPd passes to its lock/log wrappers. **Run this first.** |
| **Decompile** | `<outdir> 0xADDR…` | Decompiles each function to `<outdir>/<name>.c`, with its callers and callees in a header comment. |
| **Xrefs** | `0xADDR[:span]…` | References to an address (or to anything in `[addr, addr+span)`), with the referencing instruction and its function. |
| **ImmScan** | `0xIMM…` | Finds 32-bit immediates, including MIPS `lui`+`ori`/`addiu` pairs — this is how you find fourcc constants like `0x6374696d` (`ctim`). |
| **FindStr** | `str…` | Byte-sequence search, reporting VMA and containing function. |
| **DumpStr** | `0xADDR` or `0xSTART-0xEND` | Prints C strings in a range (handy for walking a string table). |
| **RpcMap** | `0x6717dc [outfile]` (ACPd's own) or `0x80b058` (other daemons') | Every ACP RPC registration: name, flags, handler and the parameter schema. Reconstructs o32 arguments (a0-a3 + the outgoing stack area) at each call site. Produced [../docs/rpc-surface.md](../docs/rpc-surface.md). |
| **DumpIns** | `0xSTART 0xEND` | Mnemonic, operand count and resolved operand objects per instruction — for when Ghidra's rendering surprises you (`addu rd,zero,zero` prints as `clear rd`; delay-slot instructions get a `_` prefix). |
| **FindStore** | `0xOFFSET [imm]` | Every `sw`/`sh`/`sb` at a given struct offset, optionally only where the stored register was just loaded with `imm`. Used to trace who writes `ctx+0x24`. |
| **Recon** | — | First-pass overview of the program. |

Two conventions worth knowing when reading the results:

* `strings -t x` prints **file** offsets; **VMA = file offset + 0x400000**.
* ACPd's plist accessors take format keys: `%ks:<type>` keys are plain C strings, while
  `%kO:<type>` keys are *inline* CoreFoundation constant CFStrings — read the text at `vma+8`,
  not the pointer value. `%kC=%i` / `%kC=%O` are fourcc-keyed setters.
