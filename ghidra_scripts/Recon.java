// Quick recon of the analyzed ACPd project.
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

public class Recon extends GhidraScript {
    @Override
    public void run() throws Exception {
        FunctionManager fm = currentProgram.getFunctionManager();
        int count = fm.getFunctionCount();
        Address base = currentProgram.getImageBase();
        println("IMAGE BASE: " + base);
        println("FUNCTION COUNT: " + count);
        println("MEMORY BLOCKS:");
        for (var b : currentProgram.getMemory().getBlocks()) {
            println(String.format("  %-16s %s - %s  (%d bytes) %s%s%s",
                b.getName(), b.getStart(), b.getEnd(), b.getSize(),
                b.isRead()?"r":"-", b.isWrite()?"w":"-", b.isExecute()?"x":"-"));
        }
        long[] targets = { 0x682af4L };
        for (long t : targets) {
            Address a = base.getNewAddress(t);
            Function f = fm.getFunctionContaining(a);
            println(String.format("TARGET 0x%x -> %s", t,
                f == null ? "(no function)" : f.getName() + " @ " + f.getEntryPoint()));
        }
    }
}
