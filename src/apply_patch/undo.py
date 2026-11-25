"""Undo Execute: restore files from backup session.

Uses _manifest.json in sessions/<id>/ to know which files to:
- restore (action=modified/deleted)
- delete (action=created)

Refuses undo if:
- session not found
- manifest missing
- any file's current SHA-256 differs from backup (user edited after apply)
- any backup file missing

Best-effort: per-file errors reported in UndoResult.errors.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backup import (
    find_session_for_patch,
    read_manifest,
    rollback_backup_path,
)
from .context import BackupError, ProjectDescriptor
from .patch_history import PatchHistory, get_history_path
from .safety import safe_join
from .utils import sha256_file

log = logging.getLogger(__name__)


@dataclass
class UndoResult:
    success: bool
    patch_id: str
    session_dir: Path | None = None
    restored_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    missing_backup: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    message: str = ""


def _verify_current_state(
    project: ProjectDescriptor,
    files_meta: list[dict[str, Any]],
) -> tuple[bool, list[str], list[str]]:
    """Verify current file states before undo.

    Returns (ok, modified_files, missing_backup_files).
    modified_files: current SHA-256 differs from backup -> refuse (mode A).
    missing_backup_files: backup file missing -> refuse.
    """
    modified: list[str] = []
    missing_backup: list[str] = []
    for fm in files_meta:
        action = str(fm.get("action", ""))
        rel_path = str(fm.get("rel_path", ""))
        backup_rel = fm.get("backup_rel")
        expected_sha = fm.get("sha256")

        if action == "created":
            continue
        if not backup_rel:
            missing_backup.append(rel_path)
            continue

        try:
            current_path = safe_join(project.root, rel_path)
        except Exception as exc:  # noqa: BLE001
            missing_backup.append(f"{rel_path} ({exc})")
            continue

        # expected_sha is the POST-PATCH sha of target file.
        # For action="deleted": expected_sha is None (file should not exist now).
        # For action="modified": expected_sha is SHA of patched content.
        if expected_sha is None:
            # Deleted by patch -> target should not exist now.
            # If it exists, user recreated -> refuse.
            if current_path.exists():
                modified.append(rel_path)
            continue

        if current_path.exists():
            try:
                current_sha = sha256_file(current_path)
            except Exception:  # noqa: BLE001
                current_sha = "<unreadable>"
            if current_sha != expected_sha:
                modified.append(rel_path)
    return (not modified and not missing_backup), modified, missing_backup


def undo_patch(project: ProjectDescriptor, patch_id: str) -> UndoResult:
    """Undo a previously applied patch.

    Steps:
    1. Find session in sessions/ matching patch_id
    2. Read _manifest.json
    3. Verify current state (mode A - refuse if modified)
    4. Execute: restore modified/deleted, delete created
    5. Update patch_history: status=undone
    """
    result = UndoResult(success=False, patch_id=patch_id)

    # 1. Find session
    session_dir = find_session_for_patch(project, patch_id)
    if session_dir is None:
        result.message = (
            f"Backup session not found for patch_id={patch_id}. "
            f"Cannot undo (only patches applied with current tool version "
            f"write the required manifest)."
        )
        return result
    result.session_dir = session_dir

    # 2. Read manifest
    try:
        manifest = read_manifest(session_dir)
    except BackupError as exc:
        result.message = f"Cannot read manifest: {exc}"
        return result

    files_meta = manifest.get("files", [])
    if not isinstance(files_meta, list):
        result.message = "Manifest 'files' field is not a list"
        return result

    # 3. Verify current state
    _ok, modified, missing_backup = _verify_current_state(project, files_meta)
    result.modified_files = modified
    result.missing_backup = missing_backup
    if modified:
        result.message = (
            f"Refusing undo: {len(modified)} file(s) modified since apply: "
            + ", ".join(modified)
        )
        return result
    if missing_backup:
        result.message = (
            f"Refusing undo: {len(missing_backup)} backup file(s) missing/invalid: "
            + ", ".join(missing_backup)
        )
        return result

    # 4. Execute
    for fm in files_meta:
        action = str(fm.get("action", ""))
        rel_path = str(fm.get("rel_path", ""))
        backup_rel = fm.get("backup_rel")

        if action == "created":
            target = safe_join(project.root, rel_path)
            try:
                if target.exists():
                    target.unlink()
                    result.deleted_files.append(rel_path)
            except OSError as exc:
                result.errors.append(f"delete {rel_path}: {exc}")

        elif action in ("modified", "deleted"):
            if not backup_rel:
                result.errors.append(f"{rel_path}: no backup_rel")
                continue
            backup_file = session_dir / str(backup_rel)
            try:
                rollback_backup_path(project, backup_file)
                result.restored_files.append(rel_path)
            except BackupError as exc:
                result.errors.append(f"restore {rel_path}: {exc}")

    if result.errors:
        result.message = (
            f"Undo partially failed: {len(result.errors)} error(s). "
            f"See errors list."
        )
        return result

    # 5. Update history
    try:
        history_path = get_history_path(project.root)
        history = PatchHistory.load(history_path)
        history.record_undo(
            filename=f"{patch_id}.json",
            patch_id=patch_id,
            undo_timestamp=datetime.now(UTC).isoformat(),
        )
        history.save(history_path)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"history update: {exc}")

    result.success = True
    result.message = (
        f"Undo succeeded: restored {len(result.restored_files)}, "
        f"deleted {len(result.deleted_files)}"
    )
    return result
