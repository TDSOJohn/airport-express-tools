// Print C strings at addresses / ranges. Arg forms: 0xADDR  or  0xSTART-0xEND
// @category ACPd
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryAccessException;

public class DumpStr extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address base = currentProgram.getImageBase();
        for (String a : args) {
            if (a.contains("-")) {
                String[] p = a.split("-");
                long s = Long.decode(p[0]), e = Long.decode(p[1]);
                long cur = s;
                while (cur < e) {
                    Address ad = base.getNewAddress(cur);
                    String str = cstr(ad);
                    println(String.format("0x%x: %s", cur, escape(str)));
                    cur += str.length() + 1;
                    // align to next non-empty
                    while (cur < e && readByte(base.getNewAddress(cur)) == 0) cur++;
                }
            } else {
                Address ad = base.getNewAddress(Long.decode(a));
                println(String.format("0x%x: %s", Long.decode(a), escape(cstr(ad))));
            }
        }
    }
    private byte readByte(Address a) { try { return getByte(a); } catch (MemoryAccessException e) { return 0; } }
    private String cstr(Address a) {
        StringBuilder sb = new StringBuilder();
        try { for (int i=0;i<256;i++){ byte b=getByte(a.add(i)); if(b==0)break; sb.append((char)(b&0xff)); } }
        catch (Exception e) { sb.append("<err>"); }
        return sb.toString();
    }
    private String escape(String s){ return s.replace("\t","\\t").replace("\n","\\n"); }
}
