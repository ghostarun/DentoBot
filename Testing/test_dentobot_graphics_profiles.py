"""Host-only profile checks: execute launcher branches with stubbed GPU/Docker commands."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / 'Workspace/scripts/launch-dentoworkflow.bash').read_text()


def _shell(script, env=None):
    return subprocess.run(['/bin/bash', '-c', 'set -euo pipefail\n' + script],
                          env={**os.environ, **(env or {})}, capture_output=True,
                          text=True, timeout=5)


def _stub_commands(tmp_path, *, smi='GPU stub, 580, 8192 MiB', runtime='nvidia', fail=''):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    commands = {
        'timeout': 'shift; exec "$@"',
        'docker': '[[ ${STUB_FAIL:-} != docker ]] || exit 1\nprintf "%s\\n" "$STUB_RUNTIME"',
        'nvidia-smi': '[[ ${STUB_FAIL:-} != driver ]] || exit 1\nprintf "%s\\n" "$STUB_SMI"',
    }
    for name, body in commands.items():
        path = bindir / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)
    (bindir / 'grep').symlink_to('/usr/bin/grep')
    return {'PATH': str(bindir), 'STUB_SMI': smi, 'STUB_RUNTIME': runtime, 'STUB_FAIL': fail}


@pytest.mark.parametrize('graphics,backend,overlays', [
    ('mesa', 'cpu', []), ('mesa', 'cuda:0', ['cuda']),
    ('nvidia', 'cpu', ['nvidia', 'cuda']), ('nvidia', 'cuda:0', ['nvidia', 'cuda']),
    ('wslg', 'cpu', ['wslg']),
])
def test_compose_selection(graphics, backend, overlays):
    start = LAUNCHER.index('compose_command=(')
    end = LAUNCHER.index('# compose.yaml still interpolates', start)
    selected_root = '/checkout-under-test'
    setup = f'''workspace_root=/workspace
compose_file={selected_root}/Workspace/compose.yaml
compose_wslg_file={selected_root}/Workspace/compose.wslg.yaml
compose_nvidia_file={selected_root}/Workspace/compose.nvidia.yaml
compose_cuda_file={selected_root}/Workspace/compose.cuda.yaml
compose_override_file=/missing-test-override
graphics_mode={graphics}
backend_device={backend}
'''
    result = _shell(setup + LAUNCHER[start:end] + '\nprintf "%s\\n" "${compose_command[@]}"')
    assert result.returncode == 0, result.stderr
    args = result.stdout.splitlines()
    actual = [arg for arg in args if arg.endswith('.yaml')]
    assert actual == [f'{selected_root}/Workspace/compose.yaml'] + [
        f'{selected_root}/Workspace/compose.{name}.yaml' for name in overlays]


@pytest.mark.parametrize('failure,expected', [
    ('missing', 'requires the host nvidia-smi'),
    ('driver', 'Host NVIDIA driver is unavailable'),
    ('docker', 'Could not read Docker runtimes'),
    ('runtime', 'Docker does not list the NVIDIA runtime'),
    ('', 'Host NVIDIA GPUs'),
])
def test_host_prerequisites(tmp_path, failure, expected):
    env = _stub_commands(tmp_path, runtime='runc' if failure == 'runtime' else 'nvidia', fail=failure)
    if failure == 'missing':
        (tmp_path / 'bin/nvidia-smi').unlink()
    start = LAUNCHER.index('check_nvidia_graphics_prerequisites() {')
    end = LAUNCHER.index('\n}\n', start) + 3
    result = _shell(LAUNCHER[start:end] + '\ncheck_nvidia_graphics_prerequisites', env)
    assert result.returncode == (2 if failure else 0), result.stderr
    assert expected in result.stdout + result.stderr


@pytest.mark.parametrize('visible', [True, False])
def test_container_device_visibility(tmp_path, visible):
    env = _stub_commands(tmp_path, runtime='GPU 0: stub' if visible else '', fail='')
    start = LAUNCHER.index('if [[ ${graphics_mode} == "nvidia" ]]; then\n  if ! container_nvidia_devices=')
    end = LAUNCHER.index('\ncontainer_runtime_user=', start)
    result = _shell('graphics_mode=nvidia\ncontainer_name=stub\n' + LAUNCHER[start:end], env)
    assert result.returncode == (0 if visible else 2), result.stderr
    assert ('does not verify Slicer OpenGL acceleration' if visible else 'cannot access a GPU') in result.stdout + result.stderr


def test_profile_contract_and_selected_checkout():
    nvidia = (ROOT / 'Workspace/compose.nvidia.yaml').read_text()
    cuda = (ROOT / 'Workspace/compose.cuda.yaml').read_text()
    assert 'devices: !reset []' in nvidia
    assert 'NVIDIA_DRIVER_CAPABILITIES: compute,utility,graphics,display' in cuda
    assert 'driver: nvidia' in cuda and 'capabilities: [gpu]' in cuda
    assert '${backend_device} == "cuda:0" || ${graphics_mode} == "nvidia"' in LAUNCHER
    assert 'container_repository_root="/workspace/ros2_ws/${repository_relative_path}"' in LAUNCHER
    assert 'module_path="${container_repository_root}/DENTOWorkflow"' in LAUNCHER
    assert 'DENTOBOT_WATCHDOG_METADATA=${DENTOBOT_WATCHDOG_METADATA}' in LAUNCHER
    auto = LAUNCHER[LAUNCHER.index('if [[ ${graphics_mode} == "auto" ]]'):LAUNCHER.index('if [[ ${graphics_mode} !=')]
    assert auto.index('-c ${render_device}') < auto.index('-e /dev/dxg')
    assert 'nvidia' not in auto
    start = LAUNCHER.index('if [[ ${graphics_mode} !=')
    end = LAUNCHER.index('\nif [[ -z ${backend_python}', start)
    result = _shell('graphics_mode=invalid\n' + LAUNCHER[start:end])
    assert result.returncode == 2 and 'Unsupported' in result.stderr
