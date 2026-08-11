"""Platform-neutral DENTOBOT backend process and path contracts.

This module intentionally has no Slicer imports.  Native Windows Slicer uses
the ``wsl`` adapter, while Linux Slicer (native or containerized) uses the
``local`` adapter.  Both adapters invoke the same Linux inference package by
absolute interpreter path and exchange files through a Slicer-visible
artifact directory.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


EXECUTION_MODE_ENVIRONMENT_VARIABLE = "DENTOBOT_BACKEND_EXECUTION_MODE"
BACKEND_PYTHON_ENVIRONMENT_VARIABLE = "DENTOBOT_BACKEND_PYTHON"
RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE = "DENTOBOT_RUN_ARTIFACT_ROOT"
WSL_DISTRIBUTION_ENVIRONMENT_VARIABLE = "DENTOBOT_WSL_DISTRIBUTION"
BACKEND_DEVICE_ENVIRONMENT_VARIABLE = "DENTOBOT_BACKEND_DEVICE"

SUPPORTED_EXECUTION_MODES = ("local", "wsl")
SUPPORTED_BACKEND_DEVICES = ("cpu", "cuda:0")


@dataclass(frozen=True)
class LauncherBackendConfiguration:
    """Non-persistent machine configuration inherited from a launcher."""

    execution_mode: str = ""
    distribution: str = ""
    python_path: str = ""
    artifact_root: str = ""
    device: str = ""

    def is_complete(self) -> bool:
        if self.execution_mode not in SUPPORTED_EXECUTION_MODES:
            return False
        if not self.python_path or not self.artifact_root:
            return False
        if self.device not in SUPPORTED_BACKEND_DEVICES:
            return False
        return self.execution_mode != "wsl" or bool(self.distribution)


def default_execution_mode(os_name: str | None = None) -> str:
    """Return the process adapter used by the current Slicer host."""

    return "wsl" if (os.name if os_name is None else os_name) == "nt" else "local"


def _environment_value(source: Mapping[str, str], name: str) -> str:
    """Read one environment value without retaining the environment mapping."""

    try:
        value = source[name]
    except (KeyError, TypeError):
        value = ""
    return str(value or "").strip()


def launcher_backend_configuration(
    environment: Mapping[str, str] | None = None,
) -> LauncherBackendConfiguration:
    """Read the shared Windows/Linux launcher contract.

    No path or device default is inferred here.  A launcher configuration is
    authoritative only when it states the adapter and device explicitly.
    This prevents a Windows MRB from silently executing with Linux defaults,
    or vice versa.
    """

    source = os.environ if environment is None else environment
    return LauncherBackendConfiguration(
        execution_mode=_environment_value(
            source,
            EXECUTION_MODE_ENVIRONMENT_VARIABLE,
        ).lower(),
        distribution=_environment_value(
            source,
            WSL_DISTRIBUTION_ENVIRONMENT_VARIABLE,
        ),
        python_path=_environment_value(
            source,
            BACKEND_PYTHON_ENVIRONMENT_VARIABLE,
        ),
        artifact_root=_environment_value(
            source,
            RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE,
        ),
        device=_environment_value(
            source,
            BACKEND_DEVICE_ENVIRONMENT_VARIABLE,
        ).lower(),
    )


def windows_path_to_wsl_path(windows_path: str | Path) -> str:
    """Map an absolute local Windows drive path to WSL's ``/mnt`` path."""

    path_text = str(windows_path)
    if path_text.startswith("\\\\") or path_text.startswith("//"):
        raise ValueError("UNC/network paths cannot be mapped by this bridge.")
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", path_text)
    if not match:
        raise ValueError("Expected an absolute Windows drive path.")
    drive = match.group(1).lower()
    remainder = match.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{remainder}"


def build_backend_python_command(
    *,
    execution_mode: str,
    distribution: str,
    python_path: str,
    backend_module: str,
    backend_arguments: list[str],
    wsl_executable: str,
) -> list[str]:
    """Build a shell-free command for the selected process adapter."""

    mode = execution_mode.strip().lower()
    python = python_path.strip()
    if mode not in SUPPORTED_EXECUTION_MODES:
        raise ValueError(f"Unsupported backend execution mode: {mode or '<empty>'}.")
    if not python.startswith("/"):
        raise ValueError("The backend Python path must be an absolute Linux path.")
    if mode == "wsl":
        distro = distribution.strip()
        if not distro:
            raise ValueError("The WSL distribution name is required.")
        return [
            wsl_executable,
            "--distribution",
            distro,
            "--exec",
            python,
            "-m",
            backend_module,
            *backend_arguments,
        ]
    return [python, "-m", backend_module, *backend_arguments]
