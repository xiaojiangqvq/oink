"""Extract and verify an NSIS installer read-only; never execute its entry point."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
REQUIRED_SUPPORT = ('manifest.json', 'LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE',
                    'THIRD_PARTY_LICENSES.md', 'third-party-licenses.json', 'modified-source.zip',
                    'source-changes.patch', 'installer-source.zip', '使用说明.txt',
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
    if set(manifest['files']) != {'Oink.msi', RUNTIME}:
        raise ValueError('Complete offline payload missing')
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


def sevenzip_tool(explicit=None):
    path = explicit or shutil.which('7z') or Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / '7-Zip/7z.exe'
    if not Path(path).is_file():
        raise RuntimeError('7-Zip is required for independent, nonexecuting NSIS verification; use --sevenzip')
    return str(Path(path).resolve())


def extract(installer, output, sevenzip=None):
    command = sevenzip_tool(sevenzip)
    listing = subprocess.check_output([command, 'l', '-slt', '-ba', '-sccUTF-8', str(installer)], text=True, encoding='utf-8')
    for line in listing.splitlines():
        if line.startswith('Path = '):
            safe_archive_path(line.removeprefix('Path = '))
    extracted = output / ('extracted-' + uuid.uuid4().hex)
    extracted.mkdir(parents=True)
    subprocess.run([command, 'x', '-y', '-bd', '-o' + str(extracted), str(installer)],
                   check=True, capture_output=True)
    return extracted


def extract_and_verify(installer, output, sevenzip=None):
    extracted = extract(installer, output, sevenzip)
    candidates = list(extracted.rglob('manifest.json'))
    if len(candidates) != 1 or candidates[0].parent.name != 'Support':
        raise ValueError('Expected exactly one embedded support manifest')
    support = candidates[0].parent
    payload = support.parent / 'payload'
    manifest = json.loads(candidates[0].read_text(encoding='utf-8-sig'))
    verify_payloads(payload, manifest)
    verify_source(support / 'modified-source.zip', manifest)
    if any(not (support / name).is_file() for name in REQUIRED_SUPPORT):
        raise ValueError('Embedded source, notice, or license file missing')
    with zipfile.ZipFile(support / 'installer-source.zip') as source:
        for name in ('installer.nsi', 'build.py', 'verify_installer.py'):
            if source.read('packaging/trail-installer/' + name) != (HERE / name).read_bytes():
                raise ValueError('Embedded installer source mismatch: ' + name)
    for name in ('WEBVIEW2-NOTICE.txt', 'WebView2-LICENSE.txt', 'NSIS-LICENSE.txt', 'WIX-LICENSE.txt'):
        if (support / name).read_bytes() != (HERE / name).read_bytes():
            raise ValueError('Embedded license differs from reviewed source: ' + name)
    checks = ['7-Zip extraction without executing installer', 'embedded full MSI and offline runtime hashes',
              'MSI identity, source metadata and complete component inventory', 'Microsoft runtime signature',
              'complete source inventory and recomputed tree hash', 'matching installer source and legal notices']
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
    record = {'schema': 1, 'installer_sha256': sha(installer), 'version': manifest['version'],
              'build': manifest['build'], 'source_commit': manifest['source_commit'],
              'source_tree_sha256': manifest['source_tree_sha256'], 'checks': checks,
              'no_installation_performed': True, 'fresh_machine_installation_tested': False,
              'extracted': str(extracted)}
    (output / 'installer-smoke.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
