"""Ordinary-Python tests for Windows/Linux runtime configuration."""

from pathlib import Path
import sys


HELPER_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "DENTOWorkflow"
    / "Resources"
    / "Python"
)
sys.path.insert(0, str(HELPER_DIRECTORY))

from DENTOPlatform import (  # noqa: E402
    LauncherBackendConfiguration,
    build_backend_python_command,
    default_execution_mode,
    launcher_backend_configuration,
    windows_path_to_wsl_path,
)


def test_host_default_adapter_is_explicit() -> None:
    assert default_execution_mode("nt") == "wsl"
    assert default_execution_mode("posix") == "local"


def test_linux_launcher_contract() -> None:
    configuration = launcher_backend_configuration(
        {
            "DENTOBOT_BACKEND_EXECUTION_MODE": "local",
            "DENTOBOT_BACKEND_PYTHON": "/opt/dentobot/bin/python",
            "DENTOBOT_RUN_ARTIFACT_ROOT": "/workspace/data/dentobot-runs",
            "DENTOBOT_BACKEND_DEVICE": "cpu",
        }
    )
    assert configuration == LauncherBackendConfiguration(
        execution_mode="local",
        python_path="/opt/dentobot/bin/python",
        artifact_root="/workspace/data/dentobot-runs",
        device="cpu",
    )
    assert configuration.is_complete()


def test_windows_wsl_launcher_contract_and_command() -> None:
    configuration = launcher_backend_configuration(
        {
            "DENTOBOT_BACKEND_EXECUTION_MODE": "WSL",
            "DENTOBOT_WSL_DISTRIBUTION": "Ubuntu-24.04",
            "DENTOBOT_BACKEND_PYTHON": "/home/user/miniconda3/envs/dentobot/bin/python",
            "DENTOBOT_RUN_ARTIFACT_ROOT": r"C:\DENTOBOTRuns",
            "DENTOBOT_BACKEND_DEVICE": "CUDA:0",
        }
    )
    assert configuration.is_complete()
    command = build_backend_python_command(
        execution_mode=configuration.execution_mode,
        distribution=configuration.distribution,
        python_path=configuration.python_path,
        backend_module="dentobot_inference",
        backend_arguments=["health", "--json", "--require-device", "cuda:0"],
        wsl_executable=r"C:\Windows\System32\wsl.exe",
    )
    assert command[:5] == [
        r"C:\Windows\System32\wsl.exe",
        "--distribution",
        "Ubuntu-24.04",
        "--exec",
        "/home/user/miniconda3/envs/dentobot/bin/python",
    ]
    assert command[-4:] == ["health", "--json", "--require-device", "cuda:0"]


def test_incomplete_or_ambiguous_launcher_contract_is_rejected() -> None:
    assert not launcher_backend_configuration({}).is_complete()
    assert not launcher_backend_configuration(
        {
            "DENTOBOT_BACKEND_EXECUTION_MODE": "wsl",
            "DENTOBOT_BACKEND_PYTHON": "/opt/dentobot/bin/python",
            "DENTOBOT_RUN_ARTIFACT_ROOT": r"C:\DENTOBOTRuns",
            "DENTOBOT_BACKEND_DEVICE": "cuda:0",
        }
    ).is_complete()


def test_artifact_path_translation_is_bounded_to_local_drive_paths() -> None:
    assert (
        windows_path_to_wsl_path(r"D:\DENTOBOT Runs\run-1\input.nii")
        == "/mnt/d/DENTOBOT Runs/run-1/input.nii"
    )
    try:
        windows_path_to_wsl_path(r"\\server\share\input.nii")
    except ValueError as exc:
        assert "UNC" in str(exc)
    else:
        raise AssertionError("UNC path was accepted")
