// Print instructions in a range with mnemonic, operand count and resolved operand objects.
// Usage: -postScript DumpIns.java 0xSTART 0xEND
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
public class DumpIns extends GhidraScript {
    @Override public void run() throws Exception {
        String[] a = getScriptArgs();
        Address base = currentProgram.getImageBase();
        Address s = base.getNewAddress(Long.decode(a[0])), e = base.getNewAddress(Long.decode(a[1]));
        InstructionIterator it = currentProgram.getListing().getInstructions(s, true);
        while (it.hasNext()) {
            Instruction i = it.next();
            if (i.getAddress().compareTo(e) > 0) break;
            StringBuilder sb = new StringBuilder();
            sb.append(i.getAddress()).append("  ").append(i.getMnemonicString())
              .append("  n=").append(i.getNumOperands()).append("  [");
            for (int k = 0; k < i.getNumOperands(); k++) {
                sb.append(k).append(":");
                for (Object o : i.getOpObjects(k)) sb.append(o.getClass().getSimpleName()).append("(").append(o).append(")");
                sb.append(" ");
            }
            sb.append("]  txt=").append(i.toString());
            println(sb.toString());
        }
    }
}
