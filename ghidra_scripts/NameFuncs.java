// Recover function names from embedded __func__ strings referenced inside each function.
// Many ACPd helpers call log/lock wrappers with their own name as the first arg.
// Usage: -postScript NameFuncs.java [outfile]
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class NameFuncs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        PrintWriter pw = args.length > 0 ? new PrintWriter(new FileWriter(args[0])) : null;
        FunctionManager fm = currentProgram.getFunctionManager();
        ReferenceManager rm = currentProgram.getReferenceManager();
        Memory mem = currentProgram.getMemory();
        FunctionIterator fit = fm.getFunctions(true);
        int named = 0, total = 0;
        while (fit.hasNext()) {
            Function f = fit.next();
            total++;
            Map<String,Integer> cand = new LinkedHashMap<>();
            AddressIterator ai = rm.getReferenceSourceIterator(f.getBody(), true);
            while (ai.hasNext()) {
                Address from = ai.next();
                for (Reference r : rm.getReferencesFrom(from)) {
                    if (!r.getReferenceType().isData()) continue;
                    String s = cstr(mem, r.getToAddress(), 64);
                    if (s == null) continue;
                    if (!s.matches("[A-Za-z_][A-Za-z0-9_]{3,63}")) continue;
                    cand.merge(s, 1, Integer::sum);
                }
            }
            if (cand.isEmpty()) continue;
            String best = null; int bn = 0;
            for (Map.Entry<String,Integer> e : cand.entrySet())
                if (e.getValue() > bn) { bn = e.getValue(); best = e.getKey(); }
            named++;
            String line = String.format("%s %s  n=%d  all=%s", f.getEntryPoint(), best, bn, cand.keySet());
            if (pw != null) pw.println(line); else println(line);
        }
        if (pw != null) pw.close();
        println("### functions=" + total + " with-string-candidates=" + named);
    }
    private String cstr(Memory mem, Address a, int max) {
        StringBuilder sb = new StringBuilder();
        try {
            for (int i = 0; i < max; i++) {
                byte b = mem.getByte(a.add(i));
                if (b == 0) return sb.length() > 0 ? sb.toString() : null;
                if (b < 0x20 || b > 0x7e) return null;
                sb.append((char) b);
            }
        } catch (Exception e) { return null; }
        return null;
    }
}
