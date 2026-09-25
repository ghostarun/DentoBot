"""Source-only checks for the cross-platform graphics profile contract."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_graphics_profile_contract():
    launcher = (ROOT / "Workspace/scripts/launch-dentoworkflow.bash").read_text()
    wslg = (ROOT / "Workspace/compose.wslg.yaml").read_text()
    nvidia = (ROOT / "Workspace/compose.nvidia.yaml").read_text()
    cuda = (ROOT / "Workspace/compose.cuda.yaml").read_text()

    auto_match = re.search(
        r'if \[\[ \$\{graphics_mode\} == "auto" \]\]; then(.*?)\nfi',
        launcher,
        re.S,
    )
    assert auto_match, "graphics auto-selection block is missing"
    auto = auto_match.group(1)
    assert auto.index("if [[ -e /dev/dxg || -d /mnt/wslg ]]") < auto.index(
        'elif [[ -c ${render_device} ]]'
    ), "WSLg must take precedence when WSLg and a DRM node are both present"

    assert "MESA_D3D12_DEFAULT_ADAPTER_NAME: ${DENTOBOT_WSLG_ADAPTER_NAME:-}" in wslg

    compose_start = launcher.index("compose_command=(")
    compose_end = launcher.index("# compose.yaml still interpolates", compose_start)
    compose_selection = launcher[compose_start:compose_end]
    nvidia_branch = re.search(
        r'if \[\[ \$\{graphics_mode\} == "nvidia" \]\]; then\s+'
        r'compose_command\+=\(([^)]*)\)\s+'
        r'elif \[\[ \$\{backend_device\} == "cuda:0" \]\]; then\s+'
        r'compose_command\+=\(([^)]*)\)',
        compose_selection,
    )
    assert nvidia_branch, "native NVIDIA overlay must be selected independently of inference mode"
    assert "${compose_nvidia_file}" in nvidia_branch.group(1)
    assert "${compose_cuda_file}" in nvidia_branch.group(1)
    assert "${compose_cuda_file}" in nvidia_branch.group(2)
    assert "devices: !reset []" in nvidia
    assert "NVIDIA_DRIVER_CAPABILITIES: compute,utility,graphics,display" in cuda


if __name__ == "__main__":
    test_graphics_profile_contract()
    print("DENTOBOT_GRAPHICS_PROFILES_SOURCE_CHECK_PASS")
