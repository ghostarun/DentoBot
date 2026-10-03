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


@pytest.mark.parametrize('graphics,wsl,refused', [
    ('nvidia', True, True), ('nvidia', False, False),
    ('wslg', True, False), ('mesa', False, False),
])
def test_nvidia_mode_is_refused_under_wsl(graphics, wsl, refused):
    start = LAUNCHER.index('if [[ ${graphics_mode} == "nvidia" ]] && host_is_wsl; then')
    end = LAUNCHER.index('\nrender_probe_container_case=""', start)
    stub = f'host_is_wsl() {{ return {0 if wsl else 1}; }}\ngraphics_mode={graphics}\n'
    result = _shell(stub + LAUNCHER[start:end] + '\nprintf "continued\\n"')
    assert result.returncode == (2 if refused else 0), result.stderr
    if refused:
        assert 'native Ubuntu NVIDIA hosts only' in result.stderr
        assert 'DENTOBOT_GRAPHICS_MODE=wslg' in result.stderr
        assert 'continued' not in result.stdout
    else:
        assert result.stdout.strip() == 'continued'


def test_wsl_detection_probes_and_this_host():
    start = LAUNCHER.index('host_is_wsl() {')
    end = LAUNCHER.index('\n}\n', start) + 3
    function = LAUNCHER[start:end]
    assert '/proc/sys/kernel/osrelease' in function and '*microsoft*' in function
    assert '-e /dev/dxg' in function and '-d /mnt/wslg' in function
    osrelease = Path('/proc/sys/kernel/osrelease')
    on_wsl = (osrelease.exists() and 'microsoft' in osrelease.read_text().lower()) or \
        Path('/dev/dxg').exists() or Path('/mnt/wslg').is_dir()
    result = _shell(function + '\nif host_is_wsl; then echo wsl; else echo native; fi')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ('wsl' if on_wsl else 'native')


def _recreate_block():
    start = LAUNCHER.index('container_has_nvidia_gpu_request() {')
    end = LAUNCHER.index('if [[ ${container_needs_recreate} == true ]]', start)
    return LAUNCHER[start:end] + '\nprintf "recreate=%s\\n" "${container_needs_recreate}"'


def _stub_inspect(tmp_path, *, requests, env):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    docker = bindir / 'docker'
    docker.write_text('#!/bin/bash\ncase "$*" in\n'
                      '  *Config.User*) echo 1000:1000 ;;\n'
                      '  *Mounts*) echo \'[{"Destination":"/home/dentobot"}]\' ;;\n'
                      '  *DeviceRequests*) printf "%s\\n" "$STUB_REQUESTS" ;;\n'
                      '  *Config.Env*) printf "%s\\n" "$STUB_ENV" ;;\n'
                      'esac\n')
    docker.chmod(0o755)
    return {'PATH': f'{bindir}:/usr/bin:/bin', 'STUB_REQUESTS': requests, 'STUB_ENV': env}


GPU_REQUEST = '[{"Driver":"nvidia","Count":1,"Capabilities":[["gpu"]]}]'
GRAPHICS_ENV = 'PATH=/usr/bin\nNVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display'


@pytest.mark.parametrize('graphics,backend,requests,env,recreate', [
    ('nvidia', 'cpu', GPU_REQUEST, GRAPHICS_ENV, 'false'),
    ('nvidia', 'cpu', 'null', GRAPHICS_ENV, 'true'),
    ('nvidia', 'cpu', GPU_REQUEST, 'NVIDIA_DRIVER_CAPABILITIES=compute,utility', 'true'),
    ('mesa', 'cuda:0', GPU_REQUEST, 'NVIDIA_DRIVER_CAPABILITIES=compute,utility', 'false'),
    ('mesa', 'cuda:0', 'null', '', 'true'),
    ('mesa', 'cpu', 'null', '', 'false'),
])
def test_nvidia_container_recreated_only_without_gpu_request(tmp_path, graphics, backend, requests, env, recreate):
    setup = (f'graphics_mode={graphics}\nbackend_device={backend}\ncontainer_name=stub\n'
             'host_uid=1000\nhost_gid=1000\n')
    result = _shell(setup + _recreate_block(), _stub_inspect(tmp_path, requests=requests, env=env))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == f'recreate={recreate}'


def _probe_case_block():
    start = LAUNCHER.index('render_probe_container_case=""')
    end = LAUNCHER.index('\nif [[ -z ${backend_python}', start)
    return LAUNCHER[start:end] + ('\nprintf "%s\\n%s\\n" "${render_probe_container_case}" '
                                  '"${render_probe_dir}"')


