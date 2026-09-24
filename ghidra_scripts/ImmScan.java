// Linear scan for 32-bit immediates (incl. MIPS lui+ori/addiu pairs) matching target fourccs.
// Reports the instruction address and containing function for each hit.
// Usage: -postScript ImmScan.java 0x7261574d 0x7261536b 0x72614541 0x72615745
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import java.util.*;

public class ImmScan extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Set<Long> targets = new LinkedHashSet<>();
        for (String a : args) targets.add(Long.decode(a) & 0xffffffffL);
        FunctionManager fm = currentProgram.getFunctionManager();
        Map<String,Integer> hi = new HashMap<>();   // reg -> lui immediate (<<16)

        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        int hits = 0;
        while (it.hasNext()) {
            Instruction ins = it.next();
            String m = ins.getMnemonicString();
            // (1) folded immediate: any scalar operand equal to a target
            for (int op = 0; op < ins.getNumOperands(); op++) {
                Scalar s = ins.getScalar(op);
                if (s != null && targets.contains(s.getUnsignedValue() & 0xffffffffL)) {
                    report(ins, s.getUnsignedValue() & 0xffffffffL, fm); hits++;
                }
            }
            // (2) lui/ori|addiu reconstruction
            if (m.equalsIgnoreCase("lui")) {
                Register rt = ins.getRegister(0);
                Scalar imm = ins.getScalar(1);
                if (rt != null && imm != null)
                    hi.put(rt.getName(), (int)(imm.getUnsignedValue() << 16));
            } else if (m.equalsIgnoreCase("ori") || m.equalsIgnoreCase("addiu")) {
                Register rd = ins.getRegister(0);
                Register rs = ins.getRegister(1);
                Scalar imm = ins.getScalar(2);
                if (rd != null && rs != null && imm != null && hi.containsKey(rs.getName())) {
                    long lo = m.equalsIgnoreCase("ori")
                        ? (imm.getUnsignedValue() & 0xffff)
                        : (imm.getValue() & 0xffffffffL); // addiu sign-extends
                    long val = ((long)hi.get(rs.getName()) + lo) & 0xffffffffL;
                    if (targets.contains(val)) { report(ins, val, fm); hits++; }
                    hi.put(rd.getName(), (int)val); // chain
                }
            }
        }
        println("TOTAL HITS: " + hits);
    }
    private void report(Instruction ins, long val, FunctionManager fm) {
        Function f = fm.getFunctionContaining(ins.getAddress());
        char[] c = { (char)((val>>24)&0xff),(char)((val>>16)&0xff),(char)((val>>8)&0xff),(char)(val&0xff) };
        println(String.format("HIT 0x%08x '%s' @ %s  func=%s  [%s]",
            val, new String(c), ins.getAddress(),
            f == null ? "(none)" : f.getName() + "@" + f.getEntryPoint(), ins));
    }
}
