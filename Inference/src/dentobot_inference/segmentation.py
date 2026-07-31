"""Explicit-device TotalSegmentator teeth inference and result validation."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import nibabel as nib
import numpy as np

from dentobot_inference import __version__


ProgressCallback = Callable[[dict[str, Any]], None]
TEETH_TASK_ID = 113
CRANIOFACIAL_TASK_ID = 115
TOTAL_FAST_CROP_TASK_ID = 298


class TeethSegmentationError(RuntimeError):
    """Expected Bridge C failure with a stable machine-readable code."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _distribution_version(*names: str) -> str | None:
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(document, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _image_geometry(image: nib.spatialimages.SpatialImage) -> dict[str, Any]:
    return {
        "shape": [int(value) for value in image.shape],
        "zooms": [
            float(value)
            for value in image.header.get_zooms()[: len(image.shape)]
        ],
        "affine": np.asarray(image.affine, dtype=float).tolist(),
        "dataType": str(image.get_data_dtype()),
    }


def _geometry_matches(
    input_image: nib.spatialimages.SpatialImage,
    output_image: nib.spatialimages.SpatialImage,
) -> bool:
    return bool(
        tuple(input_image.shape) == tuple(output_image.shape)
        and np.allclose(
            np.asarray(input_image.header.get_zooms()[: len(input_image.shape)]),
            np.asarray(output_image.header.get_zooms()[: len(output_image.shape)]),
            rtol=0.0,
            atol=1e-6,
        )
        and np.allclose(
            np.asarray(input_image.affine),
            np.asarray(output_image.affine),
            rtol=0.0,
            atol=1e-4,
        )
    )


def validate_segmentation_output(
    input_image: nib.spatialimages.SpatialImage,
    output_image: nib.spatialimages.SpatialImage,
    label_map: Mapping[int, str],
) -> dict[str, Any]:
    """Validate a multilabel output and calculate per-label volume metrics."""

    if len(input_image.shape) != 3 or len(output_image.shape) != 3:
        raise TeethSegmentationError(
            "Input and output NIfTI images must both be three-dimensional.",
            "INVALID_IMAGE_DIMENSION",
        )
    if not _geometry_matches(input_image, output_image):
        raise TeethSegmentationError(
            "Segmentation voxel grid or physical geometry does not match the input.",
            "GEOMETRY_MISMATCH",
        )

    output_dtype = np.dtype(output_image.get_data_dtype())
    if not np.issubdtype(output_dtype, np.integer):
        raise TeethSegmentationError(
            f"Segmentation storage type must be integer, not {output_dtype}.",
            "INVALID_LABEL_TYPE",
        )

    label_data = np.asanyarray(output_image.dataobj)
    unique_values, voxel_counts = np.unique(label_data, return_counts=True)
    label_ids = [int(value) for value in unique_values]
    if any(value < 0 for value in label_ids):
        raise TeethSegmentationError(
            "Segmentation contains a negative label value.",
            "INVALID_LABEL_VALUE",
        )

    normalized_label_map = {
        int(label_id): str(label_name)
        for label_id, label_name in label_map.items()
    }
    unknown_labels = sorted(
        label_id
        for label_id in label_ids
        if label_id != 0 and label_id not in normalized_label_map
    )
    if unknown_labels:
        raise TeethSegmentationError(
            "Segmentation contains labels outside the TotalSegmentator teeth "
            f"contract: {unknown_labels}",
            "UNKNOWN_LABEL_VALUE",
        )

    voxel_volume_mm3 = float(
        abs(np.linalg.det(np.asarray(output_image.affine, dtype=float)[:3, :3]))
    )
    if not np.isfinite(voxel_volume_mm3) or voxel_volume_mm3 <= 0:
        raise TeethSegmentationError(
            "Segmentation affine has an invalid physical voxel volume.",
            "INVALID_OUTPUT_GEOMETRY",
        )
    metrics = []
    foreground_voxels = 0
    for label_id, voxel_count in zip(label_ids, voxel_counts.tolist()):
        if label_id == 0:
            continue
        count = int(voxel_count)
        foreground_voxels += count
        metrics.append(
            {
                "id": label_id,
                "name": normalized_label_map[label_id],
                "voxelCount": count,
                "volumeMm3": round(count * voxel_volume_mm3, 6),
            }
        )

    if not metrics:
        raise TeethSegmentationError(
            "TotalSegmentator returned no foreground teeth labels.",
            "EMPTY_SEGMENTATION",
        )

    return {
        "geometryMatch": True,
        "labelValidationPassed": True,
        "detectedLabelIds": [metric["id"] for metric in metrics],
        "segmentCount": len(metrics),
        "foregroundVoxelCount": foreground_voxels,
        "foregroundVolumeMm3": round(
            foreground_voxels * voxel_volume_mm3,
            6,
        ),
        "voxelVolumeMm3": voxel_volume_mm3,
        "perLabel": metrics,
    }


def _cached_task_directories(task_id: int) -> list[Path]:
    results_value = os.environ.get("nnUNet_results", "").strip()
    if not results_value:
        raise TeethSegmentationError(
            "TotalSegmentator did not configure nnUNet_results.",
            "MODEL_CACHE_NOT_CONFIGURED",
        )
    results_directory = Path(results_value).expanduser()
    if not results_directory.is_dir():
        return []
    complete_directories = []
    for path in results_directory.glob(f"Dataset{task_id:03d}_*"):
        if (
            path.is_dir()
            and any(
                file_path.is_file() and file_path.stat().st_size > 0
                for file_path in path.rglob("dataset.json")
            )
            and any(
                file_path.is_file() and file_path.stat().st_size > 0
                for file_path in path.rglob("plans.json")
            )
            and any(
                file_path.is_file() and file_path.stat().st_size > 0
                for file_path in path.rglob("checkpoint_final.pth")
            )
        ):
            complete_directories.append(path)
    return sorted(complete_directories)


def _install_offline_weight_guard(python_api_module) -> dict[int, list[str]]:
    """Replace TotalSegmentator's downloader with a cache-only guard.

    The Python API invokes this global for the requested task and recursively
    for its crop model. Replacing it here prevents a Slicer button click from
    causing an implicit network download while still exercising the normal
    TotalSegmentator inference path.
    """

    cached_models: dict[int, list[str]] = {}

    def require_cached_weights(task_id: int) -> None:
        numeric_task_id = int(task_id)
        matches = _cached_task_directories(numeric_task_id)
        if not matches:
            task_name = {
                TEETH_TASK_ID: "teeth",
                CRANIOFACIAL_TASK_ID: "craniofacial_structures",
                TOTAL_FAST_CROP_TASK_ID: "total_fast",
            }.get(numeric_task_id, f"task {numeric_task_id}")
            raise TeethSegmentationError(
                "Required TotalSegmentator weights are not cached completely for "
                f"{task_name} (Dataset{numeric_task_id:03d}). Download them "
                "explicitly in the DENTOBOT inference environment before using "
                "Bridge C.",
                "MODEL_WEIGHTS_NOT_CACHED",
            )
        cached_models[numeric_task_id] = [str(path) for path in matches]

    python_api_module.download_pretrained_weights = require_cached_weights
    return cached_models


def _install_totalsegmentator_cpu_device_compatibility(python_api_module) -> None:
    """Work around TotalSegmentator 2.16 returning None for a CPU string.

    The teeth task recursively invokes its craniofacial crop. Version 2.16
    calls ``convert_device_to_string`` with the selected ``"cpu"`` string,
    while that helper only returns a value for torch.device objects.
    """

    original_converter = python_api_module.convert_device_to_string

    def convert_device_to_string(device_value):
        if device_value == "cpu":
            return "cpu"
        return original_converter(device_value)

    python_api_module.convert_device_to_string = convert_device_to_string


def run_teeth_segmentation(
    input_path: Path,
    output_path: Path,
    result_json_path: Path,
    run_id: str,
    device: str = "cuda:0",
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run TotalSegmentator's ToothFairy3-backed teeth task without fallback."""

    if device not in ("cpu", "cuda:0"):
        raise ValueError(f"Unsupported segmentation device: {device}")

    started_at = _utc_now()
    started_monotonic = time.monotonic()
    result: dict[str, Any] = {
        "schemaVersion": "1.0",
        "runId": run_id,
        "command": "segment-teeth",
        "status": "error",
        "errorCode": None,
        "backend": {
            "name": "dentobot-inference",
            "version": __version__,
            "pythonVersion": platform.python_version(),
            "pythonExecutable": sys.executable,
            "packages": {
                "nibabel": nib.__version__,
                "numpy": np.__version__,
                "torch": _distribution_version("torch"),
                "TotalSegmentator": _distribution_version(
                    "TotalSegmentator",
                    "totalsegmentator",
                ),
                "nnunetv2": _distribution_version("nnunetv2"),
            },
        },
        "model": {
            "task": "teeth",
            "taskId": TEETH_TASK_ID,
            "cropTask": "craniofacial_structures",
            "cropTaskId": CRANIOFACIAL_TASK_ID,
            "transitiveCropTask": "total_fast",
            "transitiveCropTaskId": TOTAL_FAST_CROP_TASK_ID,
            "sourceDataset": "ToothFairy3",
            "multilabel": True,
            "cachedWeights": {},
        },
        "device": {
            "requested": device,
            "actual": None,
            "name": None,
            "torchCudaVersion": None,
            "peakAllocatedBytes": None,
            "peakReservedBytes": None,
        },
        "startedAtUtc": started_at,
        "completedAtUtc": None,
        "runtimeSeconds": None,
        "inferenceSeconds": None,
        "input": None,
        "output": None,
        "geometryMatch": False,
        "labelValidationPassed": False,
        "labels": [],
        "metrics": None,
        "errors": [],
        "warnings": [
            "Research output only; segmentation requires human review.",
        ],
        "traceback": None,
    }
    current_stage = "initialization"

    def report(stage: str, message: str) -> None:
        nonlocal current_stage
        current_stage = stage
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
            raise TeethSegmentationError(
                f"Input NIfTI does not exist: {input_path}",
                "INPUT_NOT_FOUND",
            )
        if output_path.exists():
            raise TeethSegmentationError(
                f"Refusing to overwrite an existing segmentation: {output_path}",
                "OUTPUT_ALREADY_EXISTS",
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report("load", "Loading and validating the input CBCT NIfTI")
        input_image = nib.load(str(input_path))
        if len(input_image.shape) != 3:
            raise TeethSegmentationError(
                "The input CBCT NIfTI must be three-dimensional.",
                "INVALID_IMAGE_DIMENSION",
            )
        result["input"] = {
            "path": str(input_path),
            "fileSizeBytes": int(input_path.stat().st_size),
            **_image_geometry(input_image),
        }

        report("device", f"Checking explicit {device} execution")
        try:
            import torch
        except Exception as exc:
            raise TeethSegmentationError(
                f"PyTorch import failed: {type(exc).__name__}: {exc}",
                "PYTORCH_IMPORT_FAILED",
            ) from exc
        if device == "cuda:0":
            if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
                raise TeethSegmentationError(
                    "CUDA device 0 is unavailable. Bridge C does not fall back to CPU.",
                    "CUDA_UNAVAILABLE",
                )
            torch.cuda.set_device(0)
            torch.cuda.synchronize(0)
            torch.cuda.reset_peak_memory_stats(0)
            result["device"].update(
                {
                    "actual": "cuda:0",
                    "name": torch.cuda.get_device_name(0),
                    "torchCudaVersion": getattr(torch.version, "cuda", None),
                }
            )
        else:
            result["device"].update(
                {
                    "actual": "cpu",
                    "name": platform.processor() or platform.machine() or "CPU",
                }
            )

        report("model", "Loading TotalSegmentator with network downloads disabled")
        try:
            import totalsegmentator.python_api as total_segmentator_api
            from totalsegmentator.map_to_binary import class_map
        except Exception as exc:
            raise TeethSegmentationError(
                "TotalSegmentator import failed. Install it in the dedicated "
                f"DENTOBOT inference environment: {type(exc).__name__}: {exc}",
                "TOTALSEGMENTATOR_IMPORT_FAILED",
            ) from exc

        cached_models = _install_offline_weight_guard(total_segmentator_api)
        if device == "cpu":
            _install_totalsegmentator_cpu_device_compatibility(
                total_segmentator_api
            )
        total_segmentator_api.send_usage_stats = lambda *args, **kwargs: None
        raw_label_map = class_map.get("teeth")
        if not raw_label_map:
            raise TeethSegmentationError(
                "Installed TotalSegmentator does not expose the teeth label map.",
                "TEETH_TASK_UNAVAILABLE",
            )
        label_map = {
            int(label_id): str(label_name)
            for label_id, label_name in raw_label_map.items()
        }
        result["labels"] = [
            {"id": label_id, "name": label_map[label_id]}
            for label_id in sorted(label_map)
        ]

        report(
            "inference",
            f"Running TotalSegmentator teeth inference on {device}",
        )
        inference_started = time.monotonic()
        total_segmentator_api.totalsegmentator(
            input=input_path,
            output=output_path,
            ml=True,
            task="teeth",
            device="gpu" if device == "cuda:0" else "cpu",
            nr_thr_resamp=1,
            nr_thr_saving=1,
            quiet=False,
            verbose=False,
        )
        if device == "cuda:0":
            torch.cuda.synchronize(0)
        result["inferenceSeconds"] = round(
            time.monotonic() - inference_started,
            6,
        )
        if device == "cuda:0":
            result["device"]["peakAllocatedBytes"] = int(
                torch.cuda.max_memory_allocated(0)
            )
            result["device"]["peakReservedBytes"] = int(
                torch.cuda.max_memory_reserved(0)
            )
        result["model"]["cachedWeights"] = {
            str(task_id): paths
            for task_id, paths in sorted(cached_models.items())
        }

        if not output_path.is_file():
            raise TeethSegmentationError(
                "TotalSegmentator completed without creating the expected NIfTI.",
                "OUTPUT_NOT_CREATED",
            )

        report("validate", "Validating segmentation geometry and label values")
        output_image = nib.load(str(output_path))
        result["output"] = {
            "path": str(output_path),
            "fileSizeBytes": int(output_path.stat().st_size),
            **_image_geometry(output_image),
        }
        validation = validate_segmentation_output(
            input_image,
            output_image,
            label_map,
        )
        result["geometryMatch"] = validation.pop("geometryMatch")
        result["labelValidationPassed"] = validation.pop(
            "labelValidationPassed"
        )
        result["metrics"] = validation
        result["status"] = "ok"
        report(
            "complete",
            "Teeth segmentation and output validation completed",
        )
    except TeethSegmentationError as exc:
        result["errorCode"] = exc.code
        result["errors"].append(str(exc))
    except Exception as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        if (
            type(exc).__name__ == "OutOfMemoryError"
            or "CUDA out of memory" in str(exc)
        ):
            result["errorCode"] = (
                "CUDA_OUT_OF_MEMORY" if device == "cuda:0" else "CPU_OUT_OF_MEMORY"
            )
        elif current_stage == "model":
            result["errorCode"] = "MODEL_INITIALIZATION_FAILED"
        elif current_stage == "inference":
            result["errorCode"] = "INFERENCE_FAILED"
        elif current_stage == "validate":
            result["errorCode"] = "OUTPUT_VALIDATION_FAILED"
        else:
            result["errorCode"] = "UNEXPECTED_BACKEND_ERROR"
        result["errors"].append(error_text)
        result["traceback"] = traceback.format_exc()
    finally:
        if result["status"] != "ok" and output_path.is_file():
            try:
                output_path.unlink()
            except OSError as exc:
                result["warnings"].append(
                    f"Could not remove incomplete segmentation output: {exc}"
                )
        result["completedAtUtc"] = _utc_now()
        result["runtimeSeconds"] = round(
            time.monotonic() - started_monotonic,
            6,
        )
        _write_json(result_json_path, result)

    return result
