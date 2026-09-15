"""Pure checks for Step 4B's four immediate arch-neighbor suggestion."""

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_guide_support.py"
)


def _automatic_selection():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_automaticTemplateSupportSelection"
    )
    namespace = {}
    exec(
        compile(ast.Module([method], type_ignores=[]), str(SOURCE), "exec"),
        namespace,
    )
    return namespace["_automaticTemplateSupportSelection"]


def _records(fdi_numbers):
    return [
        {"fdiNumber": fdi, "segmentId": f"seg-{fdi}"}
        for fdi in fdi_numbers
    ]


@pytest.mark.parametrize(
    ("target", "present", "expected_fdi", "expected_ids", "missing", "complete"),
    [
        (
            "31",
            ["31", "32", "33", "41", "42"],
            ["42", "41", "32", "33"],
            ["seg-42", "seg-41", "seg-32", "seg-33"],
            [],
            True,
        ),
        (
            "36",
            ["34", "35", "36", "37", "38"],
            ["34", "35", "37", "38"],
            ["seg-34", "seg-35", "seg-37", "seg-38"],
            [],
            True,
        ),
        (
            "14",
            ["12", "13", "14", "15", "16"],
            ["16", "15", "13", "12"],
            ["seg-16", "seg-15", "seg-13", "seg-12"],
            [],
            True,
        ),
        (
            "31",
            ["31", "33", "41", "42"],
            ["42", "41", "32", "33"],
            ["seg-42", "seg-41", "seg-33"],
            ["32"],
            False,
        ),
        (
            "48",
            ["45", "46", "47", "48"],
            ["47", "46"],
            ["seg-47", "seg-46"],
            [],
            False,
        ),
    ],
)
def test_suggests_exact_arch_positions_without_crossing_or_skipping(
    target,
    present,
    expected_fdi,
    expected_ids,
    missing,
    complete,
):
    result = _automatic_selection()(target, _records(present))

    assert result["expectedFdiNumbers"] == expected_fdi
    assert result["supportSegmentIds"] == expected_ids
    assert result["missingFdiNumbers"] == missing
    assert result["complete"] is complete
