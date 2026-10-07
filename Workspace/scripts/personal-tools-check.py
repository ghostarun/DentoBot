#!/usr/bin/env python3
"""Read-only personal tooling check for ThinkStation P3 and Linux Legion only."""
import argparse, base64, json, os, re, shutil, subprocess, sys, urllib.request
from pathlib import Path

PCS = {"100.104.44.67": ("ThinkStation P3", "dentobot-b"), "100.95.7.78": ("Linux Legion", "dentobot-a")}
MIN_SWITCHER = (0, 7, 16)
MIN_T3 = (0, 0, 4503)
# This collector prints tool metadata only. Never include account credentials or histories.
COLLECTOR = r'''
import hashlib, json, os, re, subprocess, time
from pathlib import Path
h=Path.home()
def read(p):
 try: return json.loads(p.read_text())
 except (OSError,ValueError): return {}
routed=False
try:
 for line in (h/'.codex/config.toml').read_text().splitlines():
  line=line.strip()
  if line.startswith('['): break
  if re.match(r'openai_base_url\s*=\s*[\"\']http://(?:127\.0\.0\.1|localhost):18080/v1/?[\"\']',line): routed=True
except OSError: pass
root=h/'.local/opt/t3code-personal/current'
t3=root.resolve().name if root.exists() else None
activity_path=h/'.codex-switcher/two-pc-activity.json'
activity=read(activity_path)
fresh=activity_path.exists() and time.time()-activity_path.stat().st_mtime<=20
build=read(h/'.codex-switcher/installed-build.json')
local=activity.get('local',{}) if fresh else {}
running_t3=[]; t3_launcher_correct=False; switcher_running=False; running_hashes=set()
stale_codex_backends=[]
boot=time.time()-float(Path('/proc/uptime').read_text().split()[0])
def t3_owned(p):
 for _ in range(12):
  try:
   if '/t3code-personal/' in os.readlink(p/'exe'): return True
   parent=int((p/'stat').read_text().rsplit(')',1)[1].split()[1])
   if parent<=1: return False
   p=Path('/proc')/str(parent)
  except OSError: return False
 return False
for p in Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try:
  if p.stat().st_uid!=os.getuid(): continue
  exe=os.readlink(p/'exe')
  argv=(p/'cmdline').read_text().split('\0')
  if exe.removesuffix(' (deleted)').endswith('/codex') and 'app-server' in argv and t3_owned(p):
   env=dict(x.split('=',1) for x in (p/'environ').read_text().split('\0') if '=' in x)
   config=Path(env.get('CODEX_HOME',str(h/'.codex')))/'config.toml'
   launched=boot+int((p/'stat').read_text().rsplit(')',1)[1].split()[19])/os.sysconf('SC_CLK_TCK')
   explicit=env.get('OPENAI_BASE_URL') in ('http://127.0.0.1:18080/v1','http://localhost:18080/v1')
   # A file changed after spawn cannot establish the running runtime's route.
   # Custom/managed launch overrides also need independent verification.
   custom=(bool(env.get('OPENAI_BASE_URL')) and not explicit) or any('model_provider=' in a or 'openai_base_url=' in a for a in argv)
   if custom or (not explicit and (config!=h/'.codex/config.toml' or not config.exists() or launched<config.stat().st_mtime)):
    stale_codex_backends.append(int(p.name))
  if exe.removesuffix(' (deleted)').endswith('/codex-switcher'):
   switcher_running=True
   if build.get('sha256'):
    with (p/'exe').open('rb') as f:
     digest=hashlib.sha256()
     for block in iter(lambda:f.read(1024*1024),b''): digest.update(block)
     running_hashes.add(digest.hexdigest())
  match=re.search(r'/t3code-personal/([^/]+)/squashfs-root/t3code$',exe)
  if match:
   running_t3.append(match.group(1))
   env=dict(x.split('=',1) for x in (p/'environ').read_text().split('\0') if '=' in x)
   if env.get('T3CODE_SWITCHER_LAUNCHER')==str(h/'.local/bin/codex-switcher'):t3_launcher_correct=True
 except OSError: pass
print(json.dumps({'t3':t3,'t3_running':sorted(set(running_t3)),'t3_launcher_correct':t3_launcher_correct,
 'switcher':local.get('switcher_version') or build.get('version'),
 'switcher_running':switcher_running,'proxy_running':local.get('proxy_running',False),'switcher_installed':build.get('version'),
 'switcher_binary_matches':running_hashes=={build['sha256']} if switcher_running and build.get('sha256') else None,
 'codex_proxy_routed':routed,'codex_backends_need_restart_or_verification':stale_codex_backends,
 'pair_connected':bool(activity.get('peer')) if fresh else False,'protocol':local.get('protocol_version') or build.get('protocol_version'),
 'pair_enabled':activity.get('enabled',False) if fresh else None,
 'peer_ip':activity.get('peer_ip') if fresh else None,'activity_fresh':fresh}))
'''

def version(v):
    m=re.match(r"^(\d+)\.(\d+)\.(\d+)",v or "")
    return tuple(map(int,m.groups())) if m else None

def collect(command):
    p=subprocess.run(command,input=COLLECTOR,text=True,capture_output=True,timeout=15)
    if p.returncode: raise RuntimeError(p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'collection failed')
    return json.loads(p.stdout)

