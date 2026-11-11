"""Build the local Windows overwrite installer; never install or elevate it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PAYLOAD = ('oink.exe', 'oink-agent.exe', 'oink-build.json', 'report-manifest.json')
SCRIPTS = ('Run-Patch.ps1', 'Patch-Common.ps1', 'Upgrade-TrailPatch.ps1',
           'Install-TrailPatch.ps1', 'Restore-OriginalOink.ps1')
EXTRAS = ('LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE', 'THIRD_PARTY_LICENSES.md',
          'third-party-licenses.json', 'modified-source.zip', 'source-changes.patch')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    bundle, output = args.bundle.resolve(), args.output.resolve()
    try:
        output.relative_to(REPO)
    except ValueError:
        inside_source = False
    else:
        inside_source = True
    if inside_source:
        parser.error('generated outputs must be outside the source repository')
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8-sig'))
    if set(manifest['files']) != set(PAYLOAD):
        raise ValueError('bundle payload inventory differs from the four supported files')
    for name in PAYLOAD:
        if sha(bundle / 'payload' / name) != manifest['files'][name]:
            raise ValueError('payload hash mismatch: ' + name)
    for name in ('oink-build.json', 'report-manifest.json'):
        metadata = json.loads((bundle / 'payload' / name).read_text(encoding='utf-8-sig'))
        if metadata['source_tree_sha256'] != manifest['source_tree_sha256']:
            raise ValueError('payload source identity mismatch: ' + name)
    extras = {}
    for name in EXTRAS:
        source = bundle / name
        if not source.is_file() and name not in ('modified-source.zip', 'source-changes.patch'):
            source = REPO / name
        if not source.is_file():
            raise ValueError('required source or license artifact missing: ' + name)
        extras[name] = source
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'payload.zip'
    installer_source = output / 'installer-source.zip'
    with zipfile.ZipFile(installer_source, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path in sorted(HERE.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                zipped.write(path, 'packaging/trail-installer/' + path.relative_to(HERE).as_posix())
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        zipped.write(bundle / 'manifest.json', 'manifest.json')
        for name in PAYLOAD:
            zipped.write(bundle / 'payload' / name, 'payload/' + name)
        for name in SCRIPTS:
            zipped.write(HERE / 'scripts' / name, name)
        zipped.write(HERE / '使用说明.txt', '使用说明.txt')
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
    report = output / 'package-verification.json'
    subprocess.run([str(executable), '--verify-package', str(report)], check=True)
    result = json.loads(report.read_text(encoding='utf-8'))
    if not result.get('verified') or result['source_tree_sha256'] != manifest['source_tree_sha256']:
        raise RuntimeError('compiled installer verification failed')
    record = {'schema': 1, 'kind': 'third-party-personal-overwrite-installer', 'signed': False,
              'base_version': '0.3.4', 'base_build': 108, 'patch_id': manifest['patch_id'],
              'source_tree_sha256': manifest['source_tree_sha256'], 'payload_zip_sha256': archive_hash,
              'installer_sha256': sha(executable), 'installer_size': executable.stat().st_size}
    (output / 'installer-build.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'installer': str(executable), 'bytes': executable.stat().st_size,
                      'sha256': record['installer_sha256'], 'verified': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
