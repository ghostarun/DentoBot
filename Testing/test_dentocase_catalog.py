"""Focused tests for the explicit DentoCase inspector and local catalog."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import (  # noqa: E402
    CASE_BUNDLE_SCHEMA_VERSION,
    MANIFEST_MEMBER,
    build_robot_profile,
    create_case_bundle,
)
from DENTOStep6State import JOINT_NAMES, build_manual_simulation_record  # noqa: E402
from dentobot_case import catalog as catalog_module  # noqa: E402
from dentobot_case.catalog import Catalog  # noqa: E402
from dentobot_case.contracts import CaseInventory  # noqa: E402
from dentobot_case.inspection import inspect_package  # noqa: E402


def _write_mrb(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Case/scene.mrml", "<MRML/>")


def _robot_profile(tmp_path: Path) -> dict:
    description = tmp_path / "description"
    (description / "urdf").mkdir(parents=True, exist_ok=True)
    (description / "meshes").mkdir(parents=True, exist_ok=True)
    (description / "urdf" / "dentobot.urdf").write_text(
        '<robot name="dentobot"/>', encoding="utf-8"
    )
    (description / "meshes" / "link.stl").write_text(
        "solid link\nendsolid link\n", encoding="utf-8"
    )
    return build_robot_profile(description)


def _make_package(
    tmp_path: Path,
    name: str,
    workflow: dict | None = None,
    *,
    schema_version: str = CASE_BUNDLE_SCHEMA_VERSION,
) -> Path:
    scene = tmp_path / f"{name}.mrb"
    _write_mrb(scene)
    return create_case_bundle(
        tmp_path / f"{name}.dentocase",
        scene,
        case_label="Saved case",
        workflow=workflow or {"schemaVersion": "1.0", "nodes": []},
        robot_profile=_robot_profile(tmp_path),
        schema_version=schema_version,
    ).path


def _rewrite_manifest(package: Path, update) -> None:
    temporary = package.with_name(package.name + ".rewrite")
    with zipfile.ZipFile(package, "r") as source:
        members = [(info, source.read(info.filename)) for info in source.infolist()]
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as output:
        for info, payload in members:
            if info.filename == MANIFEST_MEMBER:
                manifest = json.loads(payload)
                update(manifest)
                payload = (
                    json.dumps(
                        manifest,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            output.writestr(info, payload)
    temporary.replace(package)


def _manual_record(label: str) -> dict:
    return build_manual_simulation_record(
        identity={
            name: f"{label}-{name}"
            for name in (
                "prepared_branch_id",
                "task_fingerprint",
                "base_fingerprint",
                "home_fingerprint",
                "trajectory_fingerprint",
                "robot_profile_fingerprint",
                "scene_fingerprint",
            )
        },
        events=[
            {
                "kind": "requested",
                "monotonic_ns": 0,
                "requested_joints": {name: 0.0 for name in JOINT_NAMES},
            }
        ],
    )


def _inventory(
    path: Path,
    *,
    package_id: str = "package-1",
    case_id: str = "case-1",
    sha256: str = "a" * 64,
) -> CaseInventory:
    info = path.stat()
    return CaseInventory(
        path=str(path.resolve()),
        package_id=package_id,
        case_id=case_id,
        label="Saved case",
        archive_schema="1.0",
        package_sha256=sha256,
        checked_at_utc="2026-10-01T00:00:00Z",
        stat_size=info.st_size,
        stat_mtime_ns=info.st_mtime_ns,
    )


def test_inspect_schema_one_and_two_is_read_only_and_legacy_blocked(tmp_path: Path) -> None:
    schema_one = _make_package(
        tmp_path, "legacy-one", schema_version="1.0"
    )
    schema_two = _make_package(tmp_path, "legacy-two", schema_version="2.0")
    before = {path: path.read_bytes() for path in (schema_one, schema_two)}

    first = inspect_package(schema_one)
    second = inspect_package(schema_two)

    assert first.archive_schema == "1.0"
    assert second.archive_schema == "2.0"
    assert first.legacy_identity and second.legacy_identity
    assert first.case_id == f"legacy:{first.package_id}:{first.package_sha256}"
    assert not first.ownership_complete and not second.ownership_complete
    assert "Legacy package has no complete checkpoint ownership inventory" in first.unknown_ownership
    assert first.metadata["historicalRecordCount"] == 0
    assert first.metadata["studyAttemptCount"] == 0
    assert first.live_freshness == "Unverified"
    assert first.metadata["projectionValidity"] == "Unverified"
    assert first.stat_size == schema_one.stat().st_size
    assert first.package_sha256
    assert {path: path.read_bytes() for path in before} == before


def test_schema_two_saved_home_and_history_stay_display_only(tmp_path: Path) -> None:
    scene = tmp_path / "saved-home-history-record.mrb"
    _write_mrb(scene)
    profile = _robot_profile(tmp_path)
    package = create_case_bundle(
        tmp_path / "saved-home-history-record.dentocase",
        scene,
        case_label="Saved case",
        workflow={
            "schemaVersion": "1.0",
            "nodes": [],
            "step6": {
                "taskHome": {
                    "revision": 3,
                    "runtime_validation_status": "Unreviewed",
                }
            },
        },
        robot_profile=profile,
        manual_simulation_records=[_manual_record("history")],
        schema_version="2.0",
    ).path

    result = inspect_package(package)

    assert result.archive_schema == "2.0"
    assert result.historical_record_count == 1
    assert result.metadata["historicalRecordCount"] == 1
    assert result.metadata["savedHome"] == {
        "revision": 3,
        "savedRuntimeValidationStatus": "Unreviewed",
        "freshness": "Unverified",
    }
    assert result.live_freshness == "Unverified"


def test_manifest_uuid_identity_is_stable_across_package_revisions(
    tmp_path: Path,
) -> None:
    case_id = str(uuid.uuid4())
    workflow = {
        "schemaVersion": "1.0",
        "nodes": [],
        "caseIdentity": {"id": case_id},
    }
    first = _make_package(tmp_path, "revision-one", workflow)
    second = _make_package(
        tmp_path,
        "revision-two",
        workflow,
    )

    first_inventory = inspect_package(first)
    second_inventory = inspect_package(second)
    with Catalog(tmp_path / "catalog.sqlite") as catalog:
        scan_results = catalog.scan([tmp_path])
        case = catalog.list_cases()[0]

    assert first_inventory.case_id == case_id
    assert second_inventory.case_id == case_id
    assert not first_inventory.legacy_identity and not second_inventory.legacy_identity
    assert first_inventory.package_id != second_inventory.package_id
    assert len(case["package_revisions"]) == 2
    assert {item["case_id"] for item in case["package_revisions"]} == {case_id}
    assert [item["status"] for item in scan_results] == ["Valid", "Valid"]


def test_manifest_uuid_rejects_invalid_and_mismatched_case_identity(
    tmp_path: Path,
) -> None:
    invalid = _make_package(tmp_path, "invalid-case-id")
    _rewrite_manifest(invalid, lambda manifest: manifest["case"].update(id="not-a-uuid"))
    with pytest.raises(ValueError, match="manifest.case.id must be a UUID"):
        inspect_package(invalid)

    manifest_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    mismatched = _make_package(
        tmp_path,
        "mismatched-case-id",
        {"schemaVersion": "1.0", "nodes": [], "caseIdentity": {"id": workflow_id}},
    )
    _rewrite_manifest(
        mismatched, lambda manifest: manifest["case"].update(id=manifest_id)
    )
    with pytest.raises(ValueError, match="case IDs do not match"):
        inspect_package(mismatched)


def test_inspect_preserves_unknown_inventory_semantics_without_trusting_them(
    tmp_path: Path,
) -> None:
    future = _make_package(
        tmp_path,
        "future-inventory",
        {
            "schemaVersion": "1.0",
            "nodes": [],
            "checkpointInventory": {
                "schemaVersion": "1.0",
                "definitionVersion": "future-2.0",
                "unrecognizedFutureField": {"ignored": True},
            },
        },
    )

    result = inspect_package(future)

    assert result.integrity == "Valid"
    assert result.definition_version == "future-2.0"
    assert not result.ownership_complete
    assert "Unsupported checkpoint definition version: future-2.0." in result.unknown_ownership
    assert result.metadata["checkpointInventorySchemaVersion"] == "1.0"


def test_inspect_unknown_inventory_schema_does_not_require_future_fields(
    tmp_path: Path,
) -> None:
    package = _make_package(
        tmp_path,
        "future-schema",
        {
            "schemaVersion": "1.0",
            "nodes": [],
            "checkpointInventory": {
                "schemaVersion": "future-2.0",
                "definitionVersion": "99.0",
            },
        },
    )

    result = inspect_package(package)

    assert result.integrity == "Valid"
    assert result.definition_version == "99.0"
    assert not result.ownership_complete
    assert "Unsupported checkpoint inventory schema version: future-2.0." in result.unknown_ownership
    assert result.metadata["checkpointInventorySchemaVersion"] == "future-2.0"


def test_inspect_keeps_unknown_checkpoint_records_but_blocks_ownership(
    tmp_path: Path,
) -> None:
    inventory = {
        "schemaVersion": "1.0",
        "definitionVersion": "1.0",
        "targetIds": ["target-a"],
        "artifacts": [
            {
                "id": "saved-node-1",
                "checkpoint_id": "future.checkpoint",
                "scope": "target",
                "target_id": "target-a",
            }
        ],
        "branches": [],
        "ownershipComplete": True,
        "unknownOwnership": [],
    }
    package = _make_package(
        tmp_path,
        "unknown-checkpoint",
        {"schemaVersion": "1.0", "nodes": [], "checkpointInventory": inventory},
    )

    result = inspect_package(package)

    assert result.artifacts[0].checkpoint_id == "future.checkpoint"
    assert result.artifacts[0].reason == "Unknown checkpoint ID: future.checkpoint"
    assert not result.ownership_complete
    assert "Unknown checkpoint ID: future.checkpoint" in result.unknown_ownership


def test_inspect_rejects_branch_without_required_trajectory_ids(tmp_path: Path) -> None:
    package = _make_package(
        tmp_path,
        "malformed-branch",
        {
            "schemaVersion": "1.0",
            "nodes": [],
            "checkpointInventory": {
                "schemaVersion": "1.0",
                "definitionVersion": "1.0",
                "targetIds": ["target-a"],
                "artifacts": [],
                "branches": [{"id": "branch-a", "target_id": "target-a"}],
                "ownershipComplete": True,
                "unknownOwnership": [],
            },
        },
    )

    with pytest.raises(ValueError, match=r"branches\[0\] has invalid fields"):
        inspect_package(package)


def test_inspect_uses_only_populated_registry_teeth_for_fdi_summary(
    tmp_path: Path,
) -> None:
    package = _make_package(
        tmp_path,
        "registry-summary",
        {
            "schemaVersion": "1.0",
            "nodes": [],
            "step6": {
                "trajectoryRegistry": {
                    "teeth": {
                        "11": {
                            "target_id": "stable-target-11",
                            "segment_id": "segment-11",
                            "trajectory_set": {"slots": []},
                        },
                        "12": {
                            "target_id": "",
                            "segment_id": "segment-12",
                            "trajectory_set": {"slots": []},
                        },
                        "13": {
                            "target_id": "",
                            "segment_id": "",
                            "trajectory_set": {"slots": []},
                        },
                    },
                    "prepared_branches": {},
                }
            },
        },
    )

    result = inspect_package(package)
    associations = result.metadata["targetToothAssociations"]

    assert result.target_ids == ("stable-target-11",)
    assert associations == [
        {"targetId": "stable-target-11", "fdi": "FDI11", "fallbackId": False},
        {"targetId": "FDI12", "fdi": "FDI12", "fallbackId": True},
    ]


def test_inspect_marks_conflicting_target_to_fdi_association_unknown(
    tmp_path: Path,
) -> None:
    package = _make_package(
        tmp_path,
        "registry-conflict",
        {
            "schemaVersion": "1.0",
            "nodes": [],
            "step6": {
                "trajectoryRegistry": {
                    "teeth": {
                        tooth: {
                            "target_id": "duplicate-target",
                            "segment_id": f"segment-{tooth}",
                            "trajectory_set": {"slots": []},
                        }
                        for tooth in ("11", "21")
                    },
                    "prepared_branches": {},
                }
            },
        },
    )

    result = inspect_package(package)

    assert result.metadata["targetToothAssociations"] == [
        {"targetId": "duplicate-target", "fdi": "Unknown", "fallbackId": False}
    ]
    assert "Saved tooth registry has duplicate target IDs." in result.unknown_ownership


def test_legacy_duplicate_trajectory_owners_are_unknown(tmp_path: Path) -> None:
    trajectory_id = "shared-trajectory-id"
    package = _make_package(
        tmp_path,
        "trajectory-owner-conflict",
        {
            "schemaVersion": "1.0",
            "nodes": [
                {
                    "field": "trajectoryLine",
                    "id": "trajectory-node",
                    "attributes": {"DENTOBOT.RegistryTrajectoryID": trajectory_id},
                }
            ],
            "step6": {
                "trajectoryRegistry": {
                    "teeth": {
                        "11": {
                            "target_id": "target-a",
                            "segment_id": "segment-a",
                            "trajectory_set": {
                                "slots": [
                                    {"trajectory_id": trajectory_id, "target_id": "target-a"}
                                ]
                            },
                        },
                        "21": {
                            "target_id": "target-b",
                            "segment_id": "segment-b",
                            "trajectory_set": {
                                "slots": [
                                    {"trajectory_id": trajectory_id, "target_id": "target-b"}
                                ]
                            },
                        },
                    },
                    "prepared_branches": {},
                }
            },
        },
    )

    result = inspect_package(package)

    artifact = next(item for item in result.artifacts if item.id == "trajectory-node")
    assert artifact.target_id == ""
    assert "conflicting trajectory owners" in " ".join(result.unknown_ownership)


def test_inspect_surfaces_validator_error_and_detects_file_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = tmp_path / "invalid.dentocase"
    invalid.write_text("not a zip archive", encoding="utf-8")
    with pytest.raises(ValueError, match="selected file is not a DENTOBOT case bundle"):
        inspect_package(invalid)

    package = _make_package(tmp_path, "mutated-during-inspection")
    owner = sys.modules["DENTOCaseBundle"]
    original = owner.validate_case_bundle

    def mutate_after_validation(path):
        result = original(path)
        payload = Path(path).read_bytes()
        Path(path).write_bytes(payload + b"changed")
        return result

    monkeypatch.setattr(owner, "validate_case_bundle", mutate_after_validation)
    with pytest.raises(ValueError, match="changed during inspection"):
        inspect_package(package)


def test_catalog_groups_copies_and_preserves_conflicting_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "cases"
    root.mkdir()
    for name in ("a.dentocase", "b.dentocase", "c.dentocase"):
        (root / name).write_bytes(name.encode())

    def fake_inspect(path):
        path = Path(path)
        return _inventory(
            path,
            package_id="package-1",
            case_id="case-1",
            sha256="b" * 64 if path.name.startswith("c") else "a" * 64,
        )

    monkeypatch.setattr(catalog_module, "inspect_package", fake_inspect)
    with Catalog(tmp_path / "catalog.sqlite") as catalog:
        results = catalog.scan([root])
        cases = catalog.list_cases()
        package = catalog.get_package("package-1")

    assert [row["status"] for row in results] == ["Valid", "Valid", "Conflict"]
    assert len(cases) == 1
    assert len(cases[0]["package_revisions"]) == 1
    assert [row["status"] for row in package["locations"]] == [
        "Valid",
        "Valid",
        "Conflict",
    ]
    assert package["sha256"] == "a" * 64


def test_catalog_missing_then_invalid_location_never_shows_stale_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "cases"
    root.mkdir()
    package_path = root / "one.dentocase"
    package_path.write_bytes(b"valid")
    monkeypatch.setattr(
        catalog_module, "inspect_package", lambda path: _inventory(Path(path))
    )

    with Catalog(tmp_path / "catalog.sqlite") as catalog:
        catalog.scan([root])
        package_path.unlink()
        missing = catalog.scan()
        assert missing[0]["status"] == "Missing"
        assert catalog.list_cases()[0]["locations"][0]["status"] == "Missing"

        package_path.write_bytes(b"broken")
        monkeypatch.setattr(
            catalog_module,
            "inspect_package",
            lambda path: (_ for _ in ()).throw(ValueError("invalid archive")),
        )
        failed = catalog.scan()
        listed = catalog.list_cases()

    assert failed[0]["status"] == "Error"
    assert len(listed) == 1
    assert listed[0]["case_id"] is None
    assert listed[0]["package_revisions"] == []
    assert listed[0]["locations"][0]["package_id"] is None
    assert listed[0]["locations"][0]["status"] == "Error"
    assert listed[0]["locations"][0]["error"] == "invalid archive"


def test_catalog_failed_root_walk_does_not_mark_unseen_packages_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "cases"
    root.mkdir()
    package_path = root / "one.dentocase"
    package_path.write_bytes(b"valid")
    monkeypatch.setattr(
        catalog_module, "inspect_package", lambda path: _inventory(Path(path))
    )
    with Catalog(tmp_path / "catalog.sqlite") as catalog:
        catalog.scan([root])

        def failed_walk(path, *, topdown, followlinks, onerror):
            onerror(PermissionError("cannot read root"))
            yield str(path), [], []

        monkeypatch.setattr(catalog_module.os, "walk", failed_walk)
        results = catalog.scan()
        locations = [
            location
            for case in catalog.list_cases()
            for location in case["locations"]
        ]

    assert any(result["status"] == "Error" for result in results)
    package_location = next(row for row in locations if row["path"] == str(package_path.resolve()))
    root_error = next(row for row in locations if row["path"] == str(root.resolve()))
    assert package_location["status"] == "Valid"
    assert root_error["status"] == "Error"


def test_catalog_package_transaction_rolls_back_on_location_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "cases"
    root.mkdir()
    package_path = root / "one.dentocase"
    package_path.write_bytes(b"valid")
    monkeypatch.setattr(
        catalog_module, "inspect_package", lambda path: _inventory(Path(path))
    )
    with Catalog(tmp_path / "catalog.sqlite") as catalog:
        catalog.add_root(root)
        catalog._connection.execute(
            "CREATE TRIGGER reject_valid BEFORE INSERT ON locations "
            "WHEN NEW.status = 'Valid' BEGIN SELECT RAISE(ABORT, 'test failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="test failure"):
            catalog.scan()
        assert catalog._connection.execute("SELECT count(*) FROM packages").fetchone()[0] == 0
        assert catalog._connection.execute("SELECT count(*) FROM locations").fetchone()[0] == 0


def test_catalog_rejects_incompatible_database_version_without_rewriting(
    tmp_path: Path,
) -> None:
    database = tmp_path / "future.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 9")
        connection.execute("CREATE TABLE sentinel(value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('preserve')")
    before = database.read_bytes()

    with pytest.raises(ValueError, match="Unsupported catalog database version: 9"):
        Catalog(database)

    assert database.read_bytes() == before


def test_catalog_rejects_matching_column_names_with_wrong_constraints(
    tmp_path: Path,
) -> None:
    database = tmp_path / "bad-schema.sqlite"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE roots(path TEXT PRIMARY KEY);
            CREATE TABLE packages(
                package_id TEXT PRIMARY KEY NOT NULL,
                sha256 TEXT NOT NULL,
                case_id TEXT NOT NULL,
                inventory_json TEXT NOT NULL
            );
            CREATE TABLE locations(
                path TEXT PRIMARY KEY NOT NULL,
                root_path TEXT NOT NULL REFERENCES roots(path) ON DELETE CASCADE,
                package_id TEXT REFERENCES packages(package_id) ON DELETE SET NULL,
                status TEXT NOT NULL,
                error TEXT,
                size INTEGER,
                mtime INTEGER,
                checked_at TEXT NOT NULL
            );
            PRAGMA user_version = 1;
            """
        )
    before = database.read_bytes()

    with pytest.raises(ValueError, match="incompatible catalog schema"):
        Catalog(database)

    assert database.read_bytes() == before


