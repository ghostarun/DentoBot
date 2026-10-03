"""Host-only checks for the workspace-root and app-menu launch shortcuts."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Workspace/scripts'
INSTALLER = SCRIPTS / 'install-desktop-launcher.bash'


def _workspace(tmp_path):
    workspace = tmp_path / 'ws'
    workspace.mkdir()
    (workspace / 'scripts').symlink_to(SCRIPTS)
    return workspace


def _run(args, tmp_path, workspace):
    env = {**os.environ, 'HOME': str(tmp_path / 'home'), 'XDG_DATA_HOME': str(tmp_path / 'data'),
           'DENTOBOT_WORKSPACE_ROOT': str(workspace)}
    return subprocess.run(['bash', str(INSTALLER), *args], env=env, capture_output=True,
                          text=True, timeout=10, stdin=subprocess.DEVNULL)


def test_installer_writes_entry_that_follows_workspace_scripts_link(tmp_path):
    if Path('/dev/dxg').exists() or Path('/mnt/wslg').is_dir():
        return
    workspace = _workspace(tmp_path)
    result = _run([], tmp_path, workspace)
    assert result.returncode == 0, result.stderr
    desktop = tmp_path / 'data/applications/dentobot-workflow.desktop'
    text = desktop.read_text()
    assert f'Exec="{workspace}/scripts/launch-dentobot-desktop.bash"' in text
    assert 'Terminal=true' in text and 'Name=DENTO Workflow' in text
    assert f'Icon={ROOT}/DentalDrillNav.png' in text and (ROOT / 'DentalDrillNav.png').is_file()
    removed = _run(['--remove'], tmp_path, workspace)
    assert removed.returncode == 0 and not desktop.exists()


def test_installer_refuses_missing_workspace_link(tmp_path):
    if Path('/dev/dxg').exists() or Path('/mnt/wslg').is_dir():
        return
    workspace = tmp_path / 'ws'
    workspace.mkdir()
    result = _run([], tmp_path, workspace)
    assert result.returncode == 2 and 'Workspace launcher is missing' in result.stderr
    assert 'WSL host' in INSTALLER.read_text()


def test_desktop_wrapper_runs_launcher_and_reports_status(tmp_path):
    workspace = _workspace(tmp_path)
    result = subprocess.run(['bash', str(workspace / 'scripts/launch-dentobot-desktop.bash'), '--help'],
                            capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    assert result.returncode == 0, result.stderr
    assert 'Usage: scripts/launch-dentoworkflow.bash' in result.stdout
    assert 'launcher exited with status 0' in result.stdout
    assert 'Press Enter' not in result.stdout


def test_bootstrap_links_root_launch_command_through_scripts():
    bootstrap = (ROOT / 'Workspace/bootstrap-workspace.bash').read_text()
    assert 'install_link "${workspace_root}/launch-dentobot" \\\n  "scripts/launch-dentoworkflow.bash"' in bootstrap
    assert bootstrap.index('"${workspace_root}/scripts"') < bootstrap.index('"${workspace_root}/launch-dentobot"')
