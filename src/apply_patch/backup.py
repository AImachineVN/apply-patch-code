from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .context import BackupError, ProjectDescriptor
from .safety import safe_join
from .utils import sha256_file, write_bytes_atomic

log = logging.getLogger(__name__)

SESSION_METADATA_FILENAME = "_session.json"
BACKUP_SESSIONS_SUBDIR = "sessions"
BACKUP_PRE_FLIGHT_SUBDIR = "pre_flight"
BACKUP_MANUAL_SUBDIR = "manual"
BACKUP_INDEX_FILENAME = "_index.json"
BACKUP_MANIFEST_FILENAME = "_manifest.json"


def _sanitize_for_filename(value: str, max_len: int = 60) -> str:
    if not value:
        return "patch"
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    sanitized = re.sub(r"_+", "_", sanitized).strip("._-")
    if not sanitized:
        return "patch"
    return sanitized[:max_len]


def _make_session_id(patch_id: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{_sanitize_for_filename(patch_id)}_{timestamp}"


def _get_backup_root(project: ProjectDescriptor) -> Path:
    return project.backup_dir


@dataclass
class BackupRecord:
    backup_file: Path
    metadata_file: Path
    original_rel: str
    project_id: str
    project_root: Path
    timestamp: str
    patch_id: str
    original_sha256: str
    backup_sha256: str
    session_id: str = ""
    tool_version: str = __version__

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_file": str(self.backup_file),
            "metadata_file": str(self.metadata_file),
            "original_rel": self.original_rel,
            "project_id": self.project_id,
            "project_root": str(self.project_root),
            "timestamp": self.timestamp,
            "patch_id": self.patch_id,
            "original_sha256": self.original_sha256,
            "backup_sha256": self.backup_sha256,
            "session_id": self.session_id,
            "tool_version": self.tool_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupRecord:
        try:
            return cls(
                backup_file=Path(data["backup_file"]),
                metadata_file=Path(data["metadata_file"]),
                original_rel=str(data["original_rel"]),
                project_id=str(data.get("project_id", "")),
                project_root=Path(data.get("project_root", ".")),
                timestamp=str(data.get("timestamp", "")),
                patch_id=str(data.get("patch_id", "")),
                original_sha256=str(data.get("original_sha256", "")),
                backup_sha256=str(data["backup_sha256"]),
                session_id=str(data.get("session_id", "")),
                tool_version=str(data.get("tool_version", __version__)),
            )
        except KeyError as exc:
            raise BackupError(
                f"Backup metadata is missing required field: {exc}"
            ) from exc


def create_session_dir(
    project: ProjectDescriptor,
    patch_id: str,
    subdir: str = BACKUP_SESSIONS_SUBDIR,
) -> Path:
    base = _make_session_id(patch_id)
    subdir_path = _get_backup_root(project) / subdir
    session_dir = subdir_path / base
    suffix = 1
    while session_dir.exists():
        session_dir = subdir_path / f"{base}_{suffix}"
        suffix += 1
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def create_backup(
    project: ProjectDescriptor,
    file_path: Path,
    patch_id: str,
    session_dir: Path | None = None,
) -> BackupRecord:
    root = project.root.resolve()
    file_resolved = file_path.resolve()

    try:
        rel = file_resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise BackupError(
            f"File {file_path} is not inside project root {root}"
        ) from exc

    if not file_resolved.exists():
        raise BackupError(f"File to back up does not exist: {file_resolved}")

    if session_dir is None:
        session_dir = create_session_dir(project, patch_id)

    session_id = session_dir.name
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")

    backup_file = session_dir / rel
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_file.write_bytes(file_resolved.read_bytes())

    original_sha256 = sha256_file(file_resolved)
    backup_sha256 = sha256_file(backup_file)

    metadata_file = backup_file.parent / (backup_file.name + ".meta.json")

    record = BackupRecord(
        backup_file=backup_file.resolve(),
        metadata_file=metadata_file.resolve(),
        original_rel=rel,
        project_id=project.project_id,
        project_root=root,
        timestamp=timestamp,
        patch_id=patch_id,
        original_sha256=original_sha256,
        backup_sha256=backup_sha256,
        session_id=session_id,
        tool_version=__version__,
    )

    metadata_file.write_text(
        json.dumps(record.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return record


def write_session_metadata(
    session_dir: Path,
    project: ProjectDescriptor,
    patch_id: str,
    files: list[dict[str, Any]],
    success: bool,
) -> Path:
    metadata = {
        "schema_version": "1.0",
        "session_id": session_dir.name,
        "patch_id": patch_id,
        "project_id": project.project_id,
        "project_root": str(project.root),
        "finished_at": datetime.now(UTC).isoformat(),
        "file_count": len(files),
        "success": success,
        "files": files,
    }
    session_file = session_dir / SESSION_METADATA_FILENAME
    session_file.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return session_file


def write_manifest(
    session_dir: Path,
    patch_id: str,
    project: ProjectDescriptor,
    files_meta: list[dict[str, Any]],
) -> Path:
    """Write _manifest.json tracking action (modified/created/deleted) per file.

    files_meta item format:
      {"rel_path": str, "action": "modified"|"created"|"deleted",
       "backup_rel": str|None, "sha256": str|None, "size": int}
    """
    manifest = {
        "schema_version": "1.0",
        "session_id": session_dir.name,
        "patch_id": patch_id,
        "project_id": project.project_id,
        "project_root": str(project.root),
        "applied_at": datetime.now(UTC).isoformat(),
        "files": files_meta,
    }
    manifest_path = session_dir / BACKUP_MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def read_manifest(session_dir: Path) -> dict[str, Any]:
    manifest_path = session_dir / BACKUP_MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise BackupError(
            f"Manifest not found in session {session_dir}. "
            f"Undo requires a backup created by a tool version that writes _manifest.json."
        )
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError(f"Cannot read manifest {manifest_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BackupError(f"Manifest must be a JSON object: {manifest_path}")
    return data


def update_index(project: ProjectDescriptor) -> Path:
    """Rebuild apply_patch_backup/_index.json from all sessions subdirs."""
    root = _get_backup_root(project)
    index_data: dict[str, Any] = {
        "schema_version": "1.0",
        "updated_at": datetime.now(UTC).isoformat(),
        "project_id": project.project_id,
        "sessions": [],
        "pre_flight": [],
        "manual": [],
    }
    for subdir_name, list_key in (
        (BACKUP_SESSIONS_SUBDIR, "sessions"),
        (BACKUP_PRE_FLIGHT_SUBDIR, "pre_flight"),
        (BACKUP_MANUAL_SUBDIR, "manual"),
    ):
        subdir = root / subdir_name
        if not subdir.is_dir():
            continue
        for session_path in sorted(subdir.iterdir()):
            if not session_path.is_dir():
                continue
            session_meta_file = session_path / SESSION_METADATA_FILENAME
            entry: dict[str, Any] = {
                "session_id": session_path.name,
                "path": str(session_path),
                "file_count": 0,
                "total_bytes": 0,
                "status": "unknown",
            }
            if session_meta_file.is_file():
                try:
                    meta = json.loads(session_meta_file.read_text(encoding="utf-8"))
                    entry["patch_id"] = str(meta.get("patch_id", ""))
                    entry["file_count"] = int(meta.get("file_count", 0))
                    entry["success"] = bool(meta.get("success", False))
                    entry["status"] = "applied" if meta.get("success") else "failed"
                except (OSError, json.JSONDecodeError, ValueError):
                    pass
            index_data[list_key].append(entry)
    index_path = root / BACKUP_INDEX_FILENAME
    try:
        index_path.write_text(
            json.dumps(index_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise BackupError(f"Cannot write index {index_path}: {exc}") from exc
    return index_path


def find_session_for_patch(project: ProjectDescriptor, patch_id: str) -> Path | None:
    """Find newest session dir in sessions/ matching patch_id."""
    sessions_root = _get_backup_root(project) / BACKUP_SESSIONS_SUBDIR
    if not sessions_root.is_dir():
        return None
    sanitized = _sanitize_for_filename(patch_id)
    candidates: list[Path] = []
    for session_path in sessions_root.iterdir():
        if not session_path.is_dir():
            continue
        if not session_path.name.startswith(sanitized + "_"):
            continue
        candidates.append(session_path)
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0]


def delete_pre_flight_session(project: ProjectDescriptor, session_id: str) -> bool:
    """Delete pre_flight/<session_id>/ after apply success. Best-effort."""
    pre_flight_root = _get_backup_root(project) / BACKUP_PRE_FLIGHT_SUBDIR
    target = pre_flight_root / session_id
    if not target.is_dir():
        return False
    try:
        shutil.rmtree(target)
        return True
    except OSError as exc:
        log.warning(f"Cannot delete pre_flight session {target}: {exc}")
        return False


def load_backup_record(metadata_path: Path) -> BackupRecord:
    if not metadata_path.exists():
        raise BackupError(f"Backup metadata not found: {metadata_path}")
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BackupError(
            f"Cannot read backup metadata {metadata_path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise BackupError(
            f"Backup metadata {metadata_path} must be a JSON object."
        )
    return BackupRecord.from_dict(data)


def list_backups(project: ProjectDescriptor) -> list[BackupRecord]:
    """List all backups of a project, newest first.

    Scans sessions/ subdir (new layout). Old root-level layout is not scanned
    (user decision 2C - no migration).
    """
    sessions_root = _get_backup_root(project) / BACKUP_SESSIONS_SUBDIR
    if not sessions_root.is_dir():
        return []
    records: list[BackupRecord] = []
    for meta_path in sessions_root.rglob("*.meta.json"):
        try:
            record = load_backup_record(meta_path)
            records.append(record)
        except BackupError:
            continue
    records.sort(key=lambda r: r.timestamp, reverse=True)
    return records


def rollback_backup_path(project: ProjectDescriptor, backup_path: Path) -> Path:
    backup_path = backup_path.resolve()

    if backup_path.name.endswith(".meta.json"):
        metadata_path = backup_path
        backup_file = metadata_path.parent / metadata_path.name[: -len(".meta.json")]
    else:
        backup_file = backup_path
        metadata_path = backup_path.parent / (backup_path.name + ".meta.json")

    if not metadata_path.exists():
        raise BackupError(
            f"Backup metadata not found: {metadata_path}. "
            "Safe rollback requires the accompanying .meta.json file."
        )

    record = load_backup_record(metadata_path)
    candidate = backup_file if backup_file.exists() else Path(record.backup_file)

    if not candidate.exists():
        raise BackupError(f"Actual backup file not found: {candidate}")

    actual_hash = sha256_file(candidate)
    if actual_hash != record.backup_sha256:
        raise BackupError(
            "Backup file SHA-256 does not match metadata. "
            "Refusing rollback to avoid data loss."
        )

    original_path = safe_join(project.root, record.original_rel)
    write_bytes_atomic(original_path, candidate.read_bytes())
    return original_path
