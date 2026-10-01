"""Explicit SQLite catalog for trusted DentoCase inventories and previews."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Iterable
import zipfile

from .contracts import CaseInventory
from .inspection import inspect_discovery, inspect_package


_CATALOG_VERSION = 2
_BATCH_SIZE = 50
_V1_SCHEMA = {
    "roots": (("path", "TEXT", 1, 1),),
    "packages": (
        ("package_id", "TEXT", 1, 1),
        ("sha256", "TEXT", 1, 0),
        ("case_id", "TEXT", 1, 0),
        ("inventory_json", "TEXT", 1, 0),
    ),
    "locations": (
        ("path", "TEXT", 1, 1),
        ("root_path", "TEXT", 1, 0),
        ("package_id", "TEXT", 0, 0),
        ("status", "TEXT", 1, 0),
        ("error", "TEXT", 0, 0),
        ("size", "INTEGER", 0, 0),
        ("mtime", "INTEGER", 0, 0),
        ("checked_at", "TEXT", 1, 0),
    ),
}
_TABLE_SCHEMA = {
    "roots": _V1_SCHEMA["roots"],
    "packages": _V1_SCHEMA["packages"] + (
        ("label", "TEXT", 1, 0),
        ("saved_at_utc", "TEXT", 0, 0),
        ("teeth_json", "TEXT", 1, 0),
        ("workflow_status", "TEXT", 1, 0),
    ),
    "locations": _V1_SCHEMA["locations"] + (
        ("dev", "INTEGER", 0, 0),
        ("ino", "INTEGER", 0, 0),
        ("ctime_ns", "INTEGER", 0, 0),
    ),
    "discoveries": (
        ("path", "TEXT", 1, 1),
        ("claimed_package_id", "TEXT", 0, 0),
        ("claimed_case_id", "TEXT", 0, 0),
        ("label", "TEXT", 1, 0),
        ("saved_at_utc", "TEXT", 0, 0),
        ("teeth_json", "TEXT", 1, 0),
        ("workflow_status", "TEXT", 1, 0),
        ("metadata_json", "TEXT", 1, 0),
    ),
}


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _signature(info) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _encoded(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _preview_status(preview: object) -> str:
    states = []
    if isinstance(preview, list):
        states = [
            item.get("state", "").strip().casefold()
            for item in preview
            if isinstance(item, dict) and isinstance(item.get("state", ""), str)
        ]
    if any(state == "stale" for state in states):
        return "Stale"
    if any(state in {"incomplete", "blocked"} for state in states):
        return "Incomplete"
    if not states:
        return "Missing"
    if len(states) != len(preview) or any(state != "current" for state in states):
        return "Unknown"
    return "Current"


def _inventory_fields(inventory: CaseInventory) -> tuple[str, str | None, list[str], str]:
    metadata = inventory.metadata if isinstance(inventory.metadata, dict) else {}
    saved_at = metadata.get("saved_at_utc")
    saved_at = saved_at if isinstance(saved_at, str) and saved_at else None
    teeth = metadata.get("teeth")
    if not isinstance(teeth, list):
        teeth = sorted({
            fdi.strip().upper() if fdi.strip().upper().startswith("FDI") else f"FDI{fdi.strip()}"
            for item in metadata.get("targetToothAssociations", ())
            if isinstance(item, dict) and isinstance((fdi := item.get("fdi")), str)
            and fdi.strip() and fdi.strip().casefold() != "unknown"
        })
    teeth = sorted({item for item in teeth if isinstance(item, str) and item})
    workflow_status = metadata.get("workflow_status")
    if not isinstance(workflow_status, str):
        preview = metadata.get("checkpointPreview")
        if preview is None:
            preview = [
                {"state": artifact.state}
                for artifact in inventory.artifacts
            ]
        workflow_status = _preview_status(preview)
    return inventory.label or "Unknown", saved_at, teeth, workflow_status


def _inventory_discovery(inventory: CaseInventory) -> dict:
    label, saved_at, teeth, workflow_status = _inventory_fields(inventory)
    metadata = dict(inventory.metadata) if isinstance(inventory.metadata, dict) else {}
    metadata.update({
        "saved_at_utc": saved_at,
        "teeth": teeth,
        "workflow_status": workflow_status,
        "trusted": True,
    })
    return {
        "path": inventory.path,
        "package_id": inventory.package_id,
        "case_id": inventory.case_id,
        "label": label,
        "saved_at_utc": saved_at,
        "teeth": teeth,
        "workflow_status": workflow_status,
        "metadata": metadata,
    }


class Catalog:
    """An explicitly opened local catalog; scanning is always caller-driven."""

    def __init__(self, db_path: str | Path):
        path = Path(db_path).expanduser()
        if path.suffix.lower() == ".dentocase" or (
            path.exists() and path.is_file() and zipfile.is_zipfile(path)
        ):
            raise ValueError("The catalog database path cannot be a DentoCase archive.")
        if not path.parent.exists() or not path.parent.is_dir():
            raise ValueError("The catalog database parent directory must exist.")
        if path.exists() and path.is_dir():
            raise ValueError("The catalog database path must be a file.")
        self.db_path = path.resolve()
        self._connection = sqlite3.connect(str(self.db_path))
        self._connection.row_factory = sqlite3.Row
        self._connection.create_function("basename", 1, lambda value: Path(value).name if value else "")
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._initialize_or_validate()
        except Exception:
            self._connection.close()
            raise

    def _objects(self) -> set[tuple[str, str]]:
        return {
            (row["type"], row["name"])
            for row in self._connection.execute(
                "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        }

    def _validate_schema(self, schema: dict, tables: set[str]) -> None:
        if self._objects() != {("table", table) for table in tables}:
            raise ValueError("The existing database has an incompatible catalog schema.")
        for table, expected in schema.items():
            columns = tuple(
                (row["name"], row["type"].upper(), row["notnull"], row["pk"])
                for row in self._connection.execute(f"PRAGMA table_info({table})")
            )
            if columns != expected:
                raise ValueError("The existing database has an incompatible catalog schema.")
        location_keys = {
            (row["table"], row["from"], row["to"], row["on_delete"])
            for row in self._connection.execute("PRAGMA foreign_key_list(locations)")
        }
        expected_location_keys = {
            ("roots", "root_path", "path", "CASCADE"),
            ("packages", "package_id", "package_id", "SET NULL"),
        }
        if location_keys != expected_location_keys:
            raise ValueError("The existing database has incompatible catalog relationships.")
        if "discoveries" in tables:
            discovery_keys = {
                (row["table"], row["from"], row["to"], row["on_delete"])
                for row in self._connection.execute("PRAGMA foreign_key_list(discoveries)")
            }
            if discovery_keys != {("locations", "path", "path", "CASCADE")}:
                raise ValueError("The existing database has incompatible catalog relationships.")

    def _initialize_or_validate(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 0:
            if self._objects():
                raise ValueError("The existing database has no compatible catalog version.")
            self._create_schema()
            return
        if version == 1:
            self._validate_schema(_V1_SCHEMA, set(_V1_SCHEMA))
            self._migrate_v1()
            version = _CATALOG_VERSION
        if version != _CATALOG_VERSION:
            raise ValueError(f"Unsupported catalog database version: {version}.")
        self._validate_schema(_TABLE_SCHEMA, set(_TABLE_SCHEMA))

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE roots (path TEXT PRIMARY KEY NOT NULL);
            CREATE TABLE packages (
                package_id TEXT PRIMARY KEY NOT NULL,
                sha256 TEXT NOT NULL,
                case_id TEXT NOT NULL,
                inventory_json TEXT NOT NULL,
                label TEXT NOT NULL,
                saved_at_utc TEXT,
                teeth_json TEXT NOT NULL,
                workflow_status TEXT NOT NULL
            );
            CREATE TABLE locations (
                path TEXT PRIMARY KEY NOT NULL,
                root_path TEXT NOT NULL REFERENCES roots(path) ON DELETE CASCADE,
                package_id TEXT REFERENCES packages(package_id) ON DELETE SET NULL,
                status TEXT NOT NULL,
                error TEXT,
                size INTEGER,
                mtime INTEGER,
                checked_at TEXT NOT NULL,
                dev INTEGER,
                ino INTEGER,
                ctime_ns INTEGER
            );
            CREATE TABLE discoveries (
                path TEXT PRIMARY KEY NOT NULL REFERENCES locations(path) ON DELETE CASCADE,
                claimed_package_id TEXT,
                claimed_case_id TEXT,
                label TEXT NOT NULL,
                saved_at_utc TEXT,
                teeth_json TEXT NOT NULL,
                workflow_status TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            PRAGMA user_version = 2;
            COMMIT;
            """
        )

    def _migrate_v1(self) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute("ALTER TABLE packages ADD COLUMN label TEXT NOT NULL DEFAULT 'Unknown'")
            self._connection.execute("ALTER TABLE packages ADD COLUMN saved_at_utc TEXT")
            self._connection.execute("ALTER TABLE packages ADD COLUMN teeth_json TEXT NOT NULL DEFAULT '[]'")
            self._connection.execute("ALTER TABLE packages ADD COLUMN workflow_status TEXT NOT NULL DEFAULT 'Missing'")
            self._connection.execute("ALTER TABLE locations ADD COLUMN dev INTEGER")
            self._connection.execute("ALTER TABLE locations ADD COLUMN ino INTEGER")
            self._connection.execute("ALTER TABLE locations ADD COLUMN ctime_ns INTEGER")
            self._connection.execute(
                "CREATE TABLE discoveries ("
                "path TEXT PRIMARY KEY NOT NULL REFERENCES locations(path) ON DELETE CASCADE,"
                "claimed_package_id TEXT, claimed_case_id TEXT, label TEXT NOT NULL,"
                "saved_at_utc TEXT, teeth_json TEXT NOT NULL, workflow_status TEXT NOT NULL,"
                "metadata_json TEXT NOT NULL)"
            )
            rows = self._connection.execute(
                "SELECT package_id, inventory_json FROM packages"
            ).fetchall()
            for row in rows:
                inventory = CaseInventory.from_dict(json.loads(row["inventory_json"]))
                label, saved_at, teeth, workflow_status = _inventory_fields(inventory)
                self._connection.execute(
                    "UPDATE packages SET label=?, saved_at_utc=?, teeth_json=?, workflow_status=? "
                    "WHERE package_id=?",
                    (label, saved_at, _encoded(teeth), workflow_status, row["package_id"]),
                )
            self._connection.execute("PRAGMA user_version = 2")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        if getattr(self, "_connection", None) is not None:
            self._connection.close()
            self._connection = None

    def add_root(self, path: str | Path) -> str:
        selected = Path(path).expanduser()
        lexical = Path(os.path.abspath(selected))
        try:
            root = lexical.resolve(strict=True)
        except OSError as exc:
            raise ValueError("Scan root must be an existing directory.") from exc
        if lexical != root or not root.is_dir():
            raise ValueError("Scan root must be an existing directory.")
        resolved = str(root)
        with self._connection:
            self._connection.execute(
                "INSERT INTO roots(path) VALUES (?) ON CONFLICT(path) DO NOTHING",
                (resolved,),
            )
        return resolved

    def _registered_roots(self) -> list[str]:
        return [row["path"] for row in self._connection.execute("SELECT path FROM roots ORDER BY path")]

    def _location(self, path: str) -> sqlite3.Row | None:
        return self._connection.execute("SELECT * FROM locations WHERE path=?", (path,)).fetchone()

    def _same_signature(self, row: sqlite3.Row | None, info) -> bool:
        return bool(
            row is not None
            and row["dev"] is not None
            and row["ino"] is not None
            and row["ctime_ns"] is not None
            and (row["dev"], row["ino"], row["size"], row["mtime"], row["ctime_ns"])
            == _signature(info)
        )

    def _prepare_file(self, path: Path, root_path: str, validation: str) -> dict:
        try:
            resolved = str(path.resolve())
            info = path.lstat()
        except OSError as exc:
            reason = self._failure_reason(exc)
            return {
                "result": {"path": str(path.absolute()), "root_path": root_path,
                           "status": "Error", "error": reason},
                "action": {"kind": "error", "path": str(path.absolute()),
                           "root_path": root_path, "error": reason, "stat": None},
            }
        if not stat.S_ISREG(info.st_mode):
            return {"result": {"path": resolved, "root_path": root_path, "status": "Skipped"}}
        existing = self._location(resolved)
        same = self._same_signature(existing, info)
        discovery_exists = self._connection.execute(
            "SELECT 1 FROM discoveries WHERE path=?", (resolved,)
        ).fetchone() is not None
        if (
            validation == "metadata"
            and same
            and discovery_exists
            and existing["status"] in {"Valid", "Conflict", "Unchecked", "Changed"}
        ):
            result = {"path": resolved, "root_path": root_path, "status": existing["status"]}
            if existing["package_id"]:
                result["package_id"] = existing["package_id"]
            return {"result": result, "action": None}
        try:
            if validation == "full":
                inventory = inspect_package(path)
                after = Path(inventory.path).stat()
                if _signature(info) != _signature(after):
                    raise ValueError("DentoCase file changed during inspection.")
                discovery = _inventory_discovery(inventory)
                action = {"kind": "verified", "inventory": inventory, "discovery": discovery, "stat": after}
                result = {
                    "path": resolved,
                    "root_path": root_path,
                    "package_id": inventory.package_id,
                    "case_id": inventory.case_id,
                    "sha256": inventory.package_sha256,
                    "status": "Valid",
                }
            else:
                discovery = inspect_discovery(path)
                after = Path(resolved).stat()
                if _signature(info) != _signature(after):
                    raise ValueError("DentoCase file changed during inspection.")
                preserve = bool(existing is not None and existing["package_id"])
                if not preserve:
                    status = "Unchecked"
                elif existing["status"] == "Conflict":
                    status = "Conflict"
                elif same and existing["status"] == "Valid":
                    status = "Valid"
                else:
                    status = "Changed"
                action = {
                    "kind": "discovery",
                    "discovery": discovery,
                    "stat": after,
                    "package_id": existing["package_id"] if preserve else None,
                    "status": status,
                }
                result = {"path": resolved, "root_path": root_path, "status": status}
                if preserve:
                    result["package_id"] = existing["package_id"]
            return {"result": result, "action": action}
        except Exception as exc:
            reason = self._failure_reason(exc)
            return {
                "result": {"path": resolved, "root_path": root_path, "status": "Error", "error": reason},
                "action": {"kind": "error", "path": resolved, "root_path": root_path, "error": reason, "stat": info},
            }

    @staticmethod
    def _failure_reason(error: Exception) -> str:
        if isinstance(error, (ValueError, RuntimeError)):
            return str(error) or type(error).__name__
        return f"Package inspection failed ({type(error).__name__})."

    def _write_location(self, path: str, root: str, package_id: str | None, status: str,
                        error: str | None, info, checked_at: str) -> None:
        values = (
            info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino, info.st_ctime_ns
        ) if info is not None else (None, None, None, None, None)
        self._connection.execute(
            """INSERT INTO locations
               (path,root_path,package_id,status,error,size,mtime,checked_at,dev,ino,ctime_ns)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET root_path=excluded.root_path,
                 package_id=excluded.package_id,status=excluded.status,error=excluded.error,
                 size=excluded.size,mtime=excluded.mtime,checked_at=excluded.checked_at,
                 dev=excluded.dev,ino=excluded.ino,ctime_ns=excluded.ctime_ns""",
            (path, root, package_id, status, error, values[0], values[1],
             checked_at, values[2], values[3], values[4]),
        )

    def _write_discovery(self, discovery: dict) -> None:
        metadata = discovery.get("metadata", {})
        self._connection.execute(
            """INSERT INTO discoveries
               (path,claimed_package_id,claimed_case_id,label,saved_at_utc,teeth_json,
                workflow_status,metadata_json) VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET claimed_package_id=excluded.claimed_package_id,
                 claimed_case_id=excluded.claimed_case_id,label=excluded.label,
                 saved_at_utc=excluded.saved_at_utc,teeth_json=excluded.teeth_json,
                 workflow_status=excluded.workflow_status,metadata_json=excluded.metadata_json""",
            (discovery["path"], discovery.get("package_id") or None,
             discovery.get("case_id") or None,
             (discovery.get("label") if discovery.get("label") != "Unknown"
              else Path(discovery["path"]).stem or "Unknown"),
             discovery.get("saved_at_utc"), _encoded(discovery.get("teeth", [])),
             discovery.get("workflow_status", "Unknown"), _encoded(metadata)),
        )

    def _apply_batch(self, batch: list[dict]) -> list[dict]:
        results = []
        with self._connection:
            for item in batch:
                result = item["result"]
                action = item.get("action")
                if action is None or action.get("kind") == "skipped":
                    results.append(result)
                    continue
                kind = action["kind"]
                if kind == "error":
                    self._write_location(action["path"], action["root_path"], None,
                                         "Error", action["error"], action["stat"], _utc_now())
                    self._connection.execute("DELETE FROM discoveries WHERE path=?", (action["path"],))
                elif kind == "discovery":
                    self._write_location(action["discovery"]["path"], result["root_path"],
                                         action["package_id"], action["status"], None,
                                         action["stat"], _utc_now())
                    self._write_discovery(action["discovery"])
                else:
                    inventory = action["inventory"]
                    row = self._connection.execute(
                        "SELECT sha256,case_id FROM packages WHERE package_id=?",
                        (inventory.package_id,),
                    ).fetchone()
                    if row is not None and (row["sha256"] != inventory.package_sha256
                                            or row["case_id"] != inventory.case_id):
                        reason = "Package ID already has a different trusted content identity."
                        self._write_location(inventory.path, result["root_path"], inventory.package_id,
                                             "Conflict", reason, action["stat"], inventory.checked_at_utc)
                        result.update(status="Conflict", error=reason)
                    else:
                        label, saved_at, teeth, workflow_status = _inventory_fields(inventory)
                        self._connection.execute(
                            """INSERT INTO packages
                               (package_id,sha256,case_id,inventory_json,label,saved_at_utc,teeth_json,workflow_status)
                               VALUES (?,?,?,?,?,?,?,?)
                               ON CONFLICT(package_id) DO UPDATE SET sha256=excluded.sha256,
                                 case_id=excluded.case_id,inventory_json=excluded.inventory_json,
                                 label=excluded.label,saved_at_utc=excluded.saved_at_utc,
                                 teeth_json=excluded.teeth_json,workflow_status=excluded.workflow_status""",
                            (inventory.package_id, inventory.package_sha256, inventory.case_id,
                             _encoded(inventory.to_dict()), label, saved_at, _encoded(teeth), workflow_status),
                        )
                        self._write_location(inventory.path, result["root_path"], inventory.package_id,
                                             "Valid", None, action["stat"], inventory.checked_at_utc)
                    self._write_discovery(action["discovery"])
                results.append(result)
        return results

    def _progress(self, callback, *, root: str, path: str | None, processed: int,
                  status: str, event: str = "package") -> None:
        if callback is not None:
            callback({"event": event, "root": root, "path": path,
                      "processed": processed, "status": status})

    def _record_root_error(self, root: str, error: Exception) -> dict:
        reason = f"Root traversal failed ({type(error).__name__})."
        try:
            info = Path(root).lstat()
        except OSError:
            info = None
        if root in self._registered_roots():
            with self._connection:
                self._write_location(root, root, None, "Error", reason, info, _utc_now())
        return {"path": root, "root_path": root, "status": "Error", "error": reason}

    def _clear_root_error(self, root: str) -> None:
        with self._connection:
            self._connection.execute(
                "DELETE FROM locations WHERE path=? AND root_path=? AND package_id IS NULL",
                (root, root),
            )

    def _mark_missing(self, root: str, found: set[str]) -> list[dict]:
        rows = self._connection.execute(
            "SELECT path,package_id FROM locations WHERE root_path=? AND path!=? ORDER BY path",
            (root, root),
        ).fetchall()
        missing = []
        with self._connection:
            for row in rows:
                if row["path"] in found:
                    continue
                self._connection.execute(
                    "UPDATE locations SET status='Missing',error='Not found during successful scan',checked_at=? "
                    "WHERE path=? AND root_path=?",
                    (_utc_now(), row["path"], root),
                )
                missing.append({"path": row["path"], "root_path": root,
                                "package_id": row["package_id"], "status": "Missing",
                                "error": "Not found during successful scan"})
        return missing

    def scan(self, roots: Iterable[str | Path] | str | Path | None = None, *,
             validation: str = "full", progress=None, cancelled=None) -> list[dict]:
        """Scan explicitly selected roots; metadata mode stores display-only previews."""
        if validation not in {"full", "metadata"}:
            raise ValueError("validation must be 'full' or 'metadata'.")
        if progress is not None and not callable(progress):
            raise TypeError("progress must be callable.")
        if cancelled is not None and not callable(cancelled):
            raise TypeError("cancelled must be callable.")
        if roots is None:
            root_paths = self._registered_roots()
        else:
            selected = [roots] if isinstance(roots, (str, Path)) else list(roots)
            root_paths = []
            for root in selected:
                try:
                    root_paths.append(self.add_root(root))
                except (OSError, ValueError):
                    root_paths.append(str(Path(root).expanduser()))
            root_paths = sorted(set(root_paths))

        results: list[dict] = []
        seen_paths: set[str] = set()
        processed_total = 0
        was_cancelled = False
        for root in root_paths:
            if cancelled and cancelled():
                results.append({"path": root, "root_path": root, "status": "Cancelled"})
                was_cancelled = True
                break
            found: set[str] = set()
            walk_errors: list[Exception] = []
            pending: list[dict] = []
            cancelled_root = False
            invalid_root = not Path(root).is_dir()
            if invalid_root:
                walk_errors.append(FileNotFoundError("scan root is unavailable"))
            else:
                for directory, dirs, filenames in os.walk(
                    root, topdown=True, followlinks=False, onerror=walk_errors.append
                ):
                    if cancelled and cancelled():
                        cancelled_root = True
                        break
                    current = Path(directory)
                    dirs[:] = sorted(name for name in dirs if not (current / name).is_symlink())
                    for filename in sorted(filenames):
                        if cancelled and cancelled():
                            cancelled_root = True
                            break
                        path = current / filename
                        if path.suffix.lower() != ".dentocase" or path.is_symlink():
                            continue
                        try:
                            if not stat.S_ISREG(path.lstat().st_mode):
                                continue
                            resolved = str(path.resolve())
                        except OSError:
                            resolved = str(path.absolute())
                        found.add(resolved)
                        if resolved in seen_paths:
                            continue
                        seen_paths.add(resolved)
                        pending.append(self._prepare_file(path, root, validation))
                        processed_total += 1
                        if len(pending) >= _BATCH_SIZE:
                            last_path = pending[-1]["result"].get("path")
                            results.extend(self._apply_batch(pending))
                            pending.clear()
                            self._progress(progress, root=root, path=last_path,
                                           processed=processed_total, status="Scanning")
                    if cancelled_root:
                        break
            if pending:
                results.extend(self._apply_batch(pending))
            if walk_errors:
                results.append(self._record_root_error(root, walk_errors[0]))
            elif cancelled_root or (cancelled and cancelled()):
                cancelled_root = True
                was_cancelled = True
                results.append({"path": root, "root_path": root, "status": "Cancelled"})
            else:
                self._clear_root_error(root)
                results.extend(self._mark_missing(root, found))
            if cancelled_root:
                break
        self._progress(
            progress, root=root_paths[-1] if root_paths else "", path=None,
            processed=processed_total,
            status="Cancelled" if was_cancelled else "Complete", event="complete",
        )
        return sorted(results, key=lambda item: (item.get("path", ""), item.get("status", "")))

    @staticmethod
    def _effective_location(row: sqlite3.Row) -> dict:
        result = dict(row)
        if result["path"] == result["root_path"] and result["status"] == "Error":
            return result
        path = Path(result["path"])
        try:
            info = path.lstat()
        except OSError:
            result["status"] = "Missing"
            result["error"] = "Location is not present on disk; scan required."
            return result
        if stat.S_ISLNK(info.st_mode):
            result["status"] = "Changed"
            result["error"] = "Location is now a symbolic link; scan required."
        elif (
            result["status"] == "Missing"
            or not stat.S_ISREG(info.st_mode)
            or result["size"] is None
            or result["mtime"] is None
            or result["dev"] is None
            or result["ino"] is None
            or result["ctime_ns"] is None
            or (result["dev"], result["ino"], result["size"], result["mtime"], result["ctime_ns"])
               != _signature(info)
        ):
            result["status"] = "Changed"
            result["error"] = "File identity or modification time changed; scan required."
        return result

    def _all_locations(self) -> list[dict]:
        return [self._effective_location(row) for row in self._connection.execute(
            "SELECT * FROM locations ORDER BY path"
        )]

    def list_cases(self) -> list[dict]:
        """Legacy full listing retained for existing CLI and callers."""
        packages = {
            row["package_id"]: {
                "package_id": row["package_id"], "sha256": row["sha256"],
                "case_id": row["case_id"], "inventory": json.loads(row["inventory_json"]),
            }
            for row in self._connection.execute(
                "SELECT package_id,sha256,case_id,inventory_json FROM packages ORDER BY package_id"
            )
        }
        grouped: dict[str, dict] = {}
        unbound = []
        for location in self._all_locations():
            package = packages.get(location["package_id"])
            if package is None:
                unbound.append(location)
                continue
            group = grouped.setdefault(package["case_id"], {
                "case_id": package["case_id"], "package_revisions": [], "locations": [],
            })
            if all(item["package_id"] != package["package_id"] for item in group["package_revisions"]):
                group["package_revisions"].append(package)
            group["locations"].append(location)
        result = list(grouped.values())
        for group in result:
            group["package_revisions"].sort(key=lambda item: (item["package_id"], item["sha256"]))
        if unbound:
            result.append({"case_id": None, "package_revisions": [], "locations": unbound})
        return sorted(result, key=lambda item: item["case_id"] or "")

    def get_package(self, package_id: str) -> dict:
        row = self._connection.execute(
            "SELECT package_id,sha256,case_id,inventory_json FROM packages WHERE package_id=?",
            (package_id,),
        ).fetchone()
        if row is None:
            raise KeyError(package_id)
        return {
            "package_id": row["package_id"], "sha256": row["sha256"],
            "case_id": row["case_id"], "inventory": json.loads(row["inventory_json"]),
            "locations": [loc for loc in self._all_locations() if loc["package_id"] == package_id],
        }

    @staticmethod
    def _summary_cte() -> str:
        return """WITH candidates AS (
          SELECT p.case_id AS case_key,
            CASE WHEN p.label='Unknown' THEN COALESCE(NULLIF(basename(l.path),''),'Unnamed case')
                 ELSE p.label END AS label,p.saved_at_utc,p.teeth_json,
            CASE WHEN l.path IS NULL THEN 'Missing' WHEN l.status='Valid' THEN 'Checked'
                 WHEN l.status='Error' THEN 'Invalid' ELSE l.status END AS package_status,
            p.workflow_status,l.status AS location_status,p.package_id,COALESCE(l.path,'') AS path,
            CASE l.status WHEN 'Valid' THEN 0 WHEN 'Conflict' THEN 1 WHEN 'Error' THEN 2
                WHEN 'Changed' THEN 3 WHEN 'Missing' THEN 4 ELSE 5 END AS location_rank
          FROM packages p LEFT JOIN locations l
            ON l.package_id=p.package_id AND l.status<>'Conflict'
          UNION ALL
          SELECT 'path:'||d.path,
            CASE WHEN d.label='Unknown' THEN basename(d.path) ELSE d.label END,
            d.saved_at_utc,d.teeth_json,
            CASE l.status WHEN 'Valid' THEN 'Checked' WHEN 'Error' THEN 'Invalid'
              WHEN 'Missing' THEN 'Missing' WHEN 'Changed' THEN 'Changed'
              WHEN 'Conflict' THEN 'Conflict' ELSE 'Unchecked' END,
            d.workflow_status,l.status,COALESCE(d.claimed_package_id,'preview:'||d.path),d.path,1
          FROM discoveries d JOIN locations l ON l.path=d.path
          WHERE l.package_id IS NULL OR l.status='Conflict'
          UNION ALL
          SELECT 'path:'||l.path,
            CASE WHEN l.path=l.root_path THEN basename(l.path)
                 ELSE COALESCE(NULLIF(basename(l.path),''),'Unknown') END,
            NULL,'[]',
            CASE l.status WHEN 'Error' THEN 'Invalid' WHEN 'Missing' THEN 'Missing'
              WHEN 'Changed' THEN 'Changed' WHEN 'Conflict' THEN 'Conflict'
              ELSE 'Unchecked' END,'Missing',l.status,'preview:'||l.path,l.path,1
          FROM locations l WHERE NOT EXISTS (SELECT 1 FROM discoveries d WHERE d.path=l.path)
            AND (l.package_id IS NULL OR l.status='Conflict')
        ), selected AS (
          SELECT c.* FROM candidates c WHERE NOT EXISTS (
            SELECT 1 FROM candidates n WHERE n.case_key=c.case_key AND (
              COALESCE(n.saved_at_utc,'') > COALESCE(c.saved_at_utc,'') OR (
                COALESCE(n.saved_at_utc,'') = COALESCE(c.saved_at_utc,'') AND
                (n.location_rank,n.path,n.package_id) < (c.location_rank,c.path,c.package_id)
              )
            )
          )
        ) """

    @staticmethod
    def _search_filter(query: str, status: str) -> tuple[str, tuple]:
        query_text = f"%{query.strip()}%"
        where = " WHERE (?='' OR label LIKE ? OR teeth_json LIKE ?)"
        args: list = [query.strip(), query_text, query_text]
        if status.strip():
            where += " AND (package_status=? COLLATE NOCASE OR workflow_status=? COLLATE NOCASE OR location_status=? COLLATE NOCASE)"
            args.extend((status.strip(), status.strip(), status.strip()))
        return where, tuple(args)

    def list_case_summaries(self, query: str = "", status: str = "", limit: int = 100,
                            offset: int = 0) -> dict:
        if not isinstance(query, str) or not isinstance(status, str):
            raise TypeError("query and status must be strings.")
        if type(limit) is not int or type(offset) is not int or offset < 0:
            raise ValueError("limit and offset must be non-negative integers.")
        limit = min(limit, 100)
        if limit < 0:
            raise ValueError("limit must be non-negative.")
        where, args = self._search_filter(query, status)
        cte = self._summary_cte()
        total = self._connection.execute(cte + " SELECT COUNT(*) FROM selected" + where, args).fetchone()[0]
        rows = self._connection.execute(
            cte + " SELECT case_key,label,saved_at_utc,teeth_json,package_status,workflow_status,package_id,path "
            "FROM selected" + where + " ORDER BY (saved_at_utc IS NULL),saved_at_utc DESC,case_key,path LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
        return {"items": [
            {"case_key": row["case_key"], "label": row["label"],
             "teeth": json.loads(row["teeth_json"]), "saved_at_utc": row["saved_at_utc"],
             "package_status": row["package_status"], "workflow_status": row["workflow_status"],
             "package_id": row["package_id"], "path": row["path"]}
            for row in rows
        ], "total": total}

    def _case_locations(self, package_id: str | None = None, path: str | None = None) -> list[dict]:
        if package_id is not None:
            rows = self._connection.execute("SELECT * FROM locations WHERE package_id=? ORDER BY path", (package_id,))
        else:
            rows = self._connection.execute("SELECT * FROM locations WHERE path=?", (path,))
        return [{"path": loc["path"], "status": effective["status"], "error": effective.get("error")}
                for loc in rows for effective in (self._effective_location(loc),)]

    @staticmethod
    def _metadata_for_inventory(inventory: CaseInventory, saved_at: str | None) -> dict:
        metadata = dict(inventory.metadata) if isinstance(inventory.metadata, dict) else {}
        metadata.setdefault("targetToothAssociations", [])
        metadata.setdefault("checkpointPreview", [
            {"checkpoint_id": item.checkpoint_id, "state": item.state,
             "target_id": item.target_id, "branch_id": item.branch_id, "scope": item.scope}
            for item in inventory.artifacts
        ])
        metadata.setdefault("branchPreview", [
            {"id": item.id, "target_id": item.target_id,
             "trajectory_ids": list(item.trajectory_ids), "pairing_intent": item.pairing_intent}
            for item in inventory.branches
        ])
        metadata["saved_at_utc"] = saved_at or metadata.get("saved_at_utc")
        return metadata

    def get_case_details(self, case_key: str) -> dict:
        if not isinstance(case_key, str) or not case_key:
            raise ValueError("case_key must be a non-empty string.")
        revisions = []
        if case_key.startswith("path:"):
            path = case_key[5:]
            row = self._connection.execute(
                "SELECT d.*,l.status,l.error,l.root_path FROM discoveries d "
                "JOIN locations l ON l.path=d.path WHERE d.path=? "
                "AND (l.package_id IS NULL OR l.status='Conflict')", (path,)
            ).fetchone()
            if row is None:
                location = self._connection.execute(
                    "SELECT * FROM locations WHERE path=? AND (package_id IS NULL OR status='Conflict')",
                    (path,),
                ).fetchone()
                if location is None:
                    raise KeyError(case_key)
                discovery_meta = {
                    "trusted": False, "targetToothAssociations": [],
                    "checkpointPreview": [], "branchPreview": [],
                    "error": self._effective_location(location).get("error"),
                }
                revision = {
                    "package_id": f"preview:{path}", "saved_at_utc": None,
                    "inventory": None, "metadata": discovery_meta,
                    "locations": self._case_locations(path=path),
                }
            else:
                discovery_meta = json.loads(row["metadata_json"])
                discovery_meta.update({"trusted": False, "claimedCaseId": row["claimed_case_id"],
                                       "claimedPackageId": row["claimed_package_id"]})
                revision = {
                    "package_id": row["claimed_package_id"] or f"preview:{path}",
                    "saved_at_utc": row["saved_at_utc"], "inventory": None,
                    "metadata": discovery_meta,
                    "locations": self._case_locations(path=path),
                }
            revisions.append(revision)
        else:
            rows = self._connection.execute(
                "SELECT package_id,inventory_json,saved_at_utc FROM packages WHERE case_id=?",
                (case_key,),
            ).fetchall()
            if not rows:
                raise KeyError(case_key)
            for row in rows:
                inventory = CaseInventory.from_dict(json.loads(row["inventory_json"]))
                revisions.append({
                    "package_id": row["package_id"], "saved_at_utc": row["saved_at_utc"],
                    "inventory": inventory,
                    "metadata": self._metadata_for_inventory(inventory, row["saved_at_utc"]),
                    "locations": self._case_locations(package_id=row["package_id"]),
                })
        revisions.sort(key=lambda item: (item["saved_at_utc"] is None,
                                         item["saved_at_utc"] or "", item["package_id"]))
        dated = [item for item in revisions if item["saved_at_utc"] is not None]
        unknown = [item for item in revisions if item["saved_at_utc"] is None]
        dated.sort(key=lambda item: (item["saved_at_utc"], item["package_id"]), reverse=True)
        unknown.sort(key=lambda item: item["package_id"])
        return {"case_key": case_key, "revisions": dated + unknown}

    def clear(self) -> None:
        """Forget catalog rows transactionally; package files are never touched."""
        with self._connection:
            for table in ("discoveries", "locations", "packages", "roots"):
                self._connection.execute(f"DELETE FROM {table}")

    def record_verified(self, inventory: CaseInventory) -> None:
        """Persist an on-demand full inventory after checking its current file identity."""
        if not isinstance(inventory, CaseInventory) or inventory.integrity != "Valid":
            raise ValueError("A valid CaseInventory is required.")
        path = Path(inventory.path).expanduser().resolve(strict=True)
        info = path.stat()
        if not path.is_file() or info.st_size != inventory.stat_size or info.st_mtime_ns != inventory.stat_mtime_ns:
            raise ValueError("DentoCase file changed since verification.")
        metadata = inventory.metadata if isinstance(inventory.metadata, dict) else {}
        expected_signature = tuple(metadata.get(key) for key in
                                   ("stat_dev", "stat_ino", "stat_size", "stat_mtime_ns", "stat_ctime_ns"))
        if all(value is not None for value in expected_signature) and expected_signature != _signature(info):
            raise ValueError("DentoCase file changed since verification.")
        indexed = self._location(str(path))
        indexed_status = self._effective_location(indexed)["status"] if indexed is not None else ""
        if indexed is not None and indexed_status in {"Conflict", "Error"}:
            raise ValueError(f"Indexed location is {indexed_status}; rescan it before recording.")
        if (indexed is not None and indexed["package_id"] not in {None, inventory.package_id}
                and indexed_status != "Changed"):
            raise ValueError("Indexed location now has a different package ID; rescan it before recording.")
        root = indexed["root_path"] if indexed is not None else None
        if root is None:
            roots = [value for value in self._registered_roots()
                     if os.path.commonpath((value, str(path))) == value]
            root = max(roots, key=len) if roots else self.add_root(path.parent)
        discovery = _inventory_discovery(inventory)
        label, saved_at, teeth, workflow_status = _inventory_fields(inventory)
        existing = self._connection.execute(
            "SELECT sha256,case_id FROM packages WHERE package_id=?", (inventory.package_id,)
        ).fetchone()
        if existing is not None and (existing["sha256"] != inventory.package_sha256
                                     or existing["case_id"] != inventory.case_id):
            reason = "Package ID conflicts with a different trusted identity."
            with self._connection:
                self._write_location(str(path), root, inventory.package_id, "Conflict",
                                     reason, info, inventory.checked_at_utc)
                self._write_discovery(discovery)
            raise ValueError(reason)
        with self._connection:
            self._connection.execute(
                """INSERT INTO packages
                   (package_id,sha256,case_id,inventory_json,label,saved_at_utc,teeth_json,workflow_status)
                   VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(package_id) DO UPDATE SET
                   inventory_json=excluded.inventory_json,label=excluded.label,
                   saved_at_utc=excluded.saved_at_utc,teeth_json=excluded.teeth_json,
                   workflow_status=excluded.workflow_status""",
                (inventory.package_id, inventory.package_sha256, inventory.case_id,
                 _encoded(inventory.to_dict()), label, saved_at, _encoded(teeth), workflow_status),
            )
            self._write_location(str(path), root, inventory.package_id, "Valid", None, info,
                                 inventory.checked_at_utc)
            self._write_discovery(discovery)

    def revalidate(self, path: str | Path) -> CaseInventory:
        """Fully validate current bytes and reject known identity conflicts."""
        selected_path = Path(os.path.abspath(Path(path).expanduser()))
        indexed = self._connection.execute(
            "SELECT * FROM locations WHERE path=?", (str(selected_path),)
        ).fetchone()
        inventory = inspect_package(selected_path)
        indexed_status = self._effective_location(indexed)["status"] if indexed is not None else ""
        if indexed is not None and indexed_status in {"Conflict", "Error"}:
            raise ValueError(f"Indexed location is {indexed_status}; rescan it before revalidation.")
        if (indexed is not None and indexed["package_id"] not in {None, inventory.package_id}
                and indexed_status != "Changed"):
            raise ValueError("Indexed location now has a different package ID; rescan it before revalidation.")
        trusted = self._connection.execute(
            "SELECT sha256,case_id FROM packages WHERE package_id=?", (inventory.package_id,)
        ).fetchone()
        if trusted is not None and (trusted["sha256"] != inventory.package_sha256
                                    or trusted["case_id"] != inventory.case_id):
            raise ValueError("Package ID conflicts with a different trusted identity.")
        return inventory


def _write_discovery_from_inventory(inventory: CaseInventory) -> dict:
    return _inventory_discovery(inventory)
