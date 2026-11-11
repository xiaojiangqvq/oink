"""Extract and verify an NSIS installer read-only; never execute its entry point."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = 'MicrosoftEdgeWebview2Setup.exe'
APPLICATION_SOURCE_COMMIT = 'c6d0ca0ae3ee629142bf39f7fbc7805caf6c8bb4'
APPLICATION_SOURCE_TREE = 'dd7c12c4bb7d3881ee4bdb608510882a9a8c570976bbc6debb78d6efeaf96064'
APPLICATION_MSI_SHA256 = 'bcdbbb44017817fc2966e3060dd174aac24a0faab1b4e55db8d0a37d3788553a'
REQUIRED_SUPPORT = ('manifest.json', 'LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE',
                    'THIRD_PARTY_LICENSES.md', 'third-party-licenses.json', '使用说明.txt',
                    'WEBVIEW2-NOTICE.txt', 'WebView2-LICENSE.txt', 'WIX-LICENSE.txt',
                    'NSIS-LICENSE.txt', 'license.html', 'license.txt')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_runtime(path):
    record = json.loads((HERE / 'webview2-runtime.json').read_text(encoding='utf-8'))
    if (record.get('kind'), record.get('filename')) != ('evergreen-bootstrapper', RUNTIME):
        raise ValueError('Expected the pinned Microsoft WebView2 bootstrapper')
    if sha(path) != record['sha256'] or path.stat().st_size != record['size']:
        raise ValueError('Runtime differs from the pinned Microsoft release')
    command = ("$ErrorActionPreference='Stop'; "
               "$s=Get-AuthenticodeSignature -LiteralPath $env:OINK_VERIFY_RUNTIME; "
               "if($s.Status -ne 'Valid' -or "
               "$s.SignerCertificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false) -ne 'Microsoft Corporation') "
               "{throw 'Microsoft runtime signature validation failed'}")
    environment = os.environ.copy()
    environment['OINK_VERIFY_RUNTIME'] = str(path)
    powershell = Path(os.environ['WINDIR']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    # A Python process launched by PowerShell 7 can inherit its incompatible
    # module paths. Use the selected Windows PowerShell's own security module.
    environment['PSModulePath'] = str(powershell.parent / 'Modules')
    subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', command],
                   env=environment, check=True, capture_output=True)


def safe_archive_path(name):
    path = PurePosixPath(name.replace('\\', '/'))
    if path.is_absolute() or '..' in path.parts or ':' in name or not path.parts:
        raise ValueError('Unsafe archive member path')
    return path


def verify_source(path, expected):
    sys.path.insert(0, str(ROOT / 'build-support'))
    from provenance import product_source
    with zipfile.ZipFile(path) as source:
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate complete source archive members')
        for name in names:
            safe_archive_path(name)
        inventory = json.loads(source.read('source-inventory.json'))
        if (inventory['source_tree_sha256'], inventory['source_commit'],
                source.read('source-commit.txt').decode('ascii').strip()) != (
                expected['source_tree_sha256'], expected['source_commit'], expected['source_commit']):
            raise ValueError('Complete source archive identity mismatch')
        entries = inventory['files']
        relative_names = {name.removeprefix('pointer-trail-enhanced/') for name in names
                          if name.startswith('pointer-trail-enhanced/') and not name.endswith('/')}
        if ({entry['path'] for entry in entries} != {name for name in relative_names if product_source(name)}
                or len({entry['path'] for entry in entries}) != len(entries)):
            raise ValueError('Complete source inventory is missing or repeats files')
        digest = hashlib.sha256()
        for entry in sorted(entries, key=lambda item: item['path'].encode('utf-8')):
            safe_archive_path(entry['path'])
            if entry['mode'] not in ('100644', '100755', '120000'):
                raise ValueError('Invalid portable source mode')
            content = source.read('pointer-trail-enhanced/' + entry['path'])
            if len(content) != entry['size'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
                raise ValueError('Complete source archive file mismatch: ' + entry['path'])
            digest.update(entry['path'].encode('utf-8') + b'\0' + entry['mode'].encode('ascii') + b'\0')
            digest.update(str(len(content)).encode('ascii') + b'\0' + content)
        if digest.hexdigest() != expected['source_tree_sha256']:
            raise ValueError('Complete source tree hash mismatch')


def verify_payloads(payload, manifest):
    if (manifest.get('schema'), manifest.get('kind'), manifest.get('architecture'),
            manifest.get('version'), manifest.get('build'), manifest.get('msi_version')) != (
            1, 'third-party-oink-full-installer', 'x64', '0.3.4-inhouse.110', 110, '0.0.110'):
        raise ValueError('Not the expected complete enhanced installer')
    if (manifest.get('source_commit'), manifest.get('source_tree_sha256')) != (
            APPLICATION_SOURCE_COMMIT, APPLICATION_SOURCE_TREE):
        raise ValueError('Application provenance differs from the tested build 110')
    if (manifest.get('installer_revision'), manifest.get('sources_embedded'),
            manifest.get('offline_runtime_included')) != (2, False, False):
        raise ValueError('Expected the compact revision-2 distribution')
    for field, length in [('installer_source_commit', 40), ('installer_source_tree_sha256', 64)]:
        if not isinstance(manifest.get(field), str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', manifest[field]):
            raise ValueError('Missing or malformed installer provenance: ' + field)
    if set(manifest['files']) != {'Oink.msi', RUNTIME}:
        raise ValueError('Full MSI and lightweight WebView2 bootstrapper are required')
    if manifest['files']['Oink.msi'] != APPLICATION_MSI_SHA256:
        raise ValueError('MSI differs from the exact tested build 110 package')
    for name, expected in manifest['files'].items():
        if sha(payload / name) != expected:
            raise ValueError('Embedded package mismatch: ' + name)
    sys.path.insert(0, str(ROOT / 'packaging/windows'))
    from tables import read_content_tables
    tables = read_content_tables(payload / 'Oink.msi')
    properties = dict(tables['Property'])
    for key, expected in {'ProductVersion': manifest['msi_version'], 'OINK_VERSION': manifest['version'],
                          'OINK_SOURCE_TREE': manifest['source_tree_sha256']}.items():
        if properties.get(key) != expected:
            raise ValueError('MSI metadata differs from embedded manifest: ' + key)
    for key, field in [('ProductCode', 'product_code'), ('UpgradeCode', 'upgrade_code')]:
        if uuid.UUID(properties[key]) != uuid.UUID(manifest[field]):
            raise ValueError('MSI product identity mismatch: ' + key)
    upgrade = uuid.UUID('4D39E4BE-6792-4CD6-B344-A5E95A270EA6')
    if (uuid.UUID(manifest['upgrade_code']) != upgrade or
            uuid.UUID(manifest['product_code']) != uuid.uuid5(upgrade, 'pointer-trail-enhanced:110')):
        raise ValueError('MSI must retain upgrade family and use the fork ProductCode namespace')
    names = {row[2].split('|')[-1] for row in tables['File']}
    required = {'oink.exe', 'oink-agent.exe', 'oink-service.exe', 'oink-update-worker.exe',
                'oink-crash-collector.exe', 'OinkCredentialProvider.dll', 'OinkPasteMenu.dll',
                'installed.json', 'oink-build.json', 'report-manifest.json'}
    if not required <= names:
        raise ValueError('MSI is not the full product payload')
    verify_runtime(payload / RUNTIME)


def verify_installer_source(manifest):
    """Check the wrapper checkout separately from the unchanged application MSI."""
    sys.path.insert(0, str(ROOT / 'build-support'))
    from provenance import source_inventory, source_tree_sha256
    if (ROOT / '.git').exists():
        inventory = source_inventory(ROOT)
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    else:
        record = json.loads((ROOT.parent / 'source-inventory.json').read_text(encoding='utf-8'))
        inventory = record['files']
        commit = record['source_commit']
    if (manifest['installer_source_commit'], manifest['installer_source_tree_sha256']) != (
            commit, source_tree_sha256(ROOT, inventory)):
        raise ValueError('Installer provenance differs from the current wrapper source')


def sevenzip_tool(explicit=None):
    path = explicit or shutil.which('7z') or Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / '7-Zip/7z.exe'
    if not Path(path).is_file():
        raise RuntimeError('7-Zip is required for independent, nonexecuting NSIS verification; use --sevenzip')
    return str(Path(path).resolve())


def validate_archive_inventory(names):
    """Reject unexpected content before extracting, including source ZIP leaks."""
    normalized = [safe_archive_path(name).as_posix() for name in names]
    if len({name.casefold() for name in normalized}) != len(normalized):
        raise ValueError('Duplicate installer archive path')
    required = {'$PLUGINSDIR/payload/Oink.msi', '$PLUGINSDIR/payload/' + RUNTIME}
    required.update('$PLUGINSDIR/Support/' + name for name in REQUIRED_SUPPORT)
    engine_assets = {'$PLUGINSDIR/System.dll', '$PLUGINSDIR/nsDialogs.dll'}
    directories = {'$PLUGINSDIR', '$PLUGINSDIR/Support', '$PLUGINSDIR/payload'}
    supplied = set(normalized)
    if supplied - required - engine_assets - directories:
        raise ValueError('Unexpected embedded installer content (source archives and patches must remain external)')
    if required - supplied:
        raise ValueError('Required lightweight installer payload or legal file missing')
    return supplied


def extract(installer, output, sevenzip=None):
    command = sevenzip_tool(sevenzip)
    listing = subprocess.check_output([command, 'l', '-slt', '-ba', '-sccUTF-8', str(installer)], text=True, encoding='utf-8')
    validate_archive_inventory([line.removeprefix('Path = ') for line in listing.splitlines()
                                if line.startswith('Path = ')])
    extracted = output / ('extracted-' + uuid.uuid4().hex)
    extracted.mkdir(parents=True)
    subprocess.run([command, 'x', '-y', '-bd', '-o' + str(extracted), str(installer)],
                   check=True, capture_output=True)
    return extracted


def extract_and_verify(installer, output, sevenzip=None):
    extracted = extract(installer, output, sevenzip)
    # Recheck actual extracted files as well as 7-Zip's pre-extraction listing.
    validate_archive_inventory([path.relative_to(extracted).as_posix()
                                for path in extracted.rglob('*') if path.is_file()])
    support = extracted / '$PLUGINSDIR' / 'Support'
    payload = support.parent / 'payload'
    manifest = json.loads((support / 'manifest.json').read_text(encoding='utf-8-sig'))
    verify_payloads(payload, manifest)
    for name in ('使用说明.txt', 'WEBVIEW2-NOTICE.txt', 'WebView2-LICENSE.txt', 'NSIS-LICENSE.txt', 'WIX-LICENSE.txt'):
        if (support / name).read_bytes() != (HERE / name).read_bytes():
            raise ValueError('Embedded license differs from reviewed source: ' + name)
    for name in ('LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE', 'THIRD_PARTY_LICENSES.md', 'third-party-licenses.json'):
        if (support / name).read_bytes() != (ROOT / name).read_bytes():
            raise ValueError('Embedded application license differs from reviewed source: ' + name)
    terms = '\n\n'.join((support / name).read_text(encoding='utf-8-sig')
                        for name in ('WEBVIEW2-NOTICE.txt', 'WebView2-LICENSE.txt'))
    if (support / 'license.txt').read_text(encoding='utf-16') != terms:
        raise ValueError('Wizard license text does not include the complete WebView2 notice and terms')
    checks = ['7-Zip extraction without executing installer', 'exact embedded inventory excludes source archives and patches',
              'full MSI and lightweight bootstrapper hashes', 'MSI identity, source metadata and complete component inventory',
              'Microsoft bootstrapper signature', 'separate application and installer provenance references',
              'matching legal notices and complete WebView2 wizard terms']
    return manifest, extracted, checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sevenzip', type=Path)
    args = parser.parse_args()
    installer, output = args.installer.resolve(), args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error('generated outputs must be outside the source repository')
    output.mkdir(parents=True, exist_ok=True)
    manifest, extracted, checks = extract_and_verify(installer, output, args.sevenzip)
    verify_installer_source(manifest)
    checks.append('installer commit and recomputed source tree match current wrapper checkout')
    record = {'schema': 1, 'installer_sha256': sha(installer), 'version': manifest['version'],
              'build': manifest['build'], 'source_commit': manifest['source_commit'],
              'source_tree_sha256': manifest['source_tree_sha256'], 'checks': checks,
              'installer_source_commit': manifest['installer_source_commit'],
              'installer_source_tree_sha256': manifest['installer_source_tree_sha256'],
              'no_installation_performed': True, 'fresh_machine_installation_tested': False,
              'extracted': str(extracted)}
    (output / 'installer-smoke.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
