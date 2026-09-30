"""Offline tests for the WAN-link warning (mode.py) and the link-local fallback (discover.py).
Run: python3 -m unittest discover -s tests   (from the repository root)"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from airportctl import cli, discover, ui  # noqa: E402
from airportctl import mode as modemod  # noqa: E402

# acpd.system.show excerpts, as read live on 2026-09-28
NAT_WAN_UP = ('\t \t PHY (0x00FE3020) index 0\n'
              '\t \t \t Link State - Current  (link state 100Mbps Full Duplex)\n'
              '\t \t \t Link State - Previous (link state 100Mbps Full Duplex)\n'
              '\t \t \t linked to interface eth0 \n'
              '\t \t PHY (0x00FE3030) index 1\n'
              '\t \t \t Link State - Current  (link state 100Mbps Full Duplex)\n'
              '\t \t \t Link State - Previous (link state 100Mbps Full Duplex)\n'
              '\t \t \t linked to interface eth1 \n')
BRIDGE_WAN_DOWN = ('\t \t PHY (0x00FE3020) index 0\n'
                   '\t \t \t Link State - Current  (link state is Down)\n'
                   '\t \t \t Link State - Previous (link state is Down)\n'
                   '\t \t \t linked to interface eth1 \n'
                   '\t \t PHY (0x00FE3030) index 1\n'
                   '\t \t \t Link State - Current  (link state 100Mbps Full Duplex)\n'
                   '\t \t \t Link State - Previous (link state 100Mbps Full Duplex)\n'
                   '\t \t \t linked to interface eth1 \n')


def gate(choice):
    raNA, raDS, raWB = modemod.SHARING[choice]
    return {'raNA': int(raNA), 'raDS': int(raDS), 'raWB': int(raWB), 'waUB': None,
            'waCV': 0x8300, 'ctim': 1790173155}


class Uplink(unittest.TestCase):
    def test_phy_links(self):
        self.assertEqual(modemod.phy_links(NAT_WAN_UP),
                         {0: '100Mbps Full Duplex', 1: '100Mbps Full Duplex'})
        self.assertEqual(modemod.phy_links(BRIDGE_WAN_DOWN)[0], 'is Down')

    def test_wan_link(self):
        for text, want in ((NAT_WAN_UP, '100Mbps Full Duplex'), (BRIDGE_WAN_DOWN, None)):
            with mock.patch.object(modemod.acp, 'rpc',
                                   return_value={'status': 0, 'outputs': {'output': text}}):
                self.assertEqual(modemod.wan_link('h', 'pw'), want)

    def test_wan_link_unparsable(self):
        with mock.patch.object(modemod.acp, 'rpc', return_value={'outputs': {'output': 'x'}}):
            with self.assertRaises(RuntimeError):
                modemod.wan_link('h', 'pw')

    def test_sharing_of(self):
        for choice in modemod.SHARING:
            self.assertEqual(modemod.sharing_of(gate(choice)), choice)
        self.assertEqual(modemod.sharing_of({'raNA': 1, 'raDS': 0, 'raWB': 1}), 'custom')

    def test_warning_only_without_nat_and_link(self):
        self.assertIsNone(modemod.uplink_warning('nat', None))
        self.assertIsNone(modemod.uplink_warning('bridge', '100Mbps Full Duplex'))
        w = modemod.uplink_warning('bridge', None)
        self.assertIn('bridge', w)
        self.assertIn('mode sharing nat', w)

    def test_uplink_reuses_gate(self):
        with mock.patch.object(modemod.acp, 'rpc',
                               return_value={'outputs': {'output': BRIDGE_WAN_DOWN}}), \
                mock.patch.object(modemod, 'read_gate') as rg:
            up = modemod.uplink('h', 'pw', gate('bridge'))
        rg.assert_not_called()
        self.assertEqual((up['sharing'], up['wan_link']), ('bridge', None))
        self.assertTrue(up['warning'])


class Discover(unittest.TestCase):
    def test_query(self):
        q = discover._query('_airport._tcp.local')
        self.assertEqual(q[:12], b'\0\0\0\0\0\x01\0\0\0\0\0\0')
        self.assertEqual(q[12:], b'\x08_airport\x04_tcp\x05local\0\0\x0c\0\x01')

    def test_default_answers(self):
        with mock.patch.object(discover, 'answers', return_value=True), \
                mock.patch.object(discover, 'find') as find:
            self.assertEqual(discover.resolve_default(), '10.0.1.1')
        find.assert_not_called()

    def test_falls_back_to_link_local(self):
        logged = []
        found = [('fe80::22c9:d0ff:fe99:efd6%eth9', 'eth9'), ('fe80::1%wlan9', 'wlan9')]
        with mock.patch.object(discover, 'answers', return_value=False), \
                mock.patch.object(discover, 'find', return_value=found):
            self.assertEqual(discover.resolve_default(logged.append), found[0][0])
        self.assertIn('eth9', logged[0])
        self.assertIn('fe80::1%wlan9', logged[0])

    def test_nothing_found_keeps_default(self):
        with mock.patch.object(discover, 'answers', return_value=False), \
                mock.patch.object(discover, 'find', return_value=[]):
            self.assertEqual(discover.resolve_default(), '10.0.1.1')

    def test_cli_resolves_only_without_host(self):
        with mock.patch.object(discover, 'resolve_default', return_value='fe80::1%x') as rd, \
                mock.patch.object(cli, 'run') as run:
            cli.main(['-p', 'pw', 'info'])
            self.assertEqual(run.call_args[0][0].host, 'fe80::1%x')
            cli.main(['-p', 'pw', '--host', '10.0.1.9', 'info'])
            self.assertEqual(run.call_args[0][0].host, '10.0.1.9')
            cli.main(['-p', 'pw', 'rpc', '--list'])
        self.assertEqual(rd.call_count, 1)


class UiAction(unittest.TestCase):
    def test_sharing_fix_is_nat_only(self):
        words, pos = ui.ACTIONS['mode.sharing']({'choice': 'bridge'})
        self.assertEqual(words + pos, ['mode', 'sharing', 'nat'])
        self.assertIn('mode.sharing', ui.NEEDS_REBOOT)


if __name__ == '__main__':
    unittest.main()
