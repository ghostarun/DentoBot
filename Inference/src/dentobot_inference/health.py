"""Environment and compute-device health reporting without mutation."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


def _distribution_version(*names: str) -> str | None:
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def collect_health(
    require_cuda: bool = False,
    require_device: str | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable report for the active Python environment."""

    packages = {
        "dentobot-inference": _distribution_version("dentobot-inference"),
        "nibabel": _distribution_version("nibabel"),
        "numpy": _distribution_version("numpy"),
        "torch": _distribution_version("torch"),
        "TotalSegmentator": _distribution_version("TotalSegmentator", "totalsegmentator"),
        "openvino": _distribution_version("openvino"),
    }
    errors: list[str] = []
    for required_package in ("nibabel", "numpy"):
        if packages[required_package] is None:
            errors.append(f"Required package is not installed: {required_package}")

    cuda: dict[str, Any] = {
        "available": False,
        "deviceCount": 0,
        "devices": [],
        "torchCudaVersion": None,
    }
    requested_device = "cuda:0" if require_cuda else require_device
    if requested_device not in (None, "cpu", "cuda:0"):
        errors.append(f"Unsupported requested device: {requested_device}")

    if packages["torch"] is None:
        if requested_device:
            errors.append(
                f"PyTorch is not installed, so {requested_device} cannot be used."
            )
    else:
        try:
            import torch

            cuda["available"] = bool(torch.cuda.is_available())
            cuda["torchCudaVersion"] = getattr(torch.version, "cuda", None)
            if cuda["available"]:
                cuda["deviceCount"] = int(torch.cuda.device_count())
                cuda["devices"] = [
                    torch.cuda.get_device_name(index)
                    for index in range(cuda["deviceCount"])
                ]
            elif requested_device == "cuda:0":
                errors.append(
                    "PyTorch is installed but torch.cuda.is_available() is false."
                )
        except Exception as exc:
            errors.append(f"PyTorch CUDA inspection failed: {type(exc).__name__}: {exc}")

    if requested_device == "cpu" and packages["TotalSegmentator"] is None:
        errors.append("TotalSegmentator is not installed for CPU segmentation.")

    openvino_report: dict[str, Any] = {
        "available": packages["openvino"] is not None,
        "devices": [],
        "error": None,
    }
    if openvino_report["available"]:
        try:
            probe = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json, openvino; "
                        "print(json.dumps(list(openvino.Core().available_devices)))"
                    ),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=20.0,
            )
            if probe.returncode != 0:
                detail = probe.stderr.strip() or probe.stdout.strip()
                openvino_report["error"] = (
                    f"OpenVINO device probe exited with code {probe.returncode}"
                    + (f": {detail}" if detail else "")
                )
            else:
                output_lines = [
                    line for line in probe.stdout.splitlines() if line.strip()
                ]
                if not output_lines:
                    raise ValueError("OpenVINO device probe returned no JSON")
                devices = json.loads(output_lines[-1])
                if not isinstance(devices, list):
                    raise ValueError("OpenVINO device probe did not return a list")
                openvino_report["devices"] = [str(device) for device in devices]
        except subprocess.TimeoutExpired:
            openvino_report["error"] = "OpenVINO device probe timed out."
        except Exception as exc:
            openvino_report["error"] = f"{type(exc).__name__}: {exc}"

    return {
        "schemaVersion": "1.0",
        "command": "health",
        "status": "ok" if not errors else "error",
        "timestampUtc": datetime.now(timezone.utc).isoformat(),
        "python": {
            "executable": sys.executable,
            "prefix": sys.prefix,
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "packages": packages,
        "cuda": cuda,
        "requestedDevice": requested_device,
        "openvino": openvino_report,
        "errors": errors,
    }
