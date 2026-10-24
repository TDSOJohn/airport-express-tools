"""Offline tests for the model registry (models.py), the untested-device write gate (cli.py)
and the hardware checks before `join install` (join.py).
Run: python3 -m unittest discover -s tests   (from the repository root)"""
import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
from airportctl import acp, cli, join, models  # noqa: E402

A1392 = {'syNm': 'Kitchen', 'syAP': 115, 'syVs': '7.8.1', 'syUT': 60,
         'card': 'Atheros 802.11; driver 4.0.27.6; mac 768.3; phy 2457.9'}
A1254 = {'syNm': 'TC', 'syAP': 106, 'syVs': '7.8.1',
         'card': 'Marvell 802.11; driver 0.8.7.0, hw 5, fw 3.7.2.2'}
A1301 = {'syNm': 'Extreme', 'syAP': 108, 'syVs': '7.8.1', 'card': 'Atheros 802.11; driver x'}
A1408 = {'syNm': 'Extreme', 'syAP': 117, 'syVs': '7.8.1', 'card': 'Atheros 802.11; driver x'}


class Registry(unittest.TestCase):
    def test_live_anchors(self):
        self.assertEqual((models.get(115).codename, models.get(115).a_number), ('K31', 'A1392'))
        self.assertEqual((models.get(106).codename, models.get(106).a_number), ('M52', 'A1254'))
        self.assertEqual(models.get(108).a_number, 'A1301')
        self.assertEqual(models.get(117).a_number, 'A1408')

    def test_labels(self):
        self.assertEqual(models.label(115), 'AirPort Express (Simultaneous Dual-Band), A1392')
        self.assertEqual(models.label(999), 'unknown product 999')
        self.assertEqual(models.label(None), 'unknown product')

    def test_tested(self):
        self.assertTrue(models.is_tested(115, '7.8.1'))
        self.assertFalse(models.is_tested(115, '7.6.2'))
        self.assertFalse(models.is_tested(108, '7.8.1'))
        self.assertFalse(models.is_tested(None, None))
        self.assertEqual(models.tested_list(), 'syAP=115 (A1392) on 7.8.1')

    def test_wifi_family(self):
        self.assertEqual(models.wifi_family(A1392['card']), 'atheros')
        self.assertEqual(models.wifi_family(A1254['card']), 'marvell')
        self.assertIsNone(models.wifi_family(None))

    def test_readme_table_in_sync(self):
        with open(os.path.join(ROOT, 'README.md')) as f:
            text = f.read()
        self.assertIn(models.TABLE_BEGIN + '\n' + models.compat_table() + '\n' + models.TABLE_END,
                      text, 'README is stale: python3 -m airportctl.models --update README.md')


def run_cli(argv, dev, untested=False):
    """Parse and run argv against a fake device: (exit message or None, stderr, ran)."""
    args = cli.build_parser().parse_args(argv)
    args.host, args.password = '10.0.1.1', 'pw'
    err = io.StringIO()
    with mock.patch.object(acp, 'read_device', side_effect=[dev] if isinstance(dev, dict)
                           else dev), \
            mock.patch.object(args, 'func') as func, redirect_stderr(err), \
            redirect_stdout(io.StringIO()):
        try:
            cli.run(args)
        except SystemExit as e:
            return str(e), err.getvalue(), func.called
    return None, err.getvalue(), func.called


class WriteGate(unittest.TestCase):
    def test_tested_device_writes(self):
        refused, _, ran = run_cli(['led', 'amber'], A1392)
        self.assertIsNone(refused)
        self.assertTrue(ran)

    def test_untested_device_refused(self):
        refused, _, ran = run_cli(['led', 'amber'], A1301)
        self.assertIn('refusing to write: untested device: syAP=108', refused)
        self.assertIn('--untested', refused)
        self.assertFalse(ran)

    def test_untested_flag_warns_and_writes(self):
        refused, err, ran = run_cli(['led', 'amber', '--untested'], A1301)
        self.assertIsNone(refused)
        self.assertIn('!! untested device', err)
        self.assertTrue(ran)

    def test_untested_firmware_refused(self):
        refused, _, _ = run_cli(['name', 'x'], dict(A1392, syVs='7.6.2'))
        self.assertIn('firmware 7.6.2', refused)

    def test_unidentified_device_fails_closed(self):
        refused, _, ran = run_cli(['wifi', 'hidden', 'on'], RuntimeError('timed out'))
        self.assertIn('could not identify the base station (timed out)', refused)
        self.assertFalse(ran)
        refused, _, ran = run_cli(['wifi', 'hidden', 'on', '--untested'], RuntimeError('x'))
        self.assertIsNone(refused)
        self.assertTrue(ran)

    def test_reads_and_dry_runs_not_gated(self):
        for argv in (['led'], ['led', 'show'], ['mode', 'wan', 'show'], ['info'],
                     ['wifi', 'show'], ['name', 'x', '--dry-run']):
            refused, _, ran = run_cli(argv, RuntimeError('must not be called'))
            self.assertIsNone(refused, argv)
            self.assertTrue(ran, argv)

    def test_every_write_command_has_untested(self):
        p = cli.build_parser()
        for argv in (['wifi', 'ssid', 'x'], ['wifi', 'secure', 'open'], ['wifi', 'hidden', 'on'],
                     ['wifi', 'join', 'x', '--wifi-password', 'y'], ['wifi', 'restore', 'f'],
                     ['join', 'install', 'x', '--wifi-password', 'y'], ['led', 'green'],
                     ['name', 'x'], ['mode', 'ctim'], ['mode', 'sharing', 'nat'],
                     ['mode', 'wan', 'wired'], ['admin-password', 'x']):
            self.assertTrue(p.parse_args(argv + ['--untested']).untested, argv)


