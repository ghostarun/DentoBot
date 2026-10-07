"""Explicit SQLite catalog for validated DentoCase package locations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Iterable
import zipfile

from .contracts import CaseInventory
from .inspection import inspect_package


_CATALOG_VERSION = 1
_TABLE_SCHEMA = {
    "roots": (
        ("path", "TEXT", 1, 1),
    ),
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


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _path_stat(path: Path) -> tuple[int | None, int | None]:
    try:
        info = path.lstat()
    except OSError:
        return None, None
    return info.st_size, info.st_mtime_ns


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
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._initialize_or_validate()
        except Exception:
            self._connection.close()
            raise

    def _initialize_or_validate(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 0:
            existing = self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view', 'trigger') "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if existing:
                raise ValueError("The existing database has no compatible catalog version.")
            try:
                self._connection.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE roots (
                        path TEXT PRIMARY KEY NOT NULL
                    );
                    CREATE TABLE packages (
                        package_id TEXT PRIMARY KEY NOT NULL,
                        sha256 TEXT NOT NULL,
                        case_id TEXT NOT NULL,
                        inventory_json TEXT NOT NULL
                    );
                    CREATE TABLE locations (
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
                    COMMIT;
                    """
                )
            except Exception:
                self._connection.rollback()
                raise
            return
        if version != _CATALOG_VERSION:
            raise ValueError(f"Unsupported catalog database version: {version}.")
        objects = {
            (row["type"], row["name"])
            for row in self._connection.execute(
                "SELECT type, name FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        expected_tables = {("table", table) for table in _TABLE_SCHEMA}
        if objects != expected_tables:
            raise ValueError("The existing database has an incompatible catalog schema.")
        for table, expected in _TABLE_SCHEMA.items():
            columns = tuple(
                (row["name"], row["type"].upper(), row["notnull"], row["pk"])
                for row in self._connection.execute(f"PRAGMA table_info({table})")
            )
            if columns != expected:
                raise ValueError("The existing database has an incompatible catalog schema.")
        foreign_keys = {
            (row["table"], row["from"], row["to"], row["on_delete"])
            for row in self._connection.execute("PRAGMA foreign_key_list(locations)")
        }
        if foreign_keys != {
            ("roots", "root_path", "path", "CASCADE"),
            ("packages", "package_id", "package_id", "SET NULL"),
        }:
            raise ValueError("The existing database has incompatible catalog relationships.")

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
        return [
            row["path"]
            for row in self._connection.execute("SELECT path FROM roots ORDER BY path")
        ]

    def _upsert_location(
        self,
        *,
        path: str,
        root_path: str,
        package_id: str | None,
        status: str,
        error: str | None,
        size: int | None,
        mtime: int | None,
        checked_at: str,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO locations(path, root_path, package_id, status, error, size, mtime, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    root_path=excluded.root_path,
                    package_id=excluded.package_id,
                    status=excluded.status,
                    error=excluded.error,
                    size=excluded.size,
                    mtime=excluded.mtime,
                    checked_at=excluded.checked_at
                """,
                (path, root_path, package_id, status, error, size, mtime, checked_at),
            )

    @staticmethod
    def _failure_reason(error: Exception) -> str:
        if isinstance(error, (ValueError, RuntimeError)):
            return str(error) or type(error).__name__
        return f"Package inspection failed ({type(error).__name__})."

    def _scan_file(self, path: Path, root_path: str) -> dict:
        resolved = str(path.resolve())
        size, mtime = _path_stat(path)
        try:
            inventory = inspect_package(path)
        except Exception as exc:
            reason = self._failure_reason(exc)
            self._upsert_location(
                path=resolved,
                root_path=root_path,
                package_id=None,
                status="Error",
                error=reason,
                size=size,
                mtime=mtime,
                checked_at=_utc_now(),
            )
            return {
                "path": resolved,
                "root_path": root_path,
                "status": "Error",
                "error": reason,
            }

        encoded = json.dumps(
            inventory.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        with self._connection:
            existing = self._connection.execute(
                "SELECT sha256, case_id FROM packages WHERE package_id = ?",
                (inventory.package_id,),
            ).fetchone()
            if existing is not None and (
                existing["sha256"] != inventory.package_sha256
                or existing["case_id"] != inventory.case_id
            ):
                reason = "Package ID already has a different trusted content identity."
                self._connection.execute(
                    """
                    INSERT INTO locations(path, root_path, package_id, status, error, size, mtime, checked_at)
                    VALUES (?, ?, ?, 'Conflict', ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        root_path=excluded.root_path,
                        package_id=excluded.package_id,
                        status='Conflict',
                        error=excluded.error,
                        size=excluded.size,
                        mtime=excluded.mtime,
                        checked_at=excluded.checked_at
                    """,
                    (
                        resolved,
                        root_path,
                        inventory.package_id,
                        reason,
                        inventory.stat_size,
                        inventory.stat_mtime_ns,
                        inventory.checked_at_utc,
                    ),
                )
                return {
                    "path": resolved,
                    "root_path": root_path,
                    "package_id": inventory.package_id,
                    "case_id": inventory.case_id,
                    "sha256": inventory.package_sha256,
                    "status": "Conflict",
                    "error": reason,
                }
            self._connection.execute(
                """
                INSERT INTO packages(package_id, sha256, case_id, inventory_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(package_id) DO UPDATE SET
                    sha256=excluded.sha256,
                    case_id=excluded.case_id,
                    inventory_json=excluded.inventory_json
                """,
                (
                    inventory.package_id,
                    inventory.package_sha256,
                    inventory.case_id,
                    encoded,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO locations(path, root_path, package_id, status, error, size, mtime, checked_at)
                VALUES (?, ?, ?, 'Valid', NULL, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    root_path=excluded.root_path,
                    package_id=excluded.package_id,
                    status='Valid',
                    error=NULL,
                    size=excluded.size,
                    mtime=excluded.mtime,
                    checked_at=excluded.checked_at
                """,
                (
                    resolved,
                    root_path,
                    inventory.package_id,
                    inventory.stat_size,
                    inventory.stat_mtime_ns,
                    inventory.checked_at_utc,
                ),
            )
        return {
            "path": resolved,
            "root_path": root_path,
            "package_id": inventory.package_id,
            "case_id": inventory.case_id,
            "sha256": inventory.package_sha256,
            "status": "Valid",
        }

    def _record_root_error(self, root: str, error: Exception) -> dict:
        size, mtime = _path_stat(Path(root))
        reason = f"Root traversal failed ({type(error).__name__})."
        self._upsert_location(
            path=root,
            root_path=root,
            package_id=None,
            status="Error",
            error=reason,
            size=size,
            mtime=mtime,
            checked_at=_utc_now(),
        )
        return {"path": root, "root_path": root, "status": "Error", "error": reason}

    def _clear_root_error(self, root: str) -> None:
        with self._connection:
            self._connection.execute(
                "DELETE FROM locations WHERE path = ? AND root_path = ? AND package_id IS NULL",
                (root, root),
            )

    def _mark_missing(self, root: str, found: set[str]) -> list[dict]:
        rows = self._connection.execute(
            "SELECT path, package_id FROM locations WHERE root_path = ? AND path != ? ORDER BY path",
            (root, root),
        ).fetchall()
        missing = []
        for row in rows:
            path = row["path"]
            if path in found:
                continue
            with self._connection:
                self._connection.execute(
                    "UPDATE locations SET status='Missing', error='Not found during successful scan', "
                    "checked_at=? WHERE path=? AND root_path=?",
                    (_utc_now(), path, root),
                )
            missing.append(
                {
                    "path": path,
                    "root_path": root,
                    "package_id": row["package_id"],
                    "status": "Missing",
                    "error": "Not found during successful scan",
                }
            )
        return missing

    def scan(self, roots: Iterable[str | Path] | str | Path | None = None) -> list[dict]:
        """Inspect every package under explicitly supplied or registered roots."""

        if roots is None:
            root_paths = self._registered_roots()
        else:
            selected = [roots] if isinstance(roots, (str, Path)) else list(roots)
            root_paths = []
            for root in selected:
                try:
                    root_paths.append(self.add_root(root))
                except (OSError, ValueError) as exc:
                    raw_path = str(Path(root).expanduser())
                    root_paths.append(raw_path)
                    root_errors = getattr(self, "_unregistered_root_errors", None)
                    if root_errors is None:
                        self._unregistered_root_errors = {}
                    self._unregistered_root_errors[raw_path] = exc
            root_paths = sorted(set(root_paths))

        results: list[dict] = []
        seen_paths: set[str] = set()
        for root in root_paths:
            pending_error = getattr(self, "_unregistered_root_errors", {}).pop(root, None)
            if pending_error is not None:
                results.append(
                    {
                        "path": root,
                        "root_path": root,
                        "status": "Error",
                        "error": "Scan root must be an existing directory.",
                    }
                )
                continue
            found: set[str] = set()
            walk_errors: list[Exception] = []
            try:
                root_path = Path(root)
                if not root_path.is_dir():
                    raise FileNotFoundError("scan root is unavailable")
                for directory, dirs, filenames in os.walk(
                    root, topdown=True, followlinks=False, onerror=walk_errors.append
                ):
                    current = Path(directory)
                    dirs[:] = sorted(
                        name for name in dirs if not (current / name).is_symlink()
                    )
                    for filename in sorted(filenames):
                        path = current / filename
                        if path.suffix.lower() != ".dentocase" or path.is_symlink():
                            continue
                        try:
                            if not stat.S_ISREG(path.lstat().st_mode):
                                continue
                        except OSError:
                            pass
                        resolved = str(path.resolve())
                        found.add(resolved)
                        if resolved in seen_paths:
                            continue
                        seen_paths.add(resolved)
                        results.append(self._scan_file(path, root))
            except OSError as exc:
                walk_errors.append(exc)

            if walk_errors:
                results.append(self._record_root_error(root, walk_errors[0]))
            else:
                self._clear_root_error(root)
                results.extend(self._mark_missing(root, found))
        return sorted(results, key=lambda item: (item.get("path", ""), item.get("status", "")))

    @staticmethod
    def _effective_location(row: sqlite3.Row) -> dict:
        result = dict(row)
        path = Path(result["path"])
        if result["path"] == result["root_path"] and result["status"] == "Error":
            return result
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
            or info.st_size != result["size"]
            or info.st_mtime_ns != result["mtime"]
        ):
            result["status"] = "Changed"
            result["error"] = "File size or modification time changed; scan required."
        return result

    def _all_locations(self) -> list[dict]:
        return [
            self._effective_location(row)
            for row in self._connection.execute(
                "SELECT path, root_path, package_id, status, error, size, mtime, checked_at "
                "FROM locations ORDER BY path"
            )
        ]

    def list_cases(self) -> list[dict]:
        packages = {
            row["package_id"]: {
                "package_id": row["package_id"],
                "sha256": row["sha256"],
                "case_id": row["case_id"],
                "inventory": json.loads(row["inventory_json"]),
            }
            for row in self._connection.execute(
                "SELECT package_id, sha256, case_id, inventory_json FROM packages ORDER BY package_id"
            )
        }
        locations = self._all_locations()
        grouped: dict[str, dict] = {}
        unbound = []
        for location in locations:
            package = packages.get(location["package_id"])
            if package is None:
                unbound.append(location)
                continue
            case_id = package["case_id"]
            group = grouped.setdefault(
                case_id,
                {"case_id": case_id, "package_revisions": [], "locations": []},
            )
            if all(item["package_id"] != package["package_id"] for item in group["package_revisions"]):
                group["package_revisions"].append(package)
            group["locations"].append(location)
        result = []
        for group in grouped.values():
            group["package_revisions"].sort(key=lambda item: (item["package_id"], item["sha256"]))
            result.append(group)
        if unbound:
            result.append({"case_id": None, "package_revisions": [], "locations": unbound})
        return sorted(result, key=lambda item: item["case_id"] or "")

    def get_package(self, package_id: str) -> dict:
        row = self._connection.execute(
            "SELECT package_id, sha256, case_id, inventory_json FROM packages WHERE package_id = ?",
            (package_id,),
        ).fetchone()
        if row is None:
            raise KeyError(package_id)
        locations = [
            location
            for location in self._all_locations()
            if location["package_id"] == package_id
        ]
        return {
            "package_id": row["package_id"],
            "sha256": row["sha256"],
            "case_id": row["case_id"],
            "inventory": json.loads(row["inventory_json"]),
            "locations": locations,
        }

    def revalidate(self, path: str | Path) -> CaseInventory:
        """Validate current bytes and reject a known package-ID/hash conflict."""

        selected_path = Path(os.path.abspath(Path(path).expanduser()))
        indexed = self._connection.execute(
            "SELECT path, package_id, status FROM locations WHERE path = ?",
            (str(selected_path),),
        ).fetchone()
        inventory = inspect_package(selected_path)
        if indexed is not None and indexed["status"] in {"Conflict", "Error"}:
            raise ValueError(
                f"Indexed location is {indexed['status']}; rescan it before revalidation."
            )
        if indexed is not None and indexed["package_id"] != inventory.package_id:
            raise ValueError(
                "Indexed location now has a different package ID; rescan it before revalidation."
            )
        trusted = self._connection.execute(
            "SELECT sha256, case_id FROM packages WHERE package_id = ?",
            (inventory.package_id,),
        ).fetchone()
        if trusted is not None and (
            trusted["sha256"] != inventory.package_sha256
            or trusted["case_id"] != inventory.case_id
        ):
            raise ValueError("Package ID conflicts with a different trusted identity.")
        return inventory
