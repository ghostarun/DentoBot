"""Environment and CUDA health reporting without environment mutation."""

from __future__ import annotations

import importlib.metadata
import platform
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


def collect_health(require_cuda: bool = False) -> dict[str, Any]:
    """Return a JSON-serializable report for the active Python environment."""

    packages = {
        "dentobot-inference": _distribution_version("dentobot-inference"),
        "nibabel": _distribution_version("nibabel"),
        "numpy": _distribution_version("numpy"),
        "torch": _distribution_version("torch"),
        "TotalSegmentator": _distribution_version("TotalSegmentator", "totalsegmentator"),
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
    if packages["torch"] is None:
        if require_cuda:
            errors.append("PyTorch is not installed, so CUDA cannot be used.")
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
            elif require_cuda:
                errors.append(
                    "PyTorch is installed but torch.cuda.is_available() is false."
                )
        except Exception as exc:
            errors.append(f"PyTorch CUDA inspection failed: {type(exc).__name__}: {exc}")

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
        "errors": errors,
    }

