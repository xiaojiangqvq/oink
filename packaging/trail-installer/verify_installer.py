"""Non-installing smoke checks for the compiled overwrite installer."""
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
    for name, expected in manifest['files'].items():
        assert sha(extracted / 'payload' / name) == expected
    # Existing extraction targets are refused, never overwritten or deleted.
    again = subprocess.run([str(installer), '--extract-package', str(extracted)])
    assert again.returncode != 0
    checks = ['embedded package verification', 'bounded extraction and payload hashes', 'existing extraction target refusal']
    if not ctypes.windll.shell32.IsUserAnAdmin():
        # An explicit worker flag must not grant privileges or invoke UAC.
        result = subprocess.run([str(installer), '--worker', 'Upgrade', str(output), uuid.uuid4().hex])
        assert result.returncode != 0
        checks.append('unprivileged worker refusal without elevation')
    preview = output / 'installer-preview.png'
    subprocess.run([str(installer), '--render-preview', str(preview)], check=True)
    assert preview.stat().st_size > 1000
    pointer_preview = output / 'installer-custom-pointer-preview.png'
    subprocess.run([str(installer), '--render-preview-custom-pointer', str(pointer_preview)], check=True)
    assert pointer_preview.stat().st_size > 1000
    checks.append('real WinForms layout render')
    record = {'schema': 1, 'installer_sha256': sha(installer), 'patch_id': manifest['patch_id'],
              'checks': checks, 'no_installation_performed': True, 'preview': str(preview), 'extracted': str(extracted)}
    (output / 'installer-smoke.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
