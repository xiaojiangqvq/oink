"""Build a complete offline Windows EXE around a verified full MSI; never install."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUNTIME = 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
PAYLOAD = ('Oink.msi', RUNTIME)
EXTRAS = ('LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE', 'THIRD_PARTY_LICENSES.md',
          'third-party-licenses.json', 'modified-source.zip', 'source-changes.patch')
DOCS = ('使用说明.txt', 'WEBVIEW2-NOTICE.txt', 'WebView2-LICENSE.txt')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_bundle(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8-sig'))
    if (manifest.get('schema'), manifest.get('kind'), manifest.get('architecture'),
            manifest.get('version'), manifest.get('build'), manifest.get('msi_version')) != (
            1, 'third-party-oink-full-installer', 'x64', '0.3.4-inhouse.109', 109, '0.0.109'):
        raise ValueError('not the supported full installer manifest')
    sys.path.insert(0, str(REPO / 'build-support'))
    from provenance import source_inventory, source_tree_sha256
    inventory = (source_inventory(REPO) if (REPO / '.git').exists() else
                 json.loads((REPO.parent / 'source-inventory.json').read_text(encoding='utf-8'))['files'])
    if source_tree_sha256(REPO, inventory) != manifest['source_tree_sha256']:
        raise ValueError('current installer/source differs from the complete bundle source')
    if (REPO / '.git').exists() and subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() != manifest['source_commit']:
        raise ValueError('current commit differs from full bundle source')
    if set(manifest['files']) != set(PAYLOAD):
        raise ValueError('full MSI and offline WebView2 runtime are required')
    for name in PAYLOAD:
        if sha(bundle / 'payload' / name) != manifest['files'][name]:
            raise ValueError('payload hash mismatch: ' + name)
    # Query MSI tables read-only, without custom actions or installation.
    sys.path.insert(0, str(REPO / 'packaging/windows'))
    from tables import read_content_tables
    tables = read_content_tables(bundle / 'payload/Oink.msi')
    properties = dict(tables['Property'])
    for key, expected in {'ProductVersion': manifest['msi_version'], 'OINK_VERSION': manifest['version'],
                          'OINK_SOURCE_TREE': manifest['source_tree_sha256']}.items():
        if properties.get(key) != expected:
            raise ValueError('MSI metadata differs from full bundle: ' + key)
    for key, field in [('ProductCode', 'product_code'), ('UpgradeCode', 'upgrade_code')]:
        if uuid.UUID(properties[key]) != uuid.UUID(manifest[field]):
            raise ValueError('MSI product identity mismatch: ' + key)
    if uuid.UUID(manifest['upgrade_code']) != uuid.UUID('4D39E4BE-6792-4CD6-B344-A5E95A270EA6'):
        raise ValueError('MSI must retain the installed Oink upgrade family')
    if uuid.UUID(manifest['product_code']) != uuid.uuid5(uuid.UUID(manifest['upgrade_code']), 'pointer-trail-enhanced:109'):
        raise ValueError('MSI must use the separate fork ProductCode namespace')
    runtime = json.loads((HERE / 'webview2-runtime.json').read_text(encoding='utf-8'))
    if (manifest['files'][RUNTIME] != runtime['sha256'] or
            (bundle / 'payload' / RUNTIME).stat().st_size != runtime['size']):
        raise ValueError('WebView2 differs from the pinned Microsoft release')
    names = {row[2].split('|')[-1] for row in tables['File']}
    required = {'oink.exe', 'oink-agent.exe', 'oink-service.exe', 'oink-update-worker.exe',
                'oink-crash-collector.exe', 'OinkCredentialProvider.dll', 'OinkPasteMenu.dll',
                'installed.json', 'oink-build.json', 'report-manifest.json'}
    if not required <= names:
        raise ValueError('MSI is not the full product payload')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    bundle, output = args.bundle.resolve(), args.output.resolve()
    try:
        output.relative_to(REPO)
    except ValueError:
        pass
    else:
        parser.error('generated outputs must be outside the source repository')
    manifest = verify_bundle(bundle)
    extras = {}
    for name in EXTRAS:
        source = bundle / name
        if not source.is_file() and name not in ('modified-source.zip', 'source-changes.patch'):
            source = REPO / name
        if not source.is_file():
            raise ValueError('required source or license artifact missing: ' + name)
        extras[name] = source
    for name in DOCS:
        if not (HERE / name).is_file():
            raise ValueError('required installer document missing: ' + name)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'payload.zip'
    installer_source = output / 'installer-source.zip'
    with zipfile.ZipFile(installer_source, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path in sorted(HERE.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                zipped.write(path, 'packaging/trail-installer/' + path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        zipped.write(bundle / 'manifest.json', 'manifest.json')
        for name in PAYLOAD:
            zipped.write(bundle / 'payload' / name, 'payload/' + name)
        for name in DOCS:
            zipped.write(HERE / name, name)
        zipped.write(installer_source, 'installer-source.zip')
        for name, source in extras.items():
            zipped.write(source, name)
    archive_hash = sha(archive)
    generated = output / 'BuildInfo.cs'
    generated.write_text('internal static class BuildInfo { internal const string ArchiveSha256 = '
                         + json.dumps(archive_hash) + '; }\n', encoding='utf-8')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():
        raise RuntimeError('Windows .NET Framework 4 x64 C# compiler is required')
    executable = output / 'PointerTrail-Setup.exe'
    command = [str(compiler), '/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/codepage:65001',
               '/out:' + str(executable), '/win32manifest:' + str(HERE / 'installer.manifest'),
               '/resource:' + str(archive) + ',payload.zip', '/reference:System.dll',
               '/reference:System.Core.dll', '/reference:System.Drawing.dll', '/reference:System.Windows.Forms.dll',
               '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
               '/reference:System.Web.Extensions.dll', str(HERE / 'Installer.cs'), str(generated)]
    subprocess.run(command, check=True)
    # Chain validation and exact Microsoft signer; never execute the runtime or
    # install any certificate during packaging.
    subprocess.run([str(executable), '--verify-runtime', str(bundle / 'payload' / RUNTIME)], check=True)
    report = output / 'package-verification.json'
    subprocess.run([str(executable), '--verify-package', str(report)], check=True)
    result = json.loads(report.read_text(encoding='utf-8'))
    if not result.get('verified') or result['source_tree_sha256'] != manifest['source_tree_sha256']:
        raise RuntimeError('compiled full installer verification failed')
    record = {'schema': 1, 'kind': 'third-party-full-offline-installer', 'signed': False,
              'version': manifest['version'], 'build': manifest['build'],
              'source_commit': manifest['source_commit'], 'source_tree_sha256': manifest['source_tree_sha256'],
              'payload_zip_sha256': archive_hash, 'msi_sha256': manifest['files']['Oink.msi'],
              'webview2_sha256': manifest['files'][RUNTIME],
              'installer_sha256': sha(executable), 'installer_size': executable.stat().st_size}
    (output / 'installer-build.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'installer': str(executable), 'bytes': executable.stat().st_size,
                      'sha256': record['installer_sha256'], 'verified': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
