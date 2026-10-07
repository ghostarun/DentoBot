"""Checksum-verified exchange of one explicitly selected saved case."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import uuid

import handoff


def sync_case(source, destination, relative, replace=False):
    relative = PurePosixPath(relative)
    if relative.is_absolute() or '..' in relative.parts or relative.suffix != '.dentocase':
        raise RuntimeError('select one data-relative .dentocase path without ..')
    root = Path(source.repo).parents[2] / 'data'
    case = root / str(relative)
    try:
        case.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError('case path escapes workspace/data') from exc
    if source.host is not None or not case.is_file():
        raise RuntimeError('run sync-case on the machine containing the saved file')
    def digest():
        h = hashlib.sha256()
        with case.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
        return h.hexdigest()
    expected = digest()
    target_root = str(Path(destination.repo).parents[2] / 'data')
    token = uuid.uuid4().hex
    prepare = '''import pathlib,sys
root=pathlib.Path(sys.argv[1]).resolve();target=root/sys.argv[2]
target.resolve().relative_to(root)
target.parent.mkdir(parents=True,exist_ok=True)
print(str(target.with_name('.'+target.name+'.'+sys.argv[3]+'.part')))
'''
    staging = destination.run(['python3', '-c', prepare, target_root, str(relative), token]).strip()
    remote = (destination.host + ':' + shlex.quote(staging)) if destination.host else staging
    argv = ['rsync', '-a', '--checksum']
    if destination.host: argv += ['-e', shlex.join(['ssh', *handoff.SSH_OPTIONS])]
    result = subprocess.run([*argv, '--', str(case), remote], capture_output=True, text=True, timeout=900)
    if result.returncode or digest() != expected:
        raise RuntimeError('case transfer failed or source changed; destination was not replaced')
    finish = '''import hashlib,json,os,pathlib,sys
root=pathlib.Path(sys.argv[1]).resolve();target=root/sys.argv[2]
target.resolve().relative_to(root)
staging=target.with_name('.'+target.name+'.'+sys.argv[3]+'.part')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
if sha(staging)!=sys.argv[4]:raise SystemExit('received checksum differs; destination preserved')
backup=None
if target.exists():
 if sha(target)==sys.argv[4]:
  staging.unlink();print(json.dumps({'sha256':sys.argv[4],'path':str(target),'already_identical':True}));raise SystemExit(0)
 if sys.argv[5]!='replace':raise SystemExit('different destination exists; use --replace to retain a backup and update')
 backup=target.with_name(target.name+'.before-handoff-'+sys.argv[3]);os.rename(target,backup)
os.replace(staging,target)
print(json.dumps({'sha256':sys.argv[4],'path':str(target),'backup':str(backup) if backup else None,'already_identical':False}))
'''
    return json.loads(destination.run(['python3', '-c', finish, target_root, str(relative), token, expected, 'replace' if replace else 'preserve']))
