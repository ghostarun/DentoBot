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


def test_launcher_summary_names_source_checkout_branch_and_commit(tmp_path):
    launcher = (SCRIPTS / 'launch-dentoworkflow.bash').read_text()
    start = launcher.index('git_source_identity() {')
    function = launcher[start:launcher.index('\n}\n', start) + 3]
    assert '"Source checkout: $(git_source_identity "${repository_root}")"' in launcher
    assert 'SlicerROS2 source: $(git_source_identity "${ros2_workspace_root}/src/slicer_ros2_module")' in launcher
    repo = tmp_path / 'repo'
    repo.mkdir()
    git = ['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid']
    subprocess.run([*git, 'init', '-q', '-b', 'demo'], check=True)
    subprocess.run([*git, 'commit', '-q', '--allow-empty', '-m', 'c'], check=True)
    (repo / 'edited.txt').write_text('x')
    commit = subprocess.run([*git, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    script = 'set -euo pipefail\n' + function + f'git_source_identity {repo}; echo; git_source_identity {tmp_path / "none"}'
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [f'{repo} (demo @ {commit}, 1 uncommitted)',
                                          f'{tmp_path / "none"} (not a git checkout)']


def _checkout_fixture(tmp_path):
    ros2 = tmp_path / 'ws/ros2_ws'
    current = ros2 / 'src/DentoBot'
    current.mkdir(parents=True)

    def git(repo, *args, date=None):
        env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
               'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'}
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(['git', '-C', str(repo), *args], check=True, env=env, capture_output=True)

    git(current, 'init', '-q', '-b', 'main')
    (current / 'Workspace/scripts').mkdir(parents=True)
    (current / 'Workspace/scripts/launch-dentoworkflow.bash').write_text('echo stub\n')
    git(current, 'add', '-A')
    git(current, 'commit', '-q', '-m', 'Older main work', date='2026-09-01T10:00:00+00:00')
    newer = ros2 / 'src/DentoBot-feature'
    git(current, 'worktree', 'add', '-q', '-b', 'feature/new', str(newer))
    git(newer, 'commit', '-q', '--allow-empty', '-m', 'Newest feature work', date='2026-10-02T09:30:00+00:00')
    outside = tmp_path / 'outside'
    git(current, 'worktree', 'add', '-q', '-b', 'scratch', str(outside))
    (current / 'BRANCH_OBSOLETE.md').write_text('retired\n')
    return ros2, current, newer, outside


def _chooser_block():
    launcher = (SCRIPTS / 'launch-dentoworkflow.bash').read_text()
    start = launcher.index('# --- checkout selection and shared build hygiene ---')
    return launcher[start:launcher.index('# --- end checkout selection ---', start)]


def _select(ros2, current, answer):
    script = (f'set -euo pipefail\nrepository_root={current}\nros2_workspace_root={ros2}\n'
              + _chooser_block() + 'select_checkout\necho "selected=${selected_checkout}"')
    return subprocess.run(['bash', '-c', script], input=answer, capture_output=True, text=True, timeout=30)


def test_choose_checkout_lists_main_first_then_newest_and_runs_chosen(tmp_path):
    ros2, current, newer, outside = _checkout_fixture(tmp_path)
    result = _select(ros2, current, '2\n')
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[1] == '  (origin not reachable; showing the last fetched main)'
    assert lines[3].startswith('  1) main [current] [retired]')
    assert 'Older main work' in lines[4] and '2026-09-01' in lines[4]
    assert lines[6] == '  2) feature/new' and str(outside) not in result.stdout
    assert 'Newest feature work' in lines[7] and '2026-10-02' in lines[7]
    assert lines[-1] == f'selected={newer}'
    assert _select(ros2, current, '\n').stdout.splitlines()[-1] == f'selected={current}'
    assert _select(ros2, current, '1\n').stdout.splitlines()[-1] == f'selected={current}'


def _git(repo, *args):
    env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'}
    return subprocess.run(['git', '-C', str(repo), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def _origin_fixture(tmp_path):
    """origin/main is one commit ahead of local main; the current checkout is on 'work'."""
    origin = tmp_path / 'origin.git'
    _git(tmp_path, 'init', '-q', '--bare', '-b', 'main', str(origin))
    ros2 = tmp_path / 'ws/ros2_ws'
    current = ros2 / 'src/DentoBot'
    current.parent.mkdir(parents=True)
    _git(tmp_path, 'clone', '-q', str(origin), str(current))
    (current / 'Workspace/scripts').mkdir(parents=True)
    (current / 'Workspace/scripts/launch-dentoworkflow.bash').write_text('echo stub\n')
    _git(current, 'add', '-A')
    _git(current, 'commit', '-q', '-m', 'Released main')
    _git(current, 'push', '-q', 'origin', 'main')
    old_main = _git(current, 'rev-parse', 'HEAD')
    _git(current, 'switch', '-q', '-c', 'work')
    pusher = tmp_path / 'pusher'
    _git(tmp_path, 'clone', '-q', str(origin), str(pusher))
    _git(pusher, 'commit', '-q', '--allow-empty', '-m', 'Newer main on GitHub')
    _git(pusher, 'push', '-q', 'origin', 'main')
    return ros2, current, old_main, _git(pusher, 'rev-parse', 'HEAD')


def test_choose_main_creates_main_checkout_at_github_main(tmp_path):
    ros2, current, _old_main, new_main = _origin_fixture(tmp_path)
    result = _select(ros2, current, '1\n')
    assert result.returncode == 0, result.stderr
    main_checkout = ros2 / 'src/DentoBot-main'
    assert '  1) main [not checked out yet]' in result.stdout
    assert 'Newer main on GitHub' in result.stdout
    assert f'will be created at {main_checkout}' in result.stdout
    assert result.stdout.splitlines()[-1] == f'selected={main_checkout}'
    assert _git(main_checkout, 'rev-parse', 'HEAD') == new_main
    assert _git(main_checkout, 'rev-parse', '--abbrev-ref', 'HEAD') == 'main'


def test_choose_main_updates_clean_checkout_and_keeps_dirty_one(tmp_path):
    ros2, current, old_main, new_main = _origin_fixture(tmp_path)
    main_checkout = ros2 / 'src/DentoBot-main'
    _git(current, 'worktree', 'add', '-q', str(main_checkout), 'main')
    (main_checkout / 'notes.txt').write_text('local edit\n')
    result = _select(ros2, current, '1\n')
    assert '[1 uncommitted] [1 behind GitHub main; updated on launch]' in result.stdout
    assert 'main checkout has uncommitted changes; running it without updating.' in result.stdout
    assert _git(main_checkout, 'rev-parse', 'HEAD') == old_main
    (main_checkout / 'notes.txt').unlink()
    result = _select(ros2, current, '1\n')
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == f'selected={main_checkout}'
    assert _git(main_checkout, 'rev-parse', 'HEAD') == new_main


def test_stale_package_build_from_another_checkout_is_cleared(tmp_path):
    ros2 = tmp_path / 'ws/ros2_ws'
    chosen = ros2 / 'src/DentoBot'
    for package in ('dentobot_description', 'dentobot_moveit_config'):
        (chosen / package).mkdir(parents=True)
        (ros2 / 'install' / package).mkdir(parents=True)
        (ros2 / 'build' / package).mkdir(parents=True)
    (ros2 / 'src/dentobot_description').symlink_to('DentoBot/dentobot_description')
    (ros2 / 'build/dentobot_description/CMakeCache.txt').write_text(
        'CMAKE_HOME_DIRECTORY:INTERNAL=/workspace/ros2_ws/src/dentobot_description\n')
    (ros2 / 'build/dentobot_moveit_config/CMakeCache.txt').write_text(
        'CMAKE_HOME_DIRECTORY:INTERNAL=/workspace/ros2_ws/src/Other/dentobot_moveit_config\n')
    script = (f'set -euo pipefail\nrepository_root={chosen}\nros2_workspace_root={ros2}\n'
              + _chooser_block() + f'clear_stale_package_builds {chosen}')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        f'Rebuilding dentobot_moveit_config from {chosen} (its build came from '
        f'{ros2}/src/Other/dentobot_moveit_config).']
    assert (ros2 / 'build/dentobot_description').is_dir()
    assert (ros2 / 'install/dentobot_description').is_dir()
    assert not (ros2 / 'build/dentobot_moveit_config').exists()
    assert not (ros2 / 'install/dentobot_moveit_config').exists()


def test_launch_stops_on_build_failure_and_clears_stale_builds_first():
    launcher = (SCRIPTS / 'launch-dentoworkflow.bash').read_text()
    build = launcher.index('colcon build --symlink-install')
    guard = launcher.rindex('clear_stale_package_builds "${repository_root}"', 0, build)
    block = launcher[guard:build]
    assert block.count('docker exec') == 1
    assert '  set -euo pipefail\n  set +u\n  source /opt/ros/jazzy/setup.bash' in block
    choose = launcher.index('clear_stale_package_builds "${selected_checkout}"')
    assert choose < launcher.index('exec bash "${selected_checkout}/Workspace/scripts/launch-dentoworkflow.bash"')


def test_choose_checkout_rejects_bad_or_missing_choice(tmp_path):
    ros2, current, _newer, _outside = _checkout_fixture(tmp_path)
    for answer, message in (('9\n', 'Not a listed checkout number'), ('x\n', 'Not a listed checkout number'),
                            ('', 'No checkout chosen')):
        result = _select(ros2, current, answer)
        assert result.returncode == 2 and message in result.stderr


def test_choose_checkout_is_opt_in_and_forwards_other_options():
    launcher = (SCRIPTS / 'launch-dentoworkflow.bash').read_text()
    assert 'choose_checkout=false' in launcher
    assert '    --choose-checkout)\n      choose_checkout=true' in launcher
    assert ('exec bash "${selected_checkout}/Workspace/scripts/launch-dentoworkflow.bash" '
            '"${forward_args[@]}"') in launcher
    start = launcher.index('forward_args=()')
    block = launcher[start:launcher.index('\ndone', start) + 5]
    result = subprocess.run(['bash', '-c', 'set -euo pipefail\nset -- --render-probe c.dentocase '
                             '--choose-checkout --check-only\n' + block + '\nprintf "%s\\n" "${forward_args[@]}"'],
                            capture_output=True, text=True, timeout=10)
    assert result.stdout.splitlines() == ['--render-probe', 'c.dentocase', '--check-only']
    desktop = (SCRIPTS / 'install-desktop-launcher.bash').read_text()
    assert 'Exec="${entry}" --choose-checkout' in desktop
