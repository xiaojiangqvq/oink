"""Repackage the tested app MSI with a tiny bootstrapper; export source separately."""
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
BUILD = 110
VERSION = '0.3.4-inhouse.110'
APPLICATION_COMMIT = 'c6d0ca0ae3ee629142bf39f7fbc7805caf6c8bb4'
APPLICATION_TREE = 'dd7c12c4bb7d3881ee4bdb608510882a9a8c570976bbc6debb78d6efeaf96064'
APPLICATION_MSI_SHA256 = 'bcdbbb44017817fc2966e3060dd174aac24a0faab1b4e55db8d0a37d3788553a'
APPLICATION_SOURCE_SHA256 = '11ea9f8409692bb9ee7b40a4c5f627f64e8f30fb036353d1c137a78fc458293a'
NOTICES = ('LICENSE', 'LICENSE-ADDITIONAL-TERMS.md', 'NOTICE',
           'THIRD_PARTY_LICENSES.md', 'third-party-licenses.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    application = parser.add_mutually_exclusive_group(required=True)
    application.add_argument('--package', type=Path, help='Original tested full MSI build directory')
    application.add_argument('--msi', type=Path, help='Exact tested MSI extracted from installer revision 1')
    parser.add_argument('--application-source', type=Path, required=True,
                        help='Exact corresponding source ZIP from the tested application release')
    parser.add_argument('--webview2-runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-inventory', type=Path)
    parser.add_argument('--source-patch', type=Path)
    args = parser.parse_args()
    output, runtime = args.output.resolve(), args.webview2_runtime.resolve()
    if output.is_relative_to(ROOT):
        parser.error('output must be outside the source repository')
    if output.exists() and any(output.iterdir()):
        parser.error('output must be empty to avoid mixing old packages')
    expected_code = str(uuid.uuid5(uuid.UUID(UPGRADE_CODE), 'pointer-trail-enhanced:' + str(BUILD))).upper()
    if args.package:
        package = args.package.resolve()
        release = json.loads((package / 'release.json').read_text(encoding='utf-8'))
    else:
        # The published revision-1 installer contains this exact MSI. Its hash
        # below binds this fixed identity before any packaging is permitted.
        source_msi = args.msi.resolve()
        package = source_msi.parent
        release = {'schema':1,'source_tree_sha256':APPLICATION_TREE,'source_commit':APPLICATION_COMMIT,
                   'version':VERSION,'build':BUILD,'architecture':'x64','product_code':expected_code,
                   'upgrade_code':UPGRADE_CODE,'msi_version':'0.0.110','update_test_feed':None,
                   'update_test_fail_health':False,'signing':'unsigned',
                   'artifacts':[{'name':source_msi.name,'sha256':APPLICATION_MSI_SHA256,'size':35104327}]}
    has_git = (ROOT / '.git').exists()
    inventory_path = args.source_inventory
    if not has_git and inventory_path is None:
        inventory_path = ROOT.parent / 'source-inventory.json'
    inventory = (json.loads(inventory_path.read_text(encoding='utf-8'))['files']
                 if inventory_path else source_inventory(ROOT))
    tree = source_tree_sha256(ROOT, inventory)
    if has_git:
        from versioning import local_source_commit
        installer_commit = local_source_commit(root=ROOT)
    else:
        installer_commit = (ROOT.parent / 'source-commit.txt').read_text(encoding='ascii').strip()
    if len(installer_commit) != 40 or any(c not in '0123456789abcdef' for c in installer_commit):
        raise ValueError('Full installer source commit is required')
    if (release.get('schema'),release.get('source_tree_sha256'),release.get('version'),release.get('build'),
        release.get('architecture'),release.get('product_code'),release.get('upgrade_code'),release.get('msi_version')) != (
            1,APPLICATION_TREE,VERSION,BUILD,'x64',expected_code,UPGRADE_CODE,'0.0.110'):
        raise ValueError('MSI release does not match the tested application identity/build')
    if (release.get('update_test_feed') is not None or release.get('update_test_fail_health') is not False or
            release.get('signing') != 'unsigned'):
        raise ValueError('unexpected test-only or signed package provenance')
    commit = release.get('source_commit','')
    if commit != APPLICATION_COMMIT:
        raise ValueError('MSI must come from the tested application commit')
    if digest(args.application_source) != APPLICATION_SOURCE_SHA256:
        raise ValueError('Application source archive differs from the tested release')
    from verify_installer import verify_source
    verify_source(args.application_source, release)
    artifacts = release.get('artifacts',[])
    if len(artifacts)!=1 or not artifacts[0]['name'].endswith('.msi') or Path(artifacts[0]['name']).name!=artifacts[0]['name']:
        raise ValueError('exactly one ordinary MSI artifact is required')
    msi = package / artifacts[0]['name']
    if (digest(msi) != APPLICATION_MSI_SHA256 or digest(msi)!=artifacts[0]['sha256']
            or msi.stat().st_size!=artifacts[0]['size']):
        raise ValueError('MSI artifact changed after packaging')
    runtime_record=json.loads((ROOT/'packaging/trail-installer/webview2-runtime.json').read_text(encoding='utf-8'))
    if runtime.stat().st_size!=runtime_record['size'] or digest(runtime)!=runtime_record['sha256']:
        raise ValueError('WebView2 bootstrapper differs from the pinned Microsoft download')
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
              'architecture':'x64','source_tree_sha256':APPLICATION_TREE,'source_commit':commit,
              'installer_revision':2,'installer_source_tree_sha256':tree,'installer_source_commit':installer_commit,
              'sources_embedded':False,'offline_runtime_included':False,
              'product_code':expected_code,'upgrade_code':UPGRADE_CODE,'msi_version':'0.0.110',
              'files':{'Oink.msi':digest(payload/'Oink.msi'),runtime_record['filename']:runtime_record['sha256']}}
    write_json(output/'manifest.json',manifest)
    for name in NOTICES:
        shutil.copy2(ROOT/name,output/name)
    if has_git:
        subprocess.run(['git','diff','--binary','--output='+str(output/'source-changes.patch'),BASE_COMMIT],cwd=ROOT,check=True)
    else:
        shutil.copy2(args.source_patch or ROOT.parent/'source-changes.patch',output/'source-changes.patch')
    shutil.copy2(args.application_source,output/'application-source.zip')
    snapshot={'schema':1,'source_tree_sha256':tree,'source_commit':installer_commit,'files':inventory}
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
        archive.writestr('source-commit.txt',installer_commit+'\n')
        archive.write(output/'source-changes.patch','source-changes.patch')
    write_json(output/'bundle-build.json',{'schema':1,'base_git_commit':BASE_COMMIT,'source_commit':commit,
        'source_tree_sha256':APPLICATION_TREE,
        'installer_source_commit':installer_commit,'installer_source_tree_sha256':tree,
        'source_zip_sha256':digest(output/'modified-source.zip'),
        'application_source_zip_sha256':digest(output/'application-source.zip'),
        'full_msi_sha256':digest(msi),'webview2_sha256':runtime_record['sha256'],
        'live_verification':'not_asserted_by_bundle_builder'})
    print(json.dumps({'bundle':str(output),'installer_source_tree_sha256':tree,
                      'installer_source_commit':installer_commit,'application_commit':commit,'build':BUILD}))


if __name__=='__main__':
    main()
