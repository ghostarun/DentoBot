from pathlib import Path

import nibabel as nib
import numpy as np

from dentobot_inference.roundtrip import run_roundtrip


def test_roundtrip_preserves_data_and_geometry(tmp_path: Path):
    input_path = tmp_path / "input.nii.gz"
    output_path = tmp_path / "output.nii.gz"
    result_path = tmp_path / "result.json"
    affine = np.array(
        [
            [-0.4, 0.0, 0.0, 12.0],
            [0.0, -0.5, 0.0, -8.0],
            [0.0, 0.0, 0.6, 4.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    data = np.arange(4 * 5 * 6, dtype=np.int16).reshape((4, 5, 6))
    nib.save(nib.Nifti1Image(data, affine), input_path)

    result = run_roundtrip(
        input_path=input_path,
        output_path=output_path,
        result_json_path=result_path,
        run_id="test-run",
    )

    assert result["status"] == "ok"
    assert result["geometryMatch"] is True
    assert result["dataMatch"] is True
    assert result["backend"]["name"] == "dentobot-inference"
    assert result_path.is_file()
    assert output_path.is_file()


def test_roundtrip_records_missing_input_failure(tmp_path: Path):
    result_path = tmp_path / "result.json"

    result = run_roundtrip(
        input_path=tmp_path / "missing.nii.gz",
        output_path=tmp_path / "output.nii.gz",
        result_json_path=result_path,
        run_id="missing-input",
    )

    assert result["status"] == "error"
    assert result["geometryMatch"] is False
    assert result_path.is_file()
    assert "does not exist" in result["errors"][0]
