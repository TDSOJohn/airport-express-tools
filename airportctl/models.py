"""Every AirPort base station airportctl knows about, keyed by product ID (`syAP`).

`syAP`, codename and Apple's model name come from the product table inside ACPd itself: 32-byte
rows of id | ... | category | codename | name, found 2026-10-19 in the 7.8.1 image of product 108
(big-endian) and the 7.9.1 image of product 120 (little-endian, which adds 119/120). Every ID
seen live matches it: 106 on an A1254, 108 on an A1301, 115 (codename K31, also the CFE board
name) on an A1392.
Rows for things that never shipped as base stations (Xserve RAID, S5, J89, K54-K56) are left out.

A-numbers come from public sources; Apple's table has none. `arch` (hw.machine_arch), `wifi` (the
first word of the `card` property, lowercased) and `boot` (the `syBL` bootloader) are filled in
only once checked, live or in the model's firmware image; None means not checked yet.
`tested` lists the firmware versions (`syVs`) everything in the README was verified on.

`python3 -m airportctl.models` prints the README compatibility table; `--update README.md`
rewrites it in place.
"""
import collections
import sys

Model = collections.namedtuple('Model', 'syap codename name a_number arch wifi boot tested status')


def _m(syap, codename, name, a_number, arch=None, wifi=None, boot=None, tested=(), status=''):
    return Model(syap, codename, name, a_number, arch, wifi, boot, frozenset(tested), status)


MODELS = {m.syap: m for m in [
    _m(1, 'P19', 'AirPort (Snow)', None),
    _m(3, 'P81', 'AirPort Extreme (802.11g)', 'A1034'),
    # Apple's name is just "AirPort Express"; the radio generation is added to tell it from 107/115
    _m(102, 'Q61', 'AirPort Express (802.11g)', 'A1084/A1088'),
    _m(104, 'M28', 'AirPort Extreme (802.11n)', 'A1143'),
    _m(105, 'M91', 'AirPort Extreme (802.11n, Gigabit Ethernet)', 'A1143'),
    # live 2026-10-04/05: chip, card, syBL, and sysctl over SSH
    _m(106, 'M52', 'Time Capsule', 'A1254', arch='armeb', wifi='marvell', boot='microboot',
       status='ACP reads and the debug SSH login seen live; writes untested'),
    _m(107, 'M48', 'AirPort Express (802.11n)', 'A1264'),
    # live 2026-10-19 on 7.6.9: chip (88F5281 Orion, as on the A1254), card, syBL; arch from the
    # 7.8.1 image (NetBSD evbarm big-endian)
    _m(108, 'K10', 'AirPort Extreme (Simultaneous Dual-Band)', 'A1301', arch='armeb',
       wifi='atheros', boot='microboot', status='ACP reads seen live (7.6.9); writes untested'),
    _m(109, 'K30', 'Time Capsule (Simultaneous Dual-Band)', 'A1302'),
    _m(113, 'K30A', 'Time Capsule (Simultaneous Dual-Band, Gen2)', 'A1355'),
    _m(114, 'K10A', 'AirPort Extreme (Simultaneous Dual-Band, Gen2)', 'A1354'),
    # live 2026-09-24: card, syBL, and sysctl over SSH
    _m(115, 'K31', 'AirPort Express (Simultaneous Dual-Band)', 'A1392', arch='mipseb',
       wifi='atheros', boot='cfe', tested={'7.8.1'}, status='everything in this README'),
    _m(116, 'K30B', 'Time Capsule (Simultaneous Dual-Band, Gen3)', 'A1409'),
    _m(117, 'K10B', 'AirPort Extreme (Simultaneous Dual-Band, Gen3)', 'A1408'),
    # Apple's 7.9.1 table names these two by codename only; NetBSD 6.0, little-endian ARM
    _m(119, 'J28', 'AirPort Time Capsule (802.11ac)', 'A1470'),
    _m(120, 'J28E', 'AirPort Extreme (802.11ac)', 'A1521'),
]}


def get(syap):
    """The Model for a product ID, or None."""
    return MODELS.get(syap)


def label(syap):
    """'AirPort Express (Simultaneous Dual-Band), A1392' for display."""
    m = MODELS.get(syap)
    if m is None:
        return 'unknown product' + (f' {syap}' if syap is not None else '')
    return m.name + (f', {m.a_number}' if m.a_number else '')


def is_tested(syap, firmware):
    m = MODELS.get(syap)
    return m is not None and firmware in m.tested


def tested_list():
    """'syAP=115 (A1392) on 7.8.1' for every verified combination, for messages."""
    return ', '.join(f'syAP={m.syap} ({m.a_number}) on {"/".join(sorted(m.tested))}'
                     for m in MODELS.values() if m.tested)


def wifi_family(card):
    """'atheros' from the `card` property ('Atheros 802.11; driver 4.0.27.6; ...'), or None."""
    words = (card or '').split()
    return words[0].lower() if words else None


TABLE_BEGIN = '<!-- models:begin (generated: python3 -m airportctl.models --update README.md) -->'
TABLE_END = '<!-- models:end -->'


def compat_table():
    rows = ['| Model | A-number | `syAP` | Codename | CPU | Wi-Fi | Status |',
            '|---|---|---|---|---|---|---|']
    for m in MODELS.values():
        if m.tested:
            status = f'**Tested** on {", ".join(sorted(m.tested))}: {m.status}'
        else:
            status = m.status or 'untested'
        rows.append(f'| {m.name} | {m.a_number or ""} | {m.syap} | {m.codename} | '
                    f'{m.arch or ""} | {(m.wifi or "").capitalize()} | {status} |')
    return '\n'.join(rows)


def update_readme(path):
    """Replace the table between TABLE_BEGIN and TABLE_END; return True if the file changed."""
    with open(path) as f:
        text = f.read()
    head, sep, rest = text.partition(TABLE_BEGIN)
    if not sep or TABLE_END not in rest:
        raise SystemExit(f'{path}: no {TABLE_BEGIN!r} ... {TABLE_END!r} markers')
    new = head + TABLE_BEGIN + '\n' + compat_table() + '\n' + TABLE_END + rest.split(TABLE_END, 1)[1]
    if new != text:
        with open(path, 'w') as f:
            f.write(new)
    return new != text


if __name__ == '__main__':
    if sys.argv[1:2] == ['--update'] and len(sys.argv) == 3:
        print('updated' if update_readme(sys.argv[2]) else 'already up to date')
    else:
        print(compat_table())
