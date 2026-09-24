// Find byte sequences in memory; print VMA + containing function (if any).
// Usage: -postScript FindStr.java raWM raWE raCr raSk
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

public class FindStr extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        FunctionManager fm = currentProgram.getFunctionManager();
        for (String s : args) {
            println("### '" + s + "'");
            byte[] pat = s.getBytes("ASCII");
            Address a = currentProgram.getMinAddress();
            while (a != null) {
                Address hit = find(a, pat);
                if (hit == null) break;
                Function f = fm.getFunctionContaining(hit);
                boolean incode = currentProgram.getListing().getInstructionContaining(hit) != null;
                println(String.format("  %s  %s%s", hit,
                    incode ? "[CODE]" : "[data]",
                    f == null ? "" : "  func=" + f.getName() + "@" + f.getEntryPoint()));
                a = hit.add(1);
            }
        }
    }
}
