"""Host checks for the new package's production isolation boundary."""

import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
sys.path.insert(0, str(PYTHON))

from dentobot_case.contracts import CHECKPOINTS


def test_descriptors_reference_real_persisted_fields_and_owners():
    tree = ast.parse((PYTHON / "dentobot_workflow/parameter_state.py").read_text())
    fields = {node.target.id for node in ast.walk(tree)
              if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
    for checkpoint in CHECKPOINTS:
        assert set(checkpoint.artifact_roles + checkpoint.parameter_fields) <= fields
        owner = PYTHON / "dentobot_workflow" / (checkpoint.readiness_owner + ".py")
        assert owner.is_file() or (PYTHON / (checkpoint.readiness_owner + ".py")).is_file()


def test_core_import_has_no_runtime_or_file_side_effects(tmp_path):
    code = f"""
import os, sys
sys.path.insert(0, {str(PYTHON)!r})
import dentobot_case
from dentobot_case import contracts, lineage, catalog
assert not any(name in sys.modules for name in
               ('slicer', 'qt', 'vtk', 'rclpy', 'DENTOCaseBundle', 'DENTOStep6State'))
assert os.listdir('.') == []
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_existing_startup_does_not_eagerly_import_dentocase():
    files = [ROOT / "DENTOWorkflow/DENTOWorkflow.py",
             PYTHON / "dentobot_workflow/widget_bootstrap.py",
             PYTHON / "dentobot_workflow/widget_case_backend.py"]
    for path in files:
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.Import):
                assert all(not item.name.startswith("dentobot_case") for item in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("dentobot_case")