def test_catalog_revalidate_rejects_changed_identity_and_conflict_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "cases"
    root.mkdir()
    package_path = root / "one.dentocase"
    package_path.write_bytes(b"valid")
    current = {"package_id": "package-1", "sha256": "a" * 64}
    inspected: list[Path] = []

    def fake_inspect(path):
        inspected.append(Path(path))
        return _inventory(
            Path(path),
            package_id=current["package_id"],
            sha256=current["sha256"],
        )

    monkeypatch.setattr(catalog_module, "inspect_package", fake_inspect)
    with Catalog(tmp_path / "catalog.sqlite") as catalog:
        catalog.scan([root])
        current["package_id"] = "package-2"
        with pytest.raises(ValueError, match="different package ID"):
            catalog.revalidate(package_path)

        current.update(package_id="package-1", sha256="a" * 64)
        catalog._connection.execute(
            "UPDATE locations SET status='Conflict' WHERE path=?",
            (str(package_path.resolve()),),
        )
        count = len(inspected)
        with pytest.raises(ValueError, match="Indexed location is Conflict"):
            catalog.revalidate(package_path)

        conflict_copy = root / "unindexed.dentocase"
        conflict_copy.write_bytes(b"different")
        current["sha256"] = "b" * 64
        with pytest.raises(ValueError, match="different trusted identity"):
            catalog.revalidate(conflict_copy)

    assert len(inspected) == count + 2


