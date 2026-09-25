"""Offline tests for airportctl/join.py: join.conf generation and `join status` parsing.
Run: python3 -m unittest discover -s tests   (from the repository root)"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from airportctl import join  # noqa: E402

LEASE = ('DHCP_IP=192.168.1.23\nDHCP_MASK=255.255.255.0\nDHCP_ROUTER=192.168.1.1\n'
         'DHCP_DNS="192.168.1.1 9.9.9.9"\nDHCP_SERVER=192.168.1.1\n'
         'DHCP_SERVER_MAC=aa:bb:cc:dd:ee:ff\nDHCP_LEASE=86400\nDHCP_T1=43200\nDHCP_T2=75600\n')


def device_output(conf, lease='', log=''):
    """What status()'s one SSH command prints on the Express."""
    return ('has autorun.sh\nhas autorun/wpa_supplicant\nhas autorun/dhcpc\nhas autorun/wpa.conf\n'
            f'--conf\n{conf}--ssid\nHomeWiFi\n--hook\nyes\n--lease\n{lease}--log\n{log}')


def status(out, pids=('233',)):
    with mock.patch.object(join, '_sh', return_value=out), \
            mock.patch.object(join, 'running', return_value=list(pids)):
        return join.status('10.0.1.1', 'pw')


class JoinConf(unittest.TestCase):
    def test_dhcp_default(self):
        self.assertEqual(join.join_conf(), 'IP=dhcp\n')

    def test_dhcp_with_fallback(self):
        self.assertEqual(join.join_conf('dhcp', '192.168.1.1', '255.255.255.0', '192.168.1.250'),
                         'IP=dhcp\nFALLBACK_IP=192.168.1.250\nGW=192.168.1.1\nMASK=255.255.255.0\n')

    def test_fixed(self):
        self.assertEqual(join.join_conf('192.168.1.250', '192.168.1.1'),
                         'IP=192.168.1.250\nGW=192.168.1.1\nMASK=255.255.255.0\n')

    def test_rejects(self):
        for args in [('dhcp', '192.168.1.1'),                       # gateway without fixed ip
                     ('dhcp', None, '255.255.255.0', '192.168.1.250'),  # fallback w/o gateway
                     ('192.168.1.250', None),                       # fixed w/o gateway
                     ('192.168.1.250', '192.168.1.1', '255.255.255.0', '192.168.1.251'),
                     ('dhcp', '10.0.0.1', '255.255.255.0', '192.168.1.5')]:  # other subnet
            with self.subTest(args=args), self.assertRaises(ValueError):
                join.join_conf(*args)


class Status(unittest.TestCase):
    def test_dhcp_joined(self):
        st = status(device_output('IP=dhcp\n', LEASE,
                                  'autorun start\nlease 192.168.1.23/255.255.255.0 from 192.168.1.1\n'
                                  'joined, 192.168.1.23 via wlan2, AirPlay moved\n'))
        self.assertEqual(st['state'], 'joined')
        self.assertTrue(st['dhcp'])
        self.assertEqual((st['ip'], st['gateway'], st['netmask'], st['lease_s']),
                         ('192.168.1.23', '192.168.1.1', '255.255.255.0', '86400'))
        self.assertIn('autorun/dhcpc', st['installed'])
        self.assertIsNone(st['fallback_ip'])
        self.assertIn('address 192.168.1.23/255.255.255.0  gateway 192.168.1.1  (DHCP, lease '
                      '86400 s)', join.describe(st))

    def test_dhcp_no_lease_yet(self):
        st = status(device_output('IP=dhcp\n', '', 'autorun start\n'))
        self.assertEqual(st['state'], 'joining')
        self.assertIsNone(st['ip'])
        self.assertIn('address: DHCP (no lease yet this boot)', join.describe(st))

    def test_dhcp_failed(self):
        st = status(device_output('IP=dhcp\n', '', 'autorun start\nno DHCP lease on wlan2, gave '
                                  'up (5 GHz AP and Ethernet still up)\n'), pids=())
        self.assertEqual(st['state'], 'failed')

    def test_fallback_shown_only_when_used(self):
        conf = 'IP=dhcp\nFALLBACK_IP=192.168.1.250\nGW=192.168.1.1\nMASK=255.255.255.0\n'
        st = status(device_output(conf, '', 'autorun start\n'))
        self.assertIsNone(st['ip'])
        st = status(device_output(conf, '', 'autorun start\nno DHCP lease, using the fallback '
                                  'address 192.168.1.250\njoined, 192.168.1.250 via wlan2\n'))
        self.assertEqual((st['state'], st['ip'], st['gateway'], st['lease_s']),
                         ('joined', '192.168.1.250', '192.168.1.1', None))
        self.assertEqual((st['fallback_ip'], st['fixed_gateway']), ('192.168.1.250', '192.168.1.1'))

    def test_fixed_unchanged(self):
        st = status(device_output('IP=192.168.1.250\nGW=192.168.1.1\nMASK=255.255.255.0\n', '',
                                  'joined, 192.168.1.250 via wlan2\n'))
        self.assertEqual((st['state'], st['dhcp'], st['ip'], st['gateway']),
                         ('joined', False, '192.168.1.250', '192.168.1.1'))
        self.assertNotIn('DHCP', join.describe(st))


class UiAddress(unittest.TestCase):
    """The join card's Address selector -> `join install` flags."""
    def test_modes(self):
        from airportctl import ui
        f = ui._join_address
        self.assertEqual(f({'mode': 'dhcp', 'ip': '', 'gateway': ''}), [])
        self.assertEqual(f({'mode': 'dhcp', 'ip': ' 192.168.1.250 ', 'gateway': '192.168.1.254'}),
                         ['--fallback-ip=192.168.1.250', '--gateway=192.168.1.254'])
        self.assertEqual(f({'mode': 'fixed', 'ip': '192.168.1.250', 'gateway': '192.168.1.254'}),
                         ['--ip=192.168.1.250', '--gateway=192.168.1.254'])
        self.assertEqual(f({}), [])     # older pages: no mode, no address = DHCP


class Install(unittest.TestCase):
    def test_dry_run_dhcp(self):
        logged = []
        join.install('10.0.1.1', 'pw', 'HomeWiFi', 'correct horse', dry_run=True,
                     log=logged.append)
        self.assertIn('with an address from DHCP', logged[0])
        self.assertIn('dhcpc (', logged[1])


if __name__ == '__main__':
    unittest.main()