def latest():
    urls={"t3":"https://api.github.com/repos/ghostarun/t3code-personal/releases/latest",
          "switcher":"https://raw.githubusercontent.com/ghostarun/codex-switcher-personal/main/package.json"}
    out={}
    for name,url in urls.items():
        try:
            if shutil.which('gh'):
                endpoint='repos/ghostarun/codex-switcher-personal/contents/package.json' if name=='switcher' else 'repos/ghostarun/t3code-personal/releases/latest'
                r=subprocess.run(['gh','api',endpoint],capture_output=True,text=True,timeout=10,check=True)
                meta=json.loads(r.stdout)
                out[name]=json.loads(base64.b64decode(meta['content']))['version'] if name=='switcher' else meta['tag_name'].removeprefix('v')
                continue
            req=urllib.request.Request(url,headers={'User-Agent':'dentobot-personal-tools-check'})
            with urllib.request.urlopen(req,timeout=8) as r: d=json.load(r)
            out[name]=(d['tag_name'].removeprefix('v') if name=='t3' else d['version'])
        except Exception as e: out[name]=None; print(f"Latest {name}: unavailable ({type(e).__name__}); update status is unknown")
    return out

def evaluate(nodes, releases=None):
    problems=[]
    if releases is not None:
        for tool, value in releases.items():
            if value is None: problems.append(f'Latest {tool} version could not be verified')
    for ip,(label,_) in PCS.items():
        n=nodes.get(ip)
        if not n: problems.append(label+': unavailable; compatibility is unverified'); continue
        print(f"{label}: T3 Personal {n.get('t3') or 'unknown'}; Switcher {n.get('switcher') or 'unknown'}; pairing protocol {n.get('protocol') or 'unknown'}")
        if version(n.get('t3')) is None or version(n.get('t3'))<MIN_T3: problems.append(label+': update/install T3 Personal (minimum 0.0.4503)')
        if version(n.get('switcher')) is None or version(n.get('switcher'))<MIN_SWITCHER or n.get('protocol')!=1:
            problems.append(label+': install the Switcher two-PC build (minimum 0.7.16, protocol 1)')
        if n.get('t3_running') and not n.get('t3_launcher_correct'): problems.append(label+': T3 uses the old Switcher launcher; repair the personal launcher and restart T3 after handoff')
        if n.get('t3_running') and n['t3_running']!=[n.get('t3')]: problems.append(label+': restart T3 when work is safe; running and installed versions differ')
        if not n.get('activity_fresh') or not n.get('pair_enabled'): problems.append(label+': start Switcher and enable pairing; activity is unavailable')
        expected=next(p for p in PCS if p!=ip)
        if not n.get('peer_ip'): problems.append(label+': pairing peer is not configured')
        elif n['peer_ip']!=expected: problems.append(label+': pairing points outside the two approved PCs')
        if not n.get('codex_proxy_routed'): problems.append(label+': new Codex threads bypass Switcher; restore the local proxy setting after the model-list test')
        if n.get('codex_backends_need_restart_or_verification'): problems.append(label+': running T3 Codex backends predate routing changes or use custom settings; restart/resume after safe handoff and verify the effective proxy route')
        if not n.get('switcher_running') or not n.get('proxy_running'): problems.append(label+': Switcher proxy is stopped; account activity is unverified')
        if n.get('switcher_binary_matches') is False: problems.append(label+': running Switcher differs from the installed build; restart after safe handoff')
        if not n.get('pair_connected'): problems.append(label+': authenticated peer activity is unavailable; verify matching secrets and port 18082')
        for tool in ['t3','switcher']:
            wanted=version((releases or {}).get(tool)); current=version(n.get(tool))
            if wanted and current and current<wanted: problems.append(label+f': {tool} update available ({releases[tool]})')
    available=[n for n in nodes.values() if n]
    if len(available)==2:
        for tool in ['t3','switcher']:
            if available[0].get(tool)!=available[1].get(tool): problems.append(f'{tool} versions differ between the two PCs; align before handoff')
    return problems

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--latest',action='store_true',help='also check the personal GitHub repositories for newer versions')
    p.add_argument('--json',action='store_true',help='emit sanitized installed-state JSON instead of the report')
    a=p.parse_args()
    try:
        ts=json.loads(subprocess.check_output(['tailscale','status','--json'],text=True,timeout=5))
        ips=ts.get('Self',{}).get('TailscaleIPs',[])
        own=next((ip for ip in ips if ip in PCS),None)
        if not own or ts.get('Self',{}).get('OS')!='linux':
            print('This check is only for ThinkStation P3 and Linux Legion, using their approved Linux Tailscale identities.',file=sys.stderr)
            return 2
        nodes={own:collect([sys.executable,'-'])}
        other=next(ip for ip in PCS if ip!=own)
        online=any(other in n.get('TailscaleIPs',[]) and n.get('Online') and n.get('OS')=='linux' for n in ts.get('Peer',{}).values())
        if online:
            # The fixed SSH alias supplies its existing user/key; do not probe unrelated PCs.
            try: nodes[other]=collect(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','HostName='+other,PCS[other][1],'python3','-'])
            except (RuntimeError,subprocess.TimeoutExpired,ValueError) as e:
                print(f"{PCS[other][0]}: SSH check unavailable ({e})",file=sys.stderr); nodes[other]=None
        else: nodes[other]=None
        if a.json: print(json.dumps(nodes,indent=2)); return 0
        releases=latest() if a.latest else None
        problems=evaluate(nodes,releases)
        if problems:
            print('\nAction needed:')
            for issue in problems: print('  - '+issue)
            print('\nT3 update: t3code --update (restart separately after safe handoff).')
            print('Switcher update: install the same reviewed personal two-PC build on both PCs, then restart after safe handoff.')
            return 1
        print('\nPASS: both personal PCs have matching supported tooling and fresh pairing activity.')
        return 0
    except (OSError,ValueError,subprocess.SubprocessError) as e:
        print(f'Personal tools check unavailable: {e}',file=sys.stderr); return 2
if __name__=='__main__': sys.exit(main())
