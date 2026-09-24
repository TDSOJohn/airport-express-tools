// Find store instructions with a given struct offset, optionally whose source register
// was just loaded with a given immediate. Usage: -postScript FindStore.java 0x24 [imm]
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.lang.Register;
import java.util.*;

public class FindStore extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        long off = Long.decode(args[0]);
        Long imm = args.length > 1 ? Long.decode(args[1]) : null;
        FunctionManager fm = currentProgram.getFunctionManager();
        // reg -> last immediate value seen (li / addiu rX,zero,imm / ori rX,zero,imm)
        Map<String, Long> lastImm = new HashMap<>();
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        int hits = 0;
        Function curFn = null;
        while (it.hasNext()) {
            Instruction ins = it.next();
            Function f = fm.getFunctionContaining(ins.getAddress());
            if (f != curFn) { curFn = f; lastImm.clear(); }
            String m = ins.getMnemonicString();
            // track immediates
            if (m.equals("li") || m.equals("_li")) {
                Object[] o = ins.getOpObjects(0);
                Scalar s = firstScalar(ins, 1);
                if (o.length > 0 && o[0] instanceof Register && s != null)
                    lastImm.put(((Register)o[0]).getName(), s.getUnsignedValue());
            } else if ((m.equals("addiu") || m.equals("ori") || m.equals("addu")) && ins.getNumOperands() == 3) {
                Object[] d = ins.getOpObjects(0);
                Object[] a = ins.getOpObjects(1);
                Scalar s = firstScalar(ins, 2);
                if (d.length > 0 && d[0] instanceof Register && a.length > 0 && a[0] instanceof Register
                    && ((Register)a[0]).getName().equals("zero") && s != null)
                    lastImm.put(((Register)d[0]).getName(), s.getUnsignedValue());
                else if (d.length > 0 && d[0] instanceof Register)
                    lastImm.remove(((Register)d[0]).getName());
            }
            if (m.equals("sw") || m.equals("sh") || m.equals("sb")) {
                // operand 1 is  0xOFF(reg)
                Scalar s = null;
                for (Object o : ins.getOpObjects(1)) if (o instanceof Scalar) s = (Scalar)o;
                if (s != null && s.getSignedValue() == off) {
                    Object[] src = ins.getOpObjects(0);
                    String srcName = (src.length > 0 && src[0] instanceof Register) ? ((Register)src[0]).getName() : "?";
                    Long v = lastImm.get(srcName);
                    if (imm == null || (v != null && v.longValue() == imm.longValue())) {
                        hits++;
                        println(String.format("%s  %-30s  %s  src=%s immval=%s",
                            ins.getAddress(), ins.toString(),
                            f == null ? "(none)" : f.getName() + "@" + f.getEntryPoint(),
                            srcName, v == null ? "?" : "0x" + Long.toHexString(v)));
                    }
                }
            }
        }
        println("### FindStore off=0x" + Long.toHexString(off) + " imm=" + imm + " hits=" + hits);
    }
    private Scalar firstScalar(Instruction ins, int opIdx) {
        if (ins.getNumOperands() <= opIdx) return null;
        for (Object o : ins.getOpObjects(opIdx)) if (o instanceof Scalar) return (Scalar)o;
        return null;
    }
}