def test_catalog_list_marks_stat_changed_and_scan_skips_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "cases"
    root.mkdir()
    package_path = root / "one.dentocase"
    package_path.write_bytes(b"valid")
    monkeypatch.setattr(
        catalog_module, "inspect_package", lambda path: _inventory(Path(path))
    )
    try:
        (root / "linked.dentocase").symlink_to(package_path)
        (root / "linked-dir").symlink_to(root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with Catalog(tmp_path / "catalog.sqlite") as catalog:
        results = catalog.scan([root])
        package_path.write_bytes(b"changed-size")
        location = catalog.get_package("package-1")["locations"][0]

    assert len(results) == 1
    assert results[0]["status"] == "Valid"
    assert location["status"] == "Changed"


def test_catalog_rejects_symlink_scan_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    try:
        linked_root.symlink_to(real_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with Catalog(tmp_path / "catalog.sqlite") as catalog:
        with pytest.raises(ValueError, match="existing directory"):
            catalog.add_root(linked_root)


def test_cli_inspect_emits_json_without_creating_catalog(tmp_path: Path, capsys) -> None:
    from dentobot_case.__main__ import main

    package = _make_package(tmp_path, "cli-inspect")
    database = tmp_path / "unused.sqlite"

    code = main(["inspect", str(package)])
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["package_id"]
    assert not database.exists()


def test_plain_package_import_has_no_owner_or_runtime_imports(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(HELPERS)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    script = (
        "import sys, dentobot_case; "
        "blocked = ('DENTOCaseBundle', 'DENTOStep6State', 'slicer', 'qt', 'vtk', 'rclpy'); "
        "assert not any(name in sys.modules for name in blocked)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
