// Enumerate every ACP RPC registration: walk all call sites of the registrar and resolve the
// arguments (name, flags, handler, then the (key, type, required, ?) parameter-schema tuples).
// MIPS o32: args in a0-a3 then 16(sp), 20(sp), ...; the branch delay slot often sets the last one.
// Usage: -postScript RpcMap.java <registrar 0xADDR> [outfile]
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class RpcMap extends GhidraScript {
    static final long CFSTR_ISA = 0x56070000L;
    Memory mem;
    FunctionManager fm;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        long target = Long.decode(args[0]);
        PrintWriter pw = args.length > 1 ? new PrintWriter(new FileWriter(args[1])) : null;
        mem = currentProgram.getMemory();
        fm = currentProgram.getFunctionManager();
        Address base = currentProgram.getImageBase();
        Address reg = base.getNewAddress(target);

        // collect calling functions
        Set<Function> callers = new LinkedHashSet<>();
        for (Reference r : currentProgram.getReferenceManager().getReferencesTo(reg)) {
            Function f = fm.getFunctionContaining(r.getFromAddress());
            if (f != null) callers.add(f);
        }
        out(pw, "### registrar " + reg + "  callers=" + callers.size());

        int total = 0;
        for (Function f : callers) {
            List<String> rows = new ArrayList<>();
            Map<String, Long> regs = new HashMap<>();
            Map<Long, Long> stack = new HashMap<>();
            Map<String, Long> hi = new HashMap<>();
            InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
            Instruction pendingCall = null;
            while (it.hasNext()) {
                Instruction ins = it.next();
                if (pendingCall != null) {            // this is the delay slot: apply it first
                    track(ins, regs, stack, hi);
                    rows.add(render(regs, stack));
                    pendingCall = null;
                    clobber(regs, hi);
                    continue;
                }
                String m = ins.getMnemonicString();
                if (m.startsWith("_")) m = m.substring(1);
                if ((m.equals("jal") || m.equals("jalr")) && callsTarget(ins, reg)) {
                    pendingCall = ins;
                    continue;
                }
                track(ins, regs, stack, hi);
                if (m.startsWith("jal")) clobber(regs, hi);   // only caller-saved regs die
            }
            if (!rows.isEmpty()) {
                out(pw, "");
                out(pw, "## " + f.getName() + " @" + f.getEntryPoint() + "  (" + rows.size() + ")");
                for (String r : rows) { out(pw, "  " + r); total++; }
            }
        }
        out(pw, "");
        out(pw, "### total registrations: " + total);
        if (pw != null) pw.close();
    }

    static final String[] CALLER_SAVED = {"at", "v0", "v1", "a0", "a1", "a2", "a3",
        "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "ra"};

    static final Set<String> STORES = new HashSet<>(Arrays.asList("sb", "sh", "swl", "swr"));

    /** a call destroys v0-v1/a0-a3/t0-t9 but NOT s0-s8/gp - the schema constants live in those. */
    private void clobber(Map<String, Long> regs, Map<String, Long> hi) {
        for (String r : CALLER_SAVED) { regs.remove(r); hi.remove(r); }
    }

    private boolean callsTarget(Instruction ins, Address target) {
        for (Reference r : ins.getReferencesFrom())
            if (r.getToAddress().equals(target)) return true;
        return false;
    }

    /** crude o32 argument tracking: constants, lui/ori|addiu pairs, moves, and sw to sp+off */
    private Map<Long, Long> stackRead;

    private void track(Instruction ins, Map<String, Long> regs, Map<Long, Long> stack,
                       Map<String, Long> hi) {
        stackRead = stack;
        String m = ins.getMnemonicString();
        if (m.startsWith("_")) m = m.substring(1);   // delay-slot form, e.g. _sw
        String d = regName(ins, 0);
        if (m.equals("clear") && d != null) { regs.put(d, 0L); hi.remove(d); return; }
        // Ghidra already resolved gp-relative / lui+lo pairs into data references; trust those.
        if (d != null && !d.equals("zero")) {
            Address ref = dataRef(ins);
            if (ref != null) {
                if (m.equals("lw")) {                      // load the pointer stored there
                    Long w = word(ref);
                    if (w != null) { regs.put(d, w); hi.remove(d); return; }
                } else if (m.equals("addiu") || m.equals("ori") || m.equals("la")) {
                    regs.put(d, ref.getOffset()); hi.remove(d); return;
                }
            }
        }
        if (m.equals("lui") && d != null) {
            Scalar s = scalar(ins, 1);
            if (s != null) { hi.put(d, s.getUnsignedValue() << 16); regs.remove(d); }
            return;
        }
        if ((m.equals("ori") || m.equals("addiu") || m.equals("addu")) && ins.getNumOperands() == 3) {
            String a = regName(ins, 1);
            Scalar s = scalar(ins, 2);
            if (d == null) return;
            String b2 = regName(ins, 2);
            if (s == null && b2 != null) {                  // addu d, s1, s2  (incl. `move`)
                long x = "zero".equals(a) ? 0 : (regs.containsKey(a) ? regs.get(a) : Long.MIN_VALUE);
                long y = "zero".equals(b2) ? 0 : (regs.containsKey(b2) ? regs.get(b2) : Long.MIN_VALUE);
                if (x != Long.MIN_VALUE && y != Long.MIN_VALUE) regs.put(d, x + y);
                else { regs.remove(d); hi.remove(d); }
                return;
            }
            if (a != null && hi.containsKey(a) && s != null) {
                long v = hi.get(a);
                v = m.equals("ori") ? (v | s.getUnsignedValue()) : (v + s.getSignedValue());
                regs.put(d, v); hi.put(d, hi.get(a));
            } else if (a != null && a.equals("zero") && s != null) {
                regs.put(d, s.getSignedValue()); hi.remove(d);
            } else if (a != null && regs.containsKey(a) && s != null && !m.equals("ori")) {
                regs.put(d, regs.get(a) + s.getSignedValue());
            } else { regs.remove(d); hi.remove(d); }
            return;
        }
        if (m.equals("lw") && d != null) {
            Scalar off = null; String b = null;
            for (Object o : ins.getOpObjects(1)) {
                if (o instanceof Scalar) off = (Scalar) o;
                if (o instanceof Register) b = ((Register) o).getName();
            }
            if (b != null && regs.containsKey(b)) {
                Address a = addr(regs.get(b) + (off == null ? 0 : off.getSignedValue()));
                Long w = a == null ? null : word(a);
                if (w != null) { regs.put(d, w); hi.remove(d); return; }
            }
            if ("sp".equals(b) && off != null && stackRead != null
                && stackRead.containsKey(off.getUnsignedValue())) {
                regs.put(d, stackRead.get(off.getUnsignedValue())); hi.remove(d); return;
            }
            regs.remove(d); hi.remove(d);
            return;
        }
        if ((m.equals("li") || m.equals("_li")) && d != null) {
            Scalar s = scalar(ins, 1);
            if (s != null) regs.put(d, s.getSignedValue()); else regs.remove(d);
            hi.remove(d);
            return;
        }
        if (m.equals("move") && d != null) {
            String a = regName(ins, 1);
            if ("zero".equals(a)) regs.put(d, 0L);
            else if (a != null && regs.containsKey(a)) regs.put(d, regs.get(a));
            else regs.remove(d);
            return;
        }
        if (m.equals("sw")) {
            String src = regName(ins, 0);
            Scalar off = null; String b = null;
            for (Object o : ins.getOpObjects(1)) {
                if (o instanceof Scalar) off = (Scalar) o;
                if (o instanceof Register) b = ((Register) o).getName();
            }
            if ("sp".equals(b) && off != null) {
                Long v = ("zero".equals(src)) ? Long.valueOf(0) : regs.get(src);
                if (v != null) stack.put(off.getUnsignedValue(), v);
                else stack.remove(off.getUnsignedValue());
            }
            return;
        }
        if (STORES.contains(m)) return;   // operand 0 of a store is read, not written
        if (d != null && !m.startsWith("b") && !m.startsWith("j") && !m.equals("nop")) {
            boolean allZero = ins.getNumOperands() > 1;
            for (int i = 1; i < ins.getNumOperands(); i++) {
                String r = regName(ins, i);
                if (r == null || !r.equals("zero")) { allZero = false; break; }
            }
            if (allZero) { regs.put(d, 0L); hi.remove(d); return; }
            regs.remove(d); hi.remove(d);   // unknown definition
        }
    }

    private String render(Map<String, Long> regs, Map<Long, Long> stack) {
        List<Long> raw = new ArrayList<>();
        List<Boolean> known = new ArrayList<>();
        for (String r : new String[]{"a0", "a1", "a2", "a3"}) {
            known.add(regs.containsKey(r));
            raw.add(regs.containsKey(r) ? regs.get(r) : 0L);
        }
        for (long off = 16; off <= 92; off += 4) {
            if (!stack.containsKey(off)) break;
            known.add(true); raw.add(stack.get(off));
        }
        String name = known.get(0) ? val(raw.get(0)) : "?";
        String flags = known.get(1) ? "0x" + Long.toHexString(raw.get(1)) : "?";
        String handler = known.get(2) ? val(raw.get(2)) : "?";
        StringBuilder params = new StringBuilder();
        int i = 3;
        while (i + 2 < raw.size()) {
            if (!known.get(i)) { params.append(" <unresolved>"); break; }
            long key = raw.get(i);
            if (key == 0) break;                       // NULL name terminates the list
            String k = cfString(key);
            if (k == null) break;                      // not a CFString -> stale slot, stop
            long type = raw.get(i + 1);
            long input = raw.get(i + 2);
            long dflt = 0;
            if (input == 0) {
                i += 3;
            } else {
                dflt = (i + 3 < raw.size()) ? raw.get(i + 3) : 0;
                i += 4;
                if (dflt != 0 && dflt != 0x10) i += 1;   // a default value word follows
            }
            params.append("  ").append(k).append(':').append(type)
                  .append(input != 0 ? "" : "(out)")
                  .append(dflt != 0 ? "=d" + dflt : "");
        }
        return String.format("%-40s flags=%-6s %-22s %s", name, flags, handler, params.toString().trim());
    }

    /** render a value: CFString / C string / function / pointer-to-those / number */
    private String val(long v) { return val(v, true); }

    private String val(long v, boolean follow) {
        if (v == 0) return "0";
        if (v > -0x10000 && v < 0x10000) return (v < 10 && v > -10) ? Long.toString(v) : "0x" + Long.toHexString(v);
        Address a = addr(v);
        if (a == null) return "0x" + Long.toHexString(v);
        Function f = fm.getFunctionAt(a);
        if (f != null) return f.getName() + "()";
        Long isa = word(a);
        if (isa != null && isa == CFSTR_ISA) {
            String s = cstr(a.add(8));
            if (s != null) return "@\"" + s + "\"";
        }
        String s = cstr(a);
        if (s != null && s.length() >= 2) return "\"" + s + "\"";
        if (follow) {
            Long p = word(a);
            if (p != null && p != 0) {
                String inner = val(p, false);
                if (!inner.startsWith("0x")) return "&" + inner;
            }
        }
        return "0x" + Long.toHexString(v);
    }

    private Address dataRef(Instruction ins) {
        for (Reference r : ins.getReferencesFrom())
            if (r.getReferenceType().isData() && !r.getReferenceType().isCall()) return r.getToAddress();
        return null;
    }

    /** the text of an inline CoreFoundation constant string, or null if v is not one */
    private String cfString(long v) {
        for (int hop = 0; hop < 2; hop++) {
            Address a = addr(v);
            if (a == null) return null;
            Long isa = word(a);
            if (isa == null) return null;
            if (isa == CFSTR_ISA) return cstr(a.add(8));
            v = isa;                                   // follow one pointer and retry
        }
        return null;
    }

    private Address addr(long v) {
        try {
            Address a = currentProgram.getImageBase().getNewAddress(v);
            return mem.contains(a) ? a : null;
        } catch (Exception e) { return null; }
    }

    private Long word(Address a) {
        try { return Integer.toUnsignedLong(mem.getInt(a)); } catch (Exception e) { return null; }
    }

    private String cstr(Address a) {
        StringBuilder sb = new StringBuilder();
        try {
            for (int i = 0; i < 96; i++) {
                byte b = mem.getByte(a.add(i));
                if (b == 0) return sb.length() > 0 ? sb.toString() : null;
                if (b < 0x20 || b > 0x7e) return null;
                sb.append((char) b);
            }
        } catch (Exception e) { return null; }
        return null;
    }

    private String regName(Instruction ins, int op) {
        if (ins.getNumOperands() <= op) return null;
        for (Object o : ins.getOpObjects(op)) if (o instanceof Register) return ((Register) o).getName();
        return null;
    }

    private Scalar scalar(Instruction ins, int op) {
        if (ins.getNumOperands() <= op) return null;
        for (Object o : ins.getOpObjects(op)) if (o instanceof Scalar) return (Scalar) o;
        return null;
    }

    private void out(PrintWriter pw, String s) { if (pw != null) pw.println(s); else println(s); }
}
