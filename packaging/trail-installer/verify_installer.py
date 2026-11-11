"""Read-only and disposable-output checks; never run the actual installer worker."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import uuid


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    installer, output = args.installer.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / 'verification.json'
    subprocess.run([str(installer), '--verify-package', str(report_path)], check=True)
    verification = json.loads(report_path.read_text(encoding='utf-8'))
    assert verification['verified'] is True
    extracted = output / ('extracted-' + uuid.uuid4().hex)
    subprocess.run([str(installer), '--extract-package', str(extracted)], check=True)
    manifest = json.loads((extracted / 'manifest.json').read_text(encoding='utf-8-sig'))
    assert manifest['kind'] == 'third-party-oink-full-installer'
    for name, expected in manifest['files'].items():
        assert sha(extracted / 'payload' / name) == expected
    again = subprocess.run([str(installer), '--extract-package', str(extracted)])
    assert again.returncode != 0
    subprocess.run([str(installer), '--verify-runtime',
                    str(extracted / 'payload/MicrosoftEdgeWebView2RuntimeInstallerX64.exe')], check=True)
    rules_path = output / 'rules.json'
    subprocess.run([str(installer), '--test-rules', str(rules_path)], check=True)
    rules = json.loads(rules_path.read_text(encoding='utf-8'))
    assert rules['passed'] is True
    checks = ['embedded full package verification', 'bounded extraction and payload hashes',
              'existing extraction target refusal', 'Microsoft runtime chain and signer verification'] + rules['checks']
    if not ctypes.windll.shell32.IsUserAnAdmin():
        # This only exercises the earliest explicit privilege refusal. It must
        # not invoke UAC, stage content, call MSI, or mutate installed state.
        result = subprocess.run([str(installer), '--worker', uuid.uuid4().hex, 'runtime-not-needed'])
        assert result.returncode != 0
        checks.append('unprivileged worker refusal without elevation')
    preview = output / 'installer-preview.png'
    subprocess.run([str(installer), '--render-preview', str(preview)], check=True)
    assert preview.stat().st_size > 1000
    missing_preview = output / 'installer-missing-runtime-preview.png'
    subprocess.run([str(installer), '--render-preview-missing-runtime', str(missing_preview)], check=True)
    assert missing_preview.stat().st_size > 1000
    checks.append('real WinForms layouts for existing and missing runtime')
    record = {'schema': 1, 'installer_sha256': sha(installer), 'version': manifest['version'],
              'build': manifest['build'], 'checks': checks, 'no_installation_performed': True,
              'fresh_machine_installation_tested': False, 'preview': str(preview), 'extracted': str(extracted)}
    (output / 'installer-smoke.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
