"""Prepare a full Windows installer bundle from a verified MSI; never install."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build-support'))
from provenance import EXCLUDED, source_inventory, source_tree_sha256

BASE_COMMIT = 'ec2fd6ae9ec8d1a55e024aed661a022a9960c337'
UPGRADE_CODE = '4D39E4BE-6792-4CD6-B344-A5E95A270EA6'
BUILD = 109
VERSION = '0.3.4-inhouse.109'
NOTICES = ('LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE',
           'THIRD_PARTY_LICENSES.md', 'third-party-licenses.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--webview2-runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-inventory', type=Path)
    parser.add_argument('--source-patch', type=Path)
    args = parser.parse_args()
    package, output, runtime = args.package.resolve(), args.output.resolve(), args.webview2_runtime.resolve()
    if output.is_relative_to(ROOT):
        parser.error('output must be outside the source repository')
    if output.exists() and any(output.iterdir()):
        parser.error('output must be empty to avoid mixing old packages')
    release = json.loads((package / 'release.json').read_text(encoding='utf-8'))
    has_git = (ROOT / '.git').exists()
    inventory_path = args.source_inventory
    if not has_git and inventory_path is None:
        inventory_path = ROOT.parent / 'source-inventory.json'
    inventory = (json.loads(inventory_path.read_text(encoding='utf-8'))['files']
                 if inventory_path else source_inventory(ROOT))
    tree = source_tree_sha256(ROOT, inventory)
    expected_code = str(uuid.uuid5(uuid.UUID(UPGRADE_CODE), 'pointer-trail-enhanced:' + str(BUILD))).upper()
    if (release.get('schema'),release.get('source_tree_sha256'),release.get('version'),release.get('build'),
        release.get('architecture'),release.get('product_code'),release.get('upgrade_code'),release.get('msi_version')) != (
            1,tree,VERSION,BUILD,'x64',expected_code,UPGRADE_CODE,'0.0.109'):
        raise ValueError('MSI release does not match the current source/fork identity/build')
    if (release.get('update_test_feed') is not None or release.get('update_test_fail_health') is not False or
            release.get('signing') != 'unsigned'):
        raise ValueError('unexpected test-only or signed package provenance')
    commit = release.get('source_commit','')
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('full source commit is required')
    if has_git and subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=commit:
        raise ValueError('MSI source commit differs from checkout HEAD')
    artifacts = release.get('artifacts',[])
    if len(artifacts)!=1 or not artifacts[0]['name'].endswith('.msi') or Path(artifacts[0]['name']).name!=artifacts[0]['name']:
        raise ValueError('exactly one ordinary MSI artifact is required')
    msi = package / artifacts[0]['name']
    if digest(msi)!=artifacts[0]['sha256'] or msi.stat().st_size!=artifacts[0]['size']:
        raise ValueError('MSI artifact changed after packaging')
    runtime_record=json.loads((ROOT/'packaging/trail-installer/webview2-runtime.json').read_text(encoding='utf-8'))
    if runtime.stat().st_size!=runtime_record['size'] or digest(runtime)!=runtime_record['sha256']:
        raise ValueError('WebView2 runtime differs from the pinned Microsoft download')
    if has_git:
        tracked={raw.decode('utf-8') for raw in subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).split(b'\0') if raw}
    else:
        tracked={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()
                 and not any(part in EXCLUDED for part in p.relative_to(ROOT).parts)}
    missing={entry['path'] for entry in inventory}-tracked
    if missing:
        raise ValueError('add new source files to Git before packaging: '+', '.join(sorted(missing)))
    payload=output/'payload';payload.mkdir(parents=True)
    shutil.copy2(msi,payload/'Oink.msi')
    shutil.copy2(runtime,payload/runtime_record['filename'])
    manifest={'schema':1,'kind':'third-party-oink-full-installer','version':VERSION,'build':BUILD,
              'architecture':'x64','source_tree_sha256':tree,'source_commit':commit,
              'product_code':expected_code,'upgrade_code':UPGRADE_CODE,'msi_version':'0.0.109',
              'files':{'Oink.msi':digest(payload/'Oink.msi'),runtime_record['filename']:runtime_record['sha256']}}
    write_json(output/'manifest.json',manifest)
    for name in NOTICES:
        shutil.copy2(ROOT/name,output/name)
    if has_git:
        subprocess.run(['git','diff','--binary','--output='+str(output/'source-changes.patch'),BASE_COMMIT],cwd=ROOT,check=True)
    else:
        shutil.copy2(args.source_patch or ROOT.parent/'source-changes.patch',output/'source-changes.patch')
    snapshot={'schema':1,'source_tree_sha256':tree,'source_commit':commit,'files':inventory}
    modes={entry['path']:entry['mode'] for entry in inventory}
    with zipfile.ZipFile(output/'modified-source.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted(tracked):
            path=ROOT/name
            if not path.is_file():continue
            info=zipfile.ZipInfo.from_file(path,'pointer-trail-enhanced/'+name)
            info.create_system=3;info.external_attr=int(modes.get(name,'100644'),8)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,path.read_bytes())
        archive.writestr('source-inventory.json',json.dumps(snapshot,indent=2)+'\n')
        archive.writestr('source-commit.txt',commit+'\n')
        archive.write(output/'source-changes.patch','source-changes.patch')
    write_json(output/'bundle-build.json',{'schema':1,'base_git_commit':BASE_COMMIT,'source_commit':commit,
        'source_tree_sha256':tree,'source_zip_sha256':digest(output/'modified-source.zip'),
        'full_msi_sha256':digest(msi),'webview2_sha256':runtime_record['sha256'],
        'live_verification':'not_asserted_by_bundle_builder'})
    print(json.dumps({'bundle':str(output),'source_tree_sha256':tree,'source_commit':commit,'build':BUILD}))


if __name__=='__main__':
    main()
