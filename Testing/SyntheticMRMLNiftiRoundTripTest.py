"""Synthetic, geometry-sensitive MRML/NIfTI round-trip test for Bridge B."""

import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

import numpy as np
import slicer
import vtk


DIMENSIONS_IJK = (4, 5, 6)
ARRAY_SHAPE_KJI = (6, 5, 4)
IJK_TO_RAS = (
    (0.3464101615, -0.3500000000, 0.0, 12.50),
    (0.2000000000, 0.6062177826, 0.0, -8.25),
    (0.0000000000, 0.0000000000, 1.2, 3.75),
    (0.0000000000, 0.0000000000, 0.0, 1.00),
)
MATRIX_TOLERANCE = 1e-4
TEST_ROOT = Path("/workspace/data/test-artifacts")


def matrix_from_values(values):
    matrix = vtk.vtkMatrix4x4()
    for row in range(4):
        for column in range(4):
            matrix.SetElement(row, column, values[row][column])
    return matrix


def matrix_values(volume):
    matrix = vtk.vtkMatrix4x4()
    volume.GetIJKToRASMatrix(matrix)
    return [
        [float(matrix.GetElement(row, column)) for column in range(4)]
        for row in range(4)
    ]


def synthetic_array():
    array = np.empty(ARRAY_SHAPE_KJI, dtype=np.int16)
    for k in range(ARRAY_SHAPE_KJI[0]):
        for j in range(ARRAY_SHAPE_KJI[1]):
            for i in range(ARRAY_SHAPE_KJI[2]):
                array[k, j, i] = k * 100 + j * 10 + i - 300
    return array


def array_checksum(array):
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(contiguous.tobytes()).hexdigest()


def write_json(path, document):
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def validated_artifact_directory():
    raw_path = os.environ.get("DENTOBOT_BRIDGE_B_DIR", "")
    if not raw_path:
        raise ValueError("DENTOBOT_BRIDGE_B_DIR is required")
    path = Path(raw_path).resolve()
    root = TEST_ROOT.resolve()
    if path == root or root not in path.parents:
        raise ValueError(
            f"artifact directory must be a child of {TEST_ROOT}"
        )
    path.mkdir(parents=True, exist_ok=True)
    return path


def assert_expected_volume(volume, expected):
    image = volume.GetImageData()
    if image is None:
        raise AssertionError(f"{volume.GetName()} has no image data")
    dimensions = tuple(int(value) for value in image.GetDimensions())
    if dimensions != tuple(expected["dimensionsIJK"]):
        raise AssertionError(
            f"{volume.GetName()} dimensions {dimensions} do not match "
            f"{tuple(expected['dimensionsIJK'])}"
        )
    if image.GetScalarType() != vtk.VTK_SHORT:
        raise AssertionError(
            f"{volume.GetName()} scalar type is "
            f"{image.GetScalarTypeAsString()}, expected short"
        )

    array = slicer.util.arrayFromVolume(volume)
    checksum = array_checksum(array)
    if checksum != expected["voxelSha256KJI"]:
        raise AssertionError(
            f"{volume.GetName()} voxel checksum {checksum} does not match "
            f"{expected['voxelSha256KJI']}"
        )

    actual_matrix = matrix_values(volume)
    maximum_difference = max(
        abs(actual_matrix[row][column] - expected["ijkToRas"][row][column])
        for row in range(4)
        for column in range(4)
    )
    if maximum_difference > MATRIX_TOLERANCE:
        raise AssertionError(
            f"{volume.GetName()} IJK-to-RAS maximum difference "
            f"{maximum_difference} exceeds {MATRIX_TOLERANCE}"
        )
    return {
        "dimensionsIJK": list(dimensions),
        "arrayShapeKJI": [int(value) for value in array.shape],
        "scalarType": image.GetScalarTypeAsString(),
        "scalarRange": [float(value) for value in image.GetScalarRange()],
        "voxelSha256KJI": checksum,
        "ijkToRas": actual_matrix,
        "maximumMatrixDifference": maximum_difference,
    }


def export_synthetic_volume(artifact_directory):
    input_path = artifact_directory / "input.nii.gz"
    metadata_path = artifact_directory / "slicer-export.json"
    if input_path.exists() or metadata_path.exists():
        raise FileExistsError("export artifacts already exist")

    array = synthetic_array()
    volume = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLScalarVolumeNode", "SyntheticObliqueCBCT"
    )
    slicer.util.updateVolumeFromArray(volume, array)
    volume.SetIJKToRASMatrix(matrix_from_values(IJK_TO_RAS))

    expected = {
        "schemaVersion": "1.0",
        "test": "synthetic-mrml-nifti-roundtrip",
        "coordinateSystem": "Slicer RAS",
        "dimensionsIJK": list(DIMENSIONS_IJK),
        "arrayShapeKJI": list(ARRAY_SHAPE_KJI),
        "scalarType": "short",
        "scalarRange": [float(array.min()), float(array.max())],
        "voxelSha256KJI": array_checksum(array),
        "ijkToRas": [list(row) for row in IJK_TO_RAS],
        "slicerVersion": slicer.app.applicationVersion,
    }
    assert_expected_volume(volume, expected)
    if not slicer.util.saveNode(volume, str(input_path)):
        raise RuntimeError("Slicer failed to export the synthetic NIfTI")
    write_json(metadata_path, expected)
    slicer.mrmlScene.RemoveNode(volume)
    return {
        "event": "export-passed",
        "input": str(input_path),
        "metadata": str(metadata_path),
        "expected": expected,
    }


