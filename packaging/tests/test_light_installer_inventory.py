"""Lightweight distribution must not silently re-embed source or the offline runtime."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('light_installer_verifier', ROOT / 'packaging/trail-installer/verify_installer.py')
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class LightweightInstallerInventory(unittest.TestCase):
    def setUp(self):
        self.files = ['$PLUGINSDIR/System.dll', '$PLUGINSDIR/nsDialogs.dll',
                      '$PLUGINSDIR/payload/Oink.msi', '$PLUGINSDIR/payload/MicrosoftEdgeWebview2Setup.exe']
        self.files += ['$PLUGINSDIR/Support/' + name for name in VERIFIER.REQUIRED_SUPPORT]

    def test_valid_native_archive_paths_can_use_windows_separators(self):
        actual = VERIFIER.validate_archive_inventory([name.replace('/', '\\') for name in self.files])
        self.assertEqual(actual, set(self.files))

    def test_source_archives_and_patches_are_rejected_at_every_embedding_location(self):
        for folder in ('$PLUGINSDIR', '$PLUGINSDIR/payload', '$PLUGINSDIR/Support'):
            for name in ('modified-source.zip', 'application-source.zip', 'installer-source.zip', 'source-changes.patch'):
                with self.subTest(folder=folder, name=name), self.assertRaisesRegex(ValueError, 'Unexpected embedded'):
                    VERIFIER.validate_archive_inventory(self.files + [folder + '/' + name])

    def test_old_standalone_runtime_cannot_replace_or_accompany_bootstrapper(self):
        old = '$PLUGINSDIR/payload/MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
        for files in (self.files + [old], [name for name in self.files if name != '$PLUGINSDIR/payload/MicrosoftEdgeWebview2Setup.exe'] + [old]):
            with self.subTest(files=files), self.assertRaisesRegex(ValueError, 'Unexpected embedded'):
                VERIFIER.validate_archive_inventory(files)

    def test_msi_and_required_legal_files_cannot_be_omitted(self):
        for name in ('$PLUGINSDIR/payload/Oink.msi', '$PLUGINSDIR/Support/WebView2-LICENSE.txt', '$PLUGINSDIR/Support/manifest.json'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'missing'):
                VERIFIER.validate_archive_inventory([file for file in self.files if file != name])

    def test_duplicate_case_aliases_and_path_traversal_are_rejected_before_extraction(self):
        for extra in ('$PLUGINSDIR/Support/manifest.json', '$PLUGINSDIR/SUPPORT/MANIFEST.JSON',
                      '$PLUGINSDIR/../outside.txt', 'C:/outside.txt', '//server/share/file'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                VERIFIER.validate_archive_inventory(self.files + [extra])

    def test_unlisted_helpers_and_private_artifacts_are_rejected(self):
        for extra in ('$PLUGINSDIR/helper.exe', '$PLUGINSDIR/Support/.release-tools/check.py',
                      '$PLUGINSDIR/Support/settings.json', '$PLUGINSDIR/payload/private-backups/profile.json'):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'Unexpected embedded'):
                VERIFIER.validate_archive_inventory(self.files + [extra])


if __name__ == '__main__':
    unittest.main()
