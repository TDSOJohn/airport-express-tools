// Find references to given hex addresses; print referencing instruction + containing function.
// Also scans references landing anywhere in [addr, addr+span) when a 2nd arg span is given.
// Usage: -postScript Xrefs.java 0x7efc98 [span_hex]
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class Xrefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length == 0) { println("need addr"); return; }
        Address base = currentProgram.getImageBase();
        ReferenceManager rm = currentProgram.getReferenceManager();
        FunctionManager fm = currentProgram.getFunctionManager();
        Listing lst = currentProgram.getListing();

        for (String arg : args) {
          long start; long span = 4;
          if (arg.contains(":")) { String[] p = arg.split(":"); start = Long.decode(p[0]); span = Long.decode(p[1]); }
          else start = Long.decode(arg);
          println("### xrefs to 0x" + Long.toHexString(start) + " span 0x" + Long.toHexString(span));
          for (long off = 0; off < span; off += 4) {
            Address target = base.getNewAddress(start + off);
            ReferenceIterator it = rm.getReferencesTo(target);
            while (it.hasNext()) {
                Reference r = it.next();
                Address from = r.getFromAddress();
                Function f = fm.getFunctionContaining(from);
                Instruction ins = lst.getInstructionAt(from);
                println(String.format("-> target=%s from=%s func=%s  %s [%s]",
                    target, from,
                    f == null ? "(none)" : f.getName() + "@" + f.getEntryPoint(),
                    ins == null ? "(data)" : ins.toString(),
                    r.getReferenceType()));
            }
          }
        }
    }
}
