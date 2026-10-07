import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('tools_check',Path(__file__).with_name('personal-tools-check.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PersonalToolsCheck(unittest.TestCase):
    def node(self, peer):
        return dict(t3='0.0.4503',t3_running=['0.0.4503'],t3_launcher_correct=True,switcher='0.7.16',protocol=1,pair_enabled=True,peer_ip=peer,activity_fresh=True,pair_connected=True,switcher_binary_matches=True,switcher_running=True,proxy_running=True,codex_proxy_routed=True)
    def report(self,nodes,releases=None):
        with contextlib.redirect_stdout(io.StringIO()):return m.evaluate(nodes,releases)
    def test_supported_pair(self):
        nodes={a:self.node(next(b for b in m.PCS if b!=a)) for a in m.PCS}
        self.assertEqual(self.report(nodes),[])
    def test_offline_peer_is_unverified(self):
        self.assertTrue(any('unverified' in p for p in self.report({'100.104.44.67':self.node('100.95.7.78')})))
    def test_mismatch_and_running_old_version(self):
        nodes={a:self.node(next(b for b in m.PCS if b!=a)) for a in m.PCS}
        nodes['100.95.7.78']['t3']='0.0.4504'
        nodes['100.95.7.78']['t3_launcher_correct']=False
        errors=self.report(nodes)
        self.assertTrue(any('running and installed' in p for p in errors))
        self.assertTrue(any('old Switcher launcher' in p for p in errors))
        self.assertTrue(any('versions differ' in p for p in errors))
    def test_old_switcher_and_missing_peer_are_not_pass(self):
        nodes={a:self.node(next(b for b in m.PCS if b!=a)) for a in m.PCS}
        nodes['100.95.7.78'].update(switcher_binary_matches=False,pair_connected=False,peer_ip=None,codex_proxy_routed=False)
        errors=self.report(nodes)
        self.assertTrue(any('running Switcher differs' in p for p in errors))
        self.assertTrue(any('authenticated peer' in p for p in errors))
        self.assertTrue(any('bypass Switcher' in p for p in errors))
        self.assertTrue(any('not configured' in p for p in errors))
    def test_third_pc_and_unknown_latest_are_not_pass(self):
        nodes={a:self.node('100.80.99.112') for a in m.PCS}
        errors=self.report(nodes,{'t3':None})
        self.assertTrue(any('outside the two' in p for p in errors))
        self.assertTrue(any('could not be verified' in p for p in errors))
if __name__=='__main__':unittest.main()