class RpcGate(unittest.TestCase):
    def call(self, argv, dev):
        args = cli.build_parser().parse_args(['rpc'] + argv)
        args.host, args.password = '10.0.1.1', 'pw'
        with mock.patch.object(acp, 'read_device', return_value=dev), \
                mock.patch.object(acp, 'rpc', return_value={'status': 0}) as rpc, \
                redirect_stdout(io.StringIO()):
            try:
                cli.cmd_rpc(args)
            except SystemExit as e:
                return str(e), rpc.called
        return None, rpc.called

    def test_read_only_on_tested(self):
        self.assertEqual(self.call(['acpd.system.show'], A1392), (None, True))

    def test_read_only_on_untested_needs_force(self):
        refused, sent = self.call(['acpd.system.show'], A1301)
        self.assertIn('verified read-only on syAP=115 (A1392) on 7.8.1 only', refused)
        self.assertFalse(sent)
        self.assertEqual(self.call(['acpd.system.show', '--force'], A1301), (None, True))

    def test_dry_run_sends_nothing(self):
        self.assertEqual(self.call(['acpd.system.show', '--dry-run'], A1301), (None, False))


class JoinHardware(unittest.TestCase):
    def test_payload_arch(self):
        self.assertEqual(join.payload_arch(), 'mipseb')

    def test_support(self):
        self.assertEqual(join.support(A1392), (True, 'Atheros Wi-Fi, mipseb CPU'))
        ok, why = join.support(A1254)
        self.assertFalse(ok)
        self.assertIn("'Marvell 802.11", why)
        ok, why = join.support(A1301)
        self.assertFalse(ok)
        self.assertIn('needs a build for armeb first', why)
        self.assertIsNone(join.support(A1408)[0])

    def test_support_without_card_uses_registry(self):
        self.assertTrue(join.support({'syAP': 115})[0])
        self.assertFalse(join.support({'syAP': 117})[0])     # Wi-Fi not checked yet
        self.assertFalse(join.support({})[0])

    def check(self, dev, arch):
        with mock.patch.object(join.acp, 'read_device', return_value=dev), \
                mock.patch.object(join, '_sh', return_value=arch + '\n') as sh:
            join.check_device('10.0.1.1', 'pw')
        return sh

    def test_check_device(self):
        sh = self.check(A1392, 'mipseb')
        self.assertIn('hw.machine_arch', sh.call_args[0][2])
        with self.assertRaisesRegex(RuntimeError, "CPU is 'armeb'"):
            self.check(A1408, 'armeb')                  # not in the registry: SSH decides
        with self.assertRaisesRegex(RuntimeError, 'Atheros radio'):
            self.check(A1254, 'armeb')

    def test_install_checks_before_writing(self):
        with mock.patch.object(join, 'check_device', side_effect=RuntimeError('no')), \
                mock.patch.object(join, 'ssh') as ssh:
            with self.assertRaises(RuntimeError):
                join.install('10.0.1.1', 'pw', 'HomeWiFi', 'correct horse', log=lambda m: None)
        ssh.assert_not_called()


class Bands(unittest.TestCase):
    def test_band(self):
        from airportctl import wifi
        self.assertEqual(wifi.band(0, {'raCh': 36}), '5')       # A1301 radio 0
        self.assertEqual(wifi.band(1, {'raCh': 11}), '2.4')
        self.assertEqual(wifi.band(0, {'raCh': 0}), '2.4')      # no channel: A1392 order
        self.assertEqual(wifi.band(1, {}), '5')

    def test_wifi_join_picks_radio_by_channel(self):
        blob = {'radios': [{'raCh': 36, 'raNm': 'x', 'raSt': 0}, {'raCh': 11, 'raNm': 'x', 'raSt': 0}]}
        gate = {'ctim': 1, 'waCV': 0x8000, 'raNA': 1, 'raDS': 1, 'raWB': 0, 'waUB': None}
        args = cli.build_parser().parse_args(['wifi', 'join', 'Home', '--wifi-password', 'pw123456',
                                              '--dry-run'])
        args.host, args.password = '10.0.1.1', 'pw'
        out = io.StringIO()
        with mock.patch.object(cli.wifimod, 'load', return_value=(blob, b'')), \
                mock.patch.object(cli.modemod, 'read_gate', return_value=(gate, {})), \
                redirect_stdout(out):
            cli.cmd_wifi_join(args)
        self.assertIn("radio 1 (2.4 GHz): JOIN 'Home'", out.getvalue())
        self.assertIn('radio 0: Wi-Fi OFF', out.getvalue())


class Info(unittest.TestCase):
    def info(self, dev):
        args = cli.build_parser().parse_args(['info'])
        args.host, args.password = '10.0.1.1', 'pw'
        out = io.StringIO()
        with mock.patch.object(acp, 'read_device', return_value=dev), redirect_stdout(out):
            cli.cmd_info(args)
        return out.getvalue()

    def test_tested(self):
        out = self.info(A1392)
        self.assertIn('A1392, codename K31', out)
        self.assertIn('status:   tested', out)
        self.assertIn('join:     possible', out)

    def test_untested(self):
        out = self.info(A1301)
        self.assertIn('cpu:      armeb', out)
        self.assertIn('NOT tested', out)
        self.assertIn('join:     not on this model', out)
        self.assertIn('unknown product 999', self.info({'syAP': 999}))


if __name__ == '__main__':
    unittest.main()
