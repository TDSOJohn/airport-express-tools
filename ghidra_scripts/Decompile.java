// Decompile one or more functions (by hex address); write C to <outdir>/<name>.c
// Usage: -postScript Decompile.java <outdir> 0x682190 [0x...]
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import java.io.*;
import java.util.*;

public class Decompile extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) { println("usage: <outdir> <addr...>"); return; }
        File outdir = new File(args[0]);
        outdir.mkdirs();
        FunctionManager fm = currentProgram.getFunctionManager();
        Address base = currentProgram.getImageBase();

        DecompInterface dec = new DecompInterface();
        dec.toggleCCode(true);
        dec.toggleSyntaxTree(true);
        dec.setSimplificationStyle("decompile");
        dec.openProgram(currentProgram);

        for (int i = 1; i < args.length; i++) {
            long v = Long.decode(args[i]);
            Address a = base.getNewAddress(v);
            Function f = fm.getFunctionContaining(a);
            if (f == null) { println("0x" + Long.toHexString(v) + " : NO FUNCTION"); continue; }

            StringBuilder sb = new StringBuilder();
            sb.append("// ").append(f.getName()).append("  entry=").append(f.getEntryPoint())
              .append("  size=").append(f.getBody().getNumAddresses()).append(" bytes\n");
            Set<Function> callers = f.getCallingFunctions(monitor);
            sb.append("// CALLERS(").append(callers.size()).append("): ");
            for (Function c : callers) sb.append(c.getName()).append(" ");
            sb.append("\n");
            Set<Function> callees = f.getCalledFunctions(monitor);
            sb.append("// CALLEES(").append(callees.size()).append("): ");
            for (Function c : callees) sb.append(c.getName()).append(" ");
            sb.append("\n\n");

            DecompileResults r = dec.decompileFunction(f, 180, monitor);
            if (r != null && r.decompileCompleted()) {
                sb.append(r.getDecompiledFunction().getC());
            } else {
                sb.append("// DECOMPILE FAILED: ").append(r == null ? "null" : r.getErrorMessage());
            }
            File out = new File(outdir, f.getName() + ".c");
            try (PrintWriter pw = new PrintWriter(new FileWriter(out))) { pw.print(sb); }
            println("wrote " + out.getAbsolutePath() + " (" + f.getName() + ")");
        }
        dec.dispose();
    }
}
