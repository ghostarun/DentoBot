import tempfile
import unittest
from pathlib import Path

import case_sync
import handoff


class CaseSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.a = handoff.Machine('A', {'host': None, 'repo': str(base/'a/ros2_ws/src/DentoBot'), 'output': str(base/'outA')})
        self.b = handoff.Machine('B', {'host': None, 'repo': str(base/'b/ros2_ws/src/DentoBot'), 'output': str(base/'outB')})
        self.source = base/'a/data/Shared/case.dentocase'
        self.target = base/'b/data/Shared/case.dentocase'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'original-case')

    def test_copy_then_unchanged_noop_and_backed_up_replace(self):
        result = case_sync.sync_case(self.a, self.b, 'Shared/case.dentocase')
        self.assertEqual(self.target.read_bytes(), b'original-case')
        self.assertFalse(result['already_identical'])
        self.assertTrue(case_sync.sync_case(self.a, self.b, 'Shared/case.dentocase')['already_identical'])
        self.source.write_bytes(b'new-case')
        with self.assertRaisesRegex(RuntimeError, 'different destination exists'):
            case_sync.sync_case(self.a, self.b, 'Shared/case.dentocase')
        self.assertEqual(self.target.read_bytes(), b'original-case')
        result = case_sync.sync_case(self.a, self.b, 'Shared/case.dentocase', replace=True)
        self.assertEqual(self.target.read_bytes(), b'new-case')
        self.assertEqual(Path(result['backup']).read_bytes(), b'original-case')

    def test_traversal_and_source_symlink_escape_rejected(self):
        for path in ('../case.dentocase', '/case.dentocase', 'Shared/case.mrb'):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                case_sync.sync_case(self.a, self.b, path)
        self.source.unlink()
        self.source.symlink_to(Path(self.tmp.name)/'outside.dentocase')
        with self.assertRaisesRegex(RuntimeError, 'escapes'):
            case_sync.sync_case(self.a, self.b, 'Shared/case.dentocase')

    def test_destination_symlink_escape_preserves_outside(self):
        outside = Path(self.tmp.name)/'outside'
        outside.mkdir()
        self.target.parent.parent.mkdir(parents=True)
        self.target.parent.symlink_to(outside)
        with self.assertRaises(RuntimeError):
            case_sync.sync_case(self.a, self.b, 'Shared/case.dentocase')
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == '__main__': unittest.main()
