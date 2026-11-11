"""Prepare a shareable patch bundle from verified release output; no installation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build-support'))
from provenance import EXCLUDED, source_inventory, source_tree_sha256
from report_manifest import write_manifest

BASE_COMMIT = 'ec2fd6ae9ec8d1a55e024aed661a022a9960c337'
BASE_TREE = '4c64684ad734be155cbbf7b4f1bd5a118c145f9b99d39b33d0ab44de8b1a1d99'
PAYLOAD = ('oink.exe', 'oink-agent.exe', 'report-manifest.json', 'oink-build.json')
NOTICES = ('LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE',
           'THIRD_PARTY_LICENSES.md', 'third-party-licenses.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binaries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-inventory', type=Path)
    parser.add_argument('--source-patch', type=Path)
    args = parser.parse_args()
    binaries, output = args.binaries.resolve(), args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error('output must be outside the source repository')
    if output.exists() and any(output.iterdir()):
        parser.error('output must be empty to avoid mixing old packages')
    build = json.loads((binaries / 'release-build.json').read_text(encoding='utf-8'))
    has_git = (ROOT / '.git').exists()
    inventory_path = args.source_inventory
    if not has_git and inventory_path is None:
        inventory_path = ROOT.parent / 'source-inventory.json'
    inventory = (json.loads(inventory_path.read_text(encoding='utf-8'))['files']
                 if inventory_path else source_inventory(ROOT))
    tree = source_tree_sha256(ROOT, inventory)
    if (build.get('schema') != 1 or build.get('provenance') != 'source-tree' or
            build.get('update_test_feed') is not None or build.get('update_test_fail_health') is not False or
            build.get('identity_sha256') != digest(ROOT / 'packaging/identity.json')):
        raise ValueError('test-only updater build or mismatched product identity cannot be distributed')
    if (build['source_tree_sha256'], build['version'], build['build'], build['target']) != (
            tree, '0.3.4', 108, 'x86_64-pc-windows-msvc'):
        raise ValueError('release binaries do not match this source/base/target')
    for name in PAYLOAD[:2]:
        if digest(binaries / name) != build['files'][name]:
            raise ValueError('release binary hash mismatch: ' + name)
    # Distribution must contain newly added product files as well as old files.
    if has_git:
        tracked = {raw.decode('utf-8') for raw in subprocess.check_output(
            ['git', 'ls-files', '-z'], cwd=ROOT).split(b'\0') if raw}
    else:
        tracked = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob('*')
                   if path.is_file() and not any(part in EXCLUDED for part in path.relative_to(ROOT).parts)}
    missing = {entry['path'] for entry in inventory} - tracked
    if missing:
        raise ValueError('add new source files to Git before packaging: ' + ', '.join(sorted(missing)))
    payload = output / 'payload'
    payload.mkdir(parents=True)
    for name in PAYLOAD[:2]:
        shutil.copy2(binaries / name, payload / name)
    report = write_manifest(payload / 'report-manifest.json', tree, '0.3.4', 108,
                            [('agent', payload / 'oink.exe'), ('agent', payload / 'oink-agent.exe'),
                             ('ui_rust', payload / 'oink.exe')])
    metadata = {
        'schema': 1, 'product': 'Oink', 'provenance': 'personal-source-tree-patch',
        'source_tree_sha256': tree, 'version': '0.3.4', 'source_commit': build.get('source_commit'),
        'build': 108, 'architecture': 'x64', 'minimum_os': '10.0', 'minimumWindowsBuild': 17763,
        'protocol_baseline': 1, 'upgrade_code': '4D39E4BE-6792-4CD6-B344-A5E95A270EA6',
        'components': ['oink.exe', 'oink-agent.exe', 'oink-service.exe',
                       'oink-update-worker.exe', 'oink-crash-collector.exe'],
        'updater_included': True, 'collector_included': True,
        'update_test_feed': None, 'update_test_fail_health': False, 'signing': 'unsigned',
        'report_manifest': report,
        'personal_patch': {
            'name': 'pointer-trail-enhanced', 'base_version': '0.3.4', 'base_build': 108,
            'base_source_tree_sha256': BASE_TREE, 'replaced_components': list(PAYLOAD[:2]),
            'description': 'Third-party modification: selectable trail trigger, independent trail color, Windows arrow styles and sizes.',
        },
    }
    write_json(payload / 'oink-build.json', metadata)
    manifest = {
        'schema': 1, 'kind': 'personal-oink-movement-trail-patch',
        'patch_id': 'pointer-trail-enhanced-0.3.4-' + tree[:12],
        'base_version': '0.3.4', 'base_build': 108, 'architecture': 'x64',
        'base_source_tree_sha256': BASE_TREE, 'source_tree_sha256': tree,
        'files': {name: digest(payload / name) for name in PAYLOAD},
    }
    write_json(output / 'manifest.json', manifest)
    for name in NOTICES:
        shutil.copy2(ROOT / name, output / name)
    if has_git:
        subprocess.run(['git', 'diff', '--binary', '--output=' + str(output / 'source-changes.patch'),
                        BASE_COMMIT], cwd=ROOT, check=True)
    else:
        shutil.copy2(args.source_patch or ROOT.parent / 'source-changes.patch', output / 'source-changes.patch')
    snapshot = {'schema': 1, 'source_tree_sha256': tree, 'files': inventory}
    modes = {entry['path']: entry['mode'] for entry in inventory}
    with zipfile.ZipFile(output / 'modified-source.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(tracked):
            path = ROOT / name
            if not path.is_file():
                continue
            info = zipfile.ZipInfo.from_file(path, 'pointer-trail-enhanced/' + name)
            info.create_system = 3
            info.external_attr = int(modes.get(name, '100644'), 8) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
        archive.writestr('source-inventory.json', json.dumps(snapshot, indent=2) + '\n')
        archive.write(output / 'source-changes.patch', 'source-changes.patch')
    write_json(output / 'bundle-build.json', {
        'schema': 1, 'base_git_commit': BASE_COMMIT, 'source_tree_sha256': tree,
        'source_zip_sha256': digest(output / 'modified-source.zip'),
        'payload_hashes_verified': True, 'live_verification': 'not_asserted_by_bundle_builder',
    })
    print(json.dumps({'bundle': str(output), 'source_tree_sha256': tree, 'patch_id': manifest['patch_id']}))


if __name__ == '__main__':
    main()