def validate_round_trip(artifact_directory):
    input_path = artifact_directory / "input.nii.gz"
    output_path = artifact_directory / "roundtrip.nii.gz"
    export_metadata_path = artifact_directory / "slicer-export.json"
    backend_result_path = artifact_directory / "result.json"
    validation_path = artifact_directory / "slicer-validation.json"
    for path in (
        input_path,
        output_path,
        export_metadata_path,
        backend_result_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"required artifact is missing: {path}")

    expected = json.loads(export_metadata_path.read_text(encoding="utf-8"))
    backend_result = json.loads(
        backend_result_path.read_text(encoding="utf-8")
    )
    if backend_result.get("status") != "ok":
        raise AssertionError("backend round-trip status is not ok")
    if not backend_result.get("geometryMatch"):
        raise AssertionError("backend geometryMatch is false")
    if not backend_result.get("dataMatch"):
        raise AssertionError("backend dataMatch is false")

    input_volume = slicer.util.loadVolume(
        str(input_path), {"name": "SyntheticBridgeInput"}
    )
    output_volume = slicer.util.loadVolume(
        str(output_path), {"name": "SyntheticBridgeOutput"}
    )
    if input_volume is None or output_volume is None:
        raise RuntimeError("Slicer failed to import a round-trip volume")

    dentobot_module_path = (
        "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow"
    )
    if dentobot_module_path not in sys.path:
        sys.path.insert(0, dentobot_module_path)
    from DENTOWorkflow import DENTOWorkflowLogic

    input_validation = assert_expected_volume(input_volume, expected)
    output_validation = assert_expected_volume(output_volume, expected)
    DENTOWorkflowLogic.validateMatchingVolumeGeometry(
        input_volume,
        output_volume,
        tolerance=MATRIX_TOLERANCE,
        requireMatchingScalarType=True,
    )
    if not np.array_equal(
        slicer.util.arrayFromVolume(input_volume),
        slicer.util.arrayFromVolume(output_volume),
    ):
        raise AssertionError("returned voxel array differs from exported input")

    original_output_matrix = vtk.vtkMatrix4x4()
    output_volume.GetIJKToRASMatrix(original_output_matrix)
    perturbed_output_matrix = vtk.vtkMatrix4x4()
    perturbed_output_matrix.DeepCopy(original_output_matrix)
    perturbed_output_matrix.SetElement(
        0,
        3,
        perturbed_output_matrix.GetElement(0, 3) + 0.01,
    )
    output_volume.SetIJKToRASMatrix(perturbed_output_matrix)
    negative_geometry_rejection_passed = False
    try:
        DENTOWorkflowLogic.validateMatchingVolumeGeometry(
            input_volume,
            output_volume,
            tolerance=MATRIX_TOLERANCE,
            requireMatchingScalarType=True,
        )
    except ValueError:
        negative_geometry_rejection_passed = True
    finally:
        output_volume.SetIJKToRASMatrix(original_output_matrix)
    if not negative_geometry_rejection_passed:
        raise AssertionError(
            "DENTOWorkflow accepted deliberately perturbed geometry"
        )

    result = {
        "schemaVersion": "1.0",
        "event": "validation-passed",
        "backendStatus": backend_result["status"],
        "backendGeometryMatch": backend_result["geometryMatch"],
        "backendDataMatch": backend_result["dataMatch"],
        "negativeGeometryRejectionPassed": (
            negative_geometry_rejection_passed
        ),
        "input": input_validation,
        "output": output_validation,
    }
    write_json(validation_path, result)
    slicer.mrmlScene.RemoveNode(input_volume)
    slicer.mrmlScene.RemoveNode(output_volume)
    return result


exit_code = 1
try:
    mode = os.environ.get("DENTOBOT_BRIDGE_B_MODE", "")
    artifact_directory = validated_artifact_directory()
    if mode == "export":
        result = export_synthetic_volume(artifact_directory)
    elif mode == "validate":
        result = validate_round_trip(artifact_directory)
    else:
        raise ValueError(
            "DENTOBOT_BRIDGE_B_MODE must be 'export' or 'validate'"
        )
    print(json.dumps(result, sort_keys=True), flush=True)
    exit_code = 0
except Exception as error:
    print(
        json.dumps(
            {
                "event": "failed",
                "errorType": type(error).__name__,
                "message": str(error),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    traceback.print_exc()
finally:
    vtk.vtkDebugLeaks.SetExitError(False)
    slicer.app.quit()
    sys.exit(exit_code)
