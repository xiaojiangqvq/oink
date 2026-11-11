"""Build a standard NSIS Modern UI offline installer; never install or elevate it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUNTIME = 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
PAYLOAD = ('Oink.msi', RUNTIME)
EXTRAS = ('LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE', 'THIRD_PARTY_LICENSES.md',
          'third-party-licenses.json', 'modified-source.zip', 'source-changes.patch')
DOCS = ('使用说明.txt', 'WEBVIEW2-NOTICE.txt', 'WebView2-LICENSE.txt', 'WIX-LICENSE.txt', 'NSIS-LICENSE.txt')


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
            1, 'third-party-oink-full-installer', 'x64', '0.3.4-inhouse.110', 110, '0.0.110'):
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
    if uuid.UUID(manifest['product_code']) != uuid.uuid5(uuid.UUID(manifest['upgrade_code']), 'pointer-trail-enhanced:110'):
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


def compiler(cache):
    from verify_installer import safe_archive_path
    record = json.loads((HERE / 'nsis-toolchain.json').read_text(encoding='utf-8'))
    if tuple(int(part) for part in record['version'].split('.')) < (3, 11):
        raise ValueError('NSIS 3.11 or newer is required for protected elevated temporary files')
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / record['filename']
    if not archive.is_file():
        import shutil
        failures = []
        for url in [record['url'], *record.get('fallback_urls', [])]:
            if not url.startswith('https://'):
                raise ValueError('NSIS tool archive must use HTTPS')
            temporary = cache / ('nsis-download-' + uuid.uuid4().hex + '.zip')
            try:
                with urllib.request.urlopen(url, timeout=30) as response, temporary.open('wb') as destination:
                    shutil.copyfileobj(response, destination)
                if sha(temporary) != record['sha256']:
                    raise ValueError('Downloaded NSIS archive hash mismatch')
                temporary.replace(archive)
                break
            except (OSError, ValueError) as error:
                failures.append(type(error).__name__)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            raise RuntimeError('Could not obtain pinned NSIS archive: ' + ', '.join(failures))
    if sha(archive) != record['sha256']:
        raise ValueError('NSIS compiler archive hash mismatch')
    directory = Path(tempfile.mkdtemp(prefix='nsis-verified-', dir=cache))
    with zipfile.ZipFile(archive) as package:
        for name in package.namelist():
            safe_archive_path(name)
        package.extractall(directory)
    relative = safe_archive_path(record['makensis_relative_path'])
    executable = directory.joinpath(*relative.parts)
    if not executable.is_file() or sha(executable) != record['makensis_sha256']:
        raise ValueError('NSIS compiler executable mismatch')
    version = subprocess.check_output([str(executable), '/NOCONFIG', '/VERSION'], text=True).strip()
    if version != 'v' + record['version']:
        raise ValueError('NSIS compiler version mismatch')
    return executable, record


def support_files(bundle, output):
    import html
    import shutil
    support = output / 'Support'
    support.mkdir(parents=True, exist_ok=True)
    extras = {'manifest.json': bundle / 'manifest.json'}
    for name in EXTRAS:
        source = bundle / name
        if not source.is_file() and name not in ('modified-source.zip', 'source-changes.patch'):
            source = REPO / name
        if not source.is_file():
            raise ValueError('Required source or license artifact missing: ' + name)
        extras[name] = source
    for name in DOCS:
        if not (HERE / name).is_file():
            raise ValueError('Required installer document missing: ' + name)
        extras[name] = HERE / name
    for name, source in extras.items():
        shutil.copy2(source, support / name)
    with zipfile.ZipFile(support / 'installer-source.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path in sorted(HERE.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                zipped.write(path, 'packaging/trail-installer/' + path.relative_to(HERE).as_posix())
    sections = [('Oink 许可证', 'LICENSE'), ('附加条款', 'LICENSE-ADDITIONAL-TERMS.md'),
                ('Microsoft WebView2 说明与隐私', 'WEBVIEW2-NOTICE.txt'),
                ('Microsoft WebView2 Runtime 许可', 'WebView2-LICENSE.txt'),
                ('NSIS 许可', 'NSIS-LICENSE.txt'), ('WiX Toolset 许可（应用 MSI）', 'WIX-LICENSE.txt')]
    introduction = ('Oink 指针尾迹增强版\n基于 Oink 0.3.4 的第三方修改版。\n\n'
                    'WebView2 仅在缺少时安装，适用微软许可。其 Microsoft Defender SmartScreen 功能可能向微软发送安全相关信息。\n'
                    '微软隐私声明：https://aka.ms/privacy\n'
                    'SmartScreen 说明：https://learn.microsoft.com/en-us/microsoft-edge/privacy-whitepaper#smartscreen\n\n')
    body = '<!doctype html><meta charset="utf-8"><title>Oink 许可与隐私</title>'
    body += '<style>body{font:16px system-ui;max-width:900px;margin:40px auto;padding:0 20px}pre{white-space:pre-wrap}details{margin:20px 0}</style>'
    body += '<pre>' + html.escape(introduction) + '</pre>'
    for title, name in sections:
        content = (support / name).read_text(encoding='utf-8-sig')
        body += '<details><summary>' + html.escape(title) + '</summary><pre>' + html.escape(content) + '</pre></details>'
    body += '<h2>源代码与说明</h2><ul>'
    for name in ['modified-source.zip', 'source-changes.patch', 'installer-source.zip', '使用说明.txt', 'NOTICE', 'THIRD_PARTY_LICENSES.md']:
        body += '<li><a href="' + html.escape(name, quote=True) + '">' + html.escape(name) + '</a></li>'
    body += '</ul><p>标准安装向导：NSIS Modern UI。完整应用包：WiX MSI。</p>'
    (support / 'license.html').write_text(body, encoding='utf-8')
    # This wizard page is shown only for missing WebView2. Keep its consent
    # specific to Microsoft's terms; all application/tool licenses remain above.
    runtime_terms = '\n\n'.join((support / name).read_text(encoding='utf-8-sig')
                                for name in ('WEBVIEW2-NOTICE.txt', 'WebView2-LICENSE.txt'))
    (support / 'license.txt').write_text(runtime_terms, encoding='utf-16')
    return support


def compile_installer(makensis, bundle, support, output, manifest, preview=False):
    executable = output / ('PointerTrail-Preview-NO-INSTALL.exe' if preview else 'PointerTrail-Setup.exe')
    values = {'BUNDLE_DIR': bundle, 'SUPPORT_DIR': support, 'OUTPUT_EXE': executable,
              'DISPLAY_VERSION': manifest['version'], 'MSI_VERSION': manifest['msi_version'],
              'PRODUCT_CODE': '{' + manifest['product_code'].strip('{}').upper() + '}',
              'APP_ICON': REPO / 'apps/oink/src-tauri/icons/icon.ico',
              'MSI_SHA256': manifest['files']['Oink.msi'], 'RUNTIME_SHA256': manifest['files'][RUNTIME]}
    defines = ['/D' + key + '=' + str(value) for key, value in values.items()]
    if preview:
        defines.append('/DQA_PREVIEW')
    command = [str(makensis), '/NOCONFIG', '/INPUTCHARSET', 'UTF8', '/V4', *defines, str(HERE / 'installer.nsi')]
    compiled = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace')
    diagnostics = compiled.stdout + compiled.stderr
    (output / 'makensis.log').write_text(diagnostics, encoding='utf-8')
    if compiled.returncode:
        print(compiled.stdout, file=sys.stderr)
        print(compiled.stderr, file=sys.stderr)
        raise RuntimeError('NSIS compilation failed; see makensis.log')
    warnings = [line for line in diagnostics.splitlines() if re.match(r'^\s*warning\b', line, re.IGNORECASE)]
    # Preview intentionally has unused mutation functions/variables. No other
    # warning (especially unknown variables/commands) is acceptable in either build.
    blocking = [line for line in warnings if not (preview and re.match(r'^\s*warning (6001|6010):', line))]
    if blocking:
        raise RuntimeError('NSIS compiler warning blocks release: ' + '\n'.join(blocking))
    executions = [line.strip() for line in diagnostics.splitlines() if re.match(r'^\s*Exec(?:Wait|Shell)?\s*:', line)]
    if preview and executions:
        raise ValueError('QA preview unexpectedly contains an executable launch')
    if not preview and (not executions or any(
            not line.startswith(('ExecWait: ""$SYSDIR\\msiexec.exe" ',
                                 'ExecWait: ""$PLUGINSDIR\\payload\\' + RUNTIME + '" '))
            for line in executions)):
        raise ValueError('Compiled installer contains an unexpected executable launch')
    if not executable.is_file():
        raise ValueError('NSIS compiler did not produce the expected executable')
    return executable


def main():
    from verify_installer import extract_and_verify, verify_runtime, verify_source
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tool-cache', type=Path, default=Path.home() / '.cache/oink-build')
    parser.add_argument('--sevenzip', type=Path)
    parser.add_argument('--preview-only', action='store_true', help='compile QA_PREVIEW with no install/uninstall execution')
    args = parser.parse_args()
    bundle, output = args.bundle.resolve(), args.output.resolve()
    if output.is_relative_to(REPO):
        parser.error('generated outputs must be outside the source repository')
    if output.exists() and any(output.iterdir()):
        parser.error('output must be empty to avoid mixing installer versions')
    manifest = verify_bundle(bundle)
    verify_runtime(bundle / 'payload' / RUNTIME)
    verify_source(bundle / 'modified-source.zip', manifest)
    output.mkdir(parents=True, exist_ok=True)
    support = support_files(bundle, output)
    makensis, tool = compiler(args.tool_cache.resolve())
    executable = compile_installer(makensis, bundle, support, output, manifest, args.preview_only)
    if args.preview_only:
        # QA binaries are deliberately distinct and never receive release metadata.
        print(json.dumps({'preview': str(executable), 'release_installer': False, 'no_installation_performed': True}))
        return
    verified, extracted, checks = extract_and_verify(executable, output, args.sevenzip)
    if verified != manifest:
        raise ValueError('Embedded manifest changed during compilation')
    record = {'schema': 1, 'kind': 'third-party-standard-nsis-installer', 'signed': False,
              'version': manifest['version'], 'build': manifest['build'], 'source_commit': manifest['source_commit'],
              'source_tree_sha256': manifest['source_tree_sha256'], 'msi_sha256': manifest['files']['Oink.msi'],
              'webview2_sha256': manifest['files'][RUNTIME], 'source_zip_sha256': sha(bundle / 'modified-source.zip'),
              'installer_sha256': sha(executable), 'installer_size': executable.stat().st_size,
              'compiler': {'name': 'NSIS', 'version': tool['version'], 'archive_sha256': tool['sha256'],
                           'makensis_sha256': tool['makensis_sha256']},
              'checks': checks, 'no_installation_performed': True}
    (output / 'installer-build.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'installer': str(executable), 'bytes': executable.stat().st_size,
                     'sha256': record['installer_sha256'], 'verified': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