def test_render_probe_case_maps_into_container_data(tmp_path):
    case = tmp_path / 'ws/data/Slicer_Saved/study/case.dentocase'
    case.parent.mkdir(parents=True)
    case.write_text('stub')
    setup = f'workspace_root={tmp_path}/ws\ncheck_only=false\nrender_probe_case={case}\n'
    result = _shell(setup + _probe_case_block())
    assert result.returncode == 0, result.stderr
    container_case, probe_dir = result.stdout.splitlines()
    assert container_case == '/workspace/data/Slicer_Saved/study/case.dentocase'
    assert probe_dir.startswith(f'{tmp_path}/ws/data/dentobot-runs/render-probe-')


@pytest.mark.parametrize('where,check_only,message', [
    ('outside', 'false', 'must be under'),
    ('missing', 'false', 'case file is missing'),
    ('inside', 'true', 'cannot be combined with --check-only'),
])
def test_render_probe_case_rejections(tmp_path, where, check_only, message):
    (tmp_path / 'ws/data').mkdir(parents=True)
    case = tmp_path / ('ws/data/case.dentocase' if where != 'outside' else 'elsewhere.dentocase')
    if where != 'missing':
        case.write_text('stub')
    setup = f'workspace_root={tmp_path}/ws\ncheck_only={check_only}\nrender_probe_case={case}\n'
    result = _shell(setup + _probe_case_block())
    assert result.returncode == 2
    assert message in result.stderr


def test_render_probe_launch_uses_probe_script_and_judges_result():
    script = LAUNCHER[LAUNCHER.index("container_launch_script='"):]
    probe = script[script.index('if [[ -n ${DENTOBOT_RENDER_PROBE_SCRIPT:-} ]]'):]
    assert '"slicer_args:=--no-splash --python-script ${DENTOBOT_RENDER_PROBE_SCRIPT}"' in probe
    assert 'Testing/run_dentobot_render_frame_probe.py' in LAUNCHER
    assert 'DENTOBOT_PERF_CASE=${render_probe_container_case}' in LAUNCHER
    assert 'Testing/evaluate_render_probe.py' in LAUNCHER
    assert 'tee "${render_probe_dir}/slicer-probe.log"' in LAUNCHER
    assert 'bash -lc "${container_launch_script}"' in LAUNCHER


def _probe_report(*, renderer='NVIDIA GeForce RTX 4070/PCIe/SSE2', vendor='NVIDIA Corporation',
                  median=6.2, headless=False, software=False, status='complete'):
    return {
        'status': status, 'case_loaded': True,
        'renderer': {'renderer_string': f'OpenGL renderer string: {renderer}',
                     'vendor_string': f'OpenGL vendor string: {vendor}', 'opengl_version': '4.6'},
        'render_context': {'headless_detected': headless, 'software_renderer_detected': software},
        'render': {'median_interval_ms': median, 'p95_interval_ms': median, 'event_rate_hz': 160.0},
        'qt_heartbeat': {'median_interval_ms': 100.0},
    }


@pytest.mark.parametrize('mode,report,status,failed', [
    ('nvidia', _probe_report(), 'PASS', []),
    ('nvidia', _probe_report(median=16.9), 'PASS', []),
    ('nvidia', _probe_report(median=21.0), 'FAIL', ['median_interval_within_60fps']),
    ('nvidia', _probe_report(renderer='llvmpipe (LLVM 17.0.6, 256 bits)', vendor='Mesa',
                             software=True), 'FAIL', ['hardware_renderer', 'nvidia_renderer']),
    ('nvidia', _probe_report(headless=True), 'FAIL', ['real_display']),
    ('nvidia', _probe_report(renderer='Mesa Intel(R) UHD 770', vendor='Intel'), 'FAIL', ['nvidia_renderer']),
    ('mesa', _probe_report(renderer='Mesa Intel(R) UHD 770', vendor='Intel'), 'PASS', []),
    ('nvidia', _probe_report(status='failed'), 'FAIL', ['probe_complete']),
])
def test_render_probe_evaluator(tmp_path, mode, report, status, failed):
    import json
    import sys
    sys.path.insert(0, str(ROOT / 'Testing'))
    import evaluate_render_probe
    log = tmp_path / 'probe.log'
    log.write_text('noise\n[INFO] DENTOBOT_RENDER_FRAME_PROBE ' + json.dumps(report) + '\n')
    output = tmp_path / 'verdict.json'
    code = evaluate_render_probe.main([str(log), '--graphics-mode', mode, '--output', str(output)])
    verdict = json.loads(output.read_text())
    assert verdict['status'] == status and code == (0 if status == 'PASS' else 1)
    assert sorted(name for name, ok in verdict['checks'].items() if not ok) == sorted(failed)


def test_render_probe_evaluator_without_report(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / 'Testing'))
    import evaluate_render_probe
    log = tmp_path / 'probe.log'
    log.write_text('Slicer crashed before the probe ran\n')
    assert evaluate_render_probe.main([str(log), '--graphics-mode', 'nvidia']) == 2
