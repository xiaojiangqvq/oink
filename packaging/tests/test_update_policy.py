"""Production packages cannot ship the removed automatic-install policy."""
from pathlib import Path
import base64
import json
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build-support'))
from update_qualification import verify_binaries

class UpdatePolicyContent(unittest.TestCase):
    def test_fork_disables_windows_feed_without_erasing_manual_package_trust(self):
        trust = json.loads((ROOT / 'packaging/update-trust.json').read_text())
        self.assertTrue(trust['mac']['enabled'])
        self.assertEqual(len(base64.b64decode(trust['mac']['public_key'])), 32)
        self.assertEqual(len(trust['windows']), 1)
        windows = trust['windows'][0]
        self.assertFalse(windows['enabled'])
        self.assertEqual(windows['epoch'], 'win-2026-01')
        self.assertEqual(len(base64.b64decode(windows['public_key'])), 32)
        self.assertEqual(windows['authenticode_spki_sha256'], [])

    def test_removed_policy_is_rejected_in_executables_and_frontend(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'product'
            for marker in ('waiting_for_idle', 'may_download_automatically', 'Install automatically when idle'):
                for encoding in ('utf-8', 'utf-16le'):
                    binary.write_bytes(marker.encode(encoding))
                    with self.assertRaisesRegex(ValueError, 'removed automatic-install'):
                        verify_binaries([binary])
            binary.write_bytes(b'check download ready install quiescing')
            verify_binaries([binary])

if __name__ == '__main__':
    unittest.main()
