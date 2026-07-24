from pathlib import Path
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pytest

from dentobot_inference.segmentation import (
    TeethSegmentationError,
    _install_offline_weight_guard,
    run_teeth_segmentation,
    validate_segmentation_output,
)


def _image(data: np.ndarray) -> nib.Nifti1Image:
    affine = np.array(
        [
            [-0.4, 0.0, 0.0, 12.0],
            [0.0, -0.5, 0.0, -8.0],
            [0.0, 0.0, 0.6, 4.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    return nib.Nifti1Image(data, affine)


def test_validate_segmentation_output_calculates_label_metrics():
    source = _image(np.zeros((4, 5, 6), dtype=np.int16))
    labels = np.zeros((4, 5, 6), dtype=np.uint8)
    labels[0, 0, 0] = 1
    labels[1:3, 1:3, 1:3] = 3
    output = _image(labels)

    result = validate_segmentation_output(
        source,
        output,
        {1: "lower_jawbone", 3: "left_inferior_alveolar_canal"},
    )

    assert result["geometryMatch"] is True
    assert result["labelValidationPassed"] is True
    assert result["detectedLabelIds"] == [1, 3]
    assert result["segmentCount"] == 2
    assert result["foregroundVoxelCount"] == 9
    assert result["perLabel"][1]["voxelCount"] == 8
    assert result["foregroundVolumeMm3"] == pytest.approx(9 * 0.4 * 0.5 * 0.6)


def test_validate_segmentation_output_rejects_unknown_label():
    source = _image(np.zeros((2, 2, 2), dtype=np.int16))
    labels = np.zeros((2, 2, 2), dtype=np.uint8)
    labels[0, 0, 0] = 99

    with pytest.raises(TeethSegmentationError, match="outside"):
        validate_segmentation_output(source, _image(labels), {1: "known"})


def test_missing_input_writes_failure_without_model_import(tmp_path: Path):
    result_path = tmp_path / "result.json"

    result = run_teeth_segmentation(
        input_path=tmp_path / "missing.nii",
        output_path=tmp_path / "segmentation.nii",
        result_json_path=result_path,
        run_id="missing-input",
    )

    assert result["status"] == "error"
    assert result["errorCode"] == "INPUT_NOT_FOUND"
    assert result_path.is_file()
    assert not (tmp_path / "segmentation.nii").exists()


def test_offline_weight_guard_accepts_cache_without_downloading(
    tmp_path: Path,
    monkeypatch,
):
    results_directory = tmp_path / "nnunet" / "results"
    for dataset_name in ("Dataset113_ToothFairy3", "Dataset115_mandible"):
        model_directory = (
            results_directory
            / dataset_name
            / "trainer__plans__configuration"
            / "fold_0"
        )
        model_directory.mkdir(parents=True)
        (model_directory / "dataset.json").write_text("{}")
        (model_directory / "plans.json").write_text("{}")
        (model_directory / "checkpoint_final.pth").write_bytes(b"checkpoint")
    monkeypatch.setenv("nnUNet_results", str(results_directory))
    fake_python_api = SimpleNamespace(
        download_pretrained_weights=lambda task_id: pytest.fail(
            f"Downloader was called for {task_id}"
        )
    )

    cached_models = _install_offline_weight_guard(fake_python_api)
    fake_python_api.download_pretrained_weights(113)
    fake_python_api.download_pretrained_weights(115)

    assert sorted(cached_models) == [113, 115]


def test_offline_weight_guard_rejects_missing_cache(
    tmp_path: Path,
    monkeypatch,
):
    results_directory = tmp_path / "nnunet" / "results"
    results_directory.mkdir(parents=True)
    monkeypatch.setenv("nnUNet_results", str(results_directory))
    fake_python_api = SimpleNamespace(download_pretrained_weights=None)
    _install_offline_weight_guard(fake_python_api)

    with pytest.raises(TeethSegmentationError, match="not cached"):
        fake_python_api.download_pretrained_weights(113)
