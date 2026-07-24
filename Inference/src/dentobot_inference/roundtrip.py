"""Geometry-preserving NIfTI round-trip used to verify the bridge."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import nibabel as nib
import numpy as np

from dentobot_inference import __version__


ProgressCallback = Callable[[dict[str, Any]], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _image_checksum(image: nib.spatialimages.SpatialImage) -> str:
    """Hash voxel values after one sequential materialization of the proxy.

    Repeated random access through a compressed NIfTI proxy can decompress the
    same file many times. Materializing once keeps compressed inputs linear in
    file size, while per-plane byte conversion limits additional peak memory.
    """

    digest = hashlib.sha256()
    shape = tuple(int(value) for value in image.shape)
    data = np.asanyarray(image.dataobj)

    if not shape:
        digest.update(np.ascontiguousarray(data).tobytes())
        return digest.hexdigest()

    if len(shape) == 1:
        digest.update(np.ascontiguousarray(data).tobytes())
        return digest.hexdigest()

    for index in range(shape[-1]):
        data_slice = np.ascontiguousarray(data[..., index])
        digest.update(data_slice.tobytes())
    return digest.hexdigest()


def _image_metadata(image: nib.spatialimages.SpatialImage) -> dict[str, Any]:
    return {
        "shape": [int(value) for value in image.shape],
        "zooms": [float(value) for value in image.header.get_zooms()],
        "affine": np.asarray(image.affine, dtype=float).tolist(),
        "dataType": str(image.get_data_dtype()),
        "sha256": _image_checksum(image),
    }


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(document, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def run_roundtrip(
    input_path: Path,
    output_path: Path,
    result_json_path: Path,
    run_id: str,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Rewrite a NIfTI image and validate data plus physical geometry."""

    started_at = _utc_now()
    started_monotonic = time.monotonic()
    result: dict[str, Any] = {
        "schemaVersion": "1.0",
        "runId": run_id,
        "command": "roundtrip",
        "status": "error",
        "backend": {
            "name": "dentobot-inference",
            "version": __version__,
            "pythonVersion": platform.python_version(),
            "pythonExecutable": sys.executable,
            "nibabelVersion": nib.__version__,
            "numpyVersion": np.__version__,
        },
        "startedAtUtc": started_at,
        "completedAtUtc": None,
        "runtimeSeconds": None,
        "input": None,
        "output": None,
        "geometryMatch": False,
        "dataMatch": False,
        "errors": [],
    }

    def report(stage: str, message: str) -> None:
        if progress_callback:
            progress_callback(
                {
                    "schemaVersion": "1.0",
                    "event": "progress",
                    "runId": run_id,
                    "stage": stage,
                    "message": message,
                    "timestampUtc": _utc_now(),
                }
            )

    try:
        if not input_path.is_file():
            raise FileNotFoundError(f"Input NIfTI does not exist: {input_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report("load", "Loading input NIfTI")
        input_image = nib.load(str(input_path))
        report("checksum-input", "Calculating input voxel checksum")
        result["input"] = _image_metadata(input_image)

        report("write", "Writing round-trip NIfTI")
        nib.save(input_image, str(output_path))

        report("validate", "Reloading and validating output NIfTI")
        output_image = nib.load(str(output_path))
        report("checksum-output", "Calculating output voxel checksum")
        result["output"] = _image_metadata(output_image)

        result["geometryMatch"] = bool(
            result["input"]["shape"] == result["output"]["shape"]
            and np.allclose(
                np.asarray(result["input"]["zooms"]),
                np.asarray(result["output"]["zooms"]),
                rtol=0.0,
                atol=1e-6,
            )
            and np.allclose(
                np.asarray(result["input"]["affine"]),
                np.asarray(result["output"]["affine"]),
                rtol=0.0,
                atol=1e-5,
            )
        )
        result["dataMatch"] = bool(
            result["input"]["dataType"] == result["output"]["dataType"]
            and result["input"]["sha256"] == result["output"]["sha256"]
        )

        if not result["geometryMatch"]:
            result["errors"].append("Output physical geometry does not match the input.")
        if not result["dataMatch"]:
            result["errors"].append("Output voxel data does not match the input.")
        if not result["errors"]:
            result["status"] = "ok"
            report("complete", "NIfTI round-trip validation passed")
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        result["completedAtUtc"] = _utc_now()
        result["runtimeSeconds"] = round(time.monotonic() - started_monotonic, 6)
        _write_json(result_json_path, result)

    return result
