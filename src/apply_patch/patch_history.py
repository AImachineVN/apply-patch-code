"""Patch history tracking for Apply Patch Code.
Tracks which patch files have been applied to a project, storing:
filename, patch_id, sha256 hash, timestamp, status, progress_report_snapshot
Used to prevent accidental re-application of modified patches,
and to preserve AI coordination audit trail (progress_report).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

HISTORY_FILENAME = "patch_history.json"
HISTORY_SCHEMA_VERSION = "1.1"


@dataclass
class PatchHistoryEntry:
    """One record in patch history."""
    filename: str
    patch_id: str
    applied_at: str
    sha256: str
    status: str = "applied"
    undone_at: str = ""
    # [H3 FIX] Snapshot của progress_report tại thời điểm apply.
    # Bảo toàn audit trail khi patch file gốc bị xóa khỏi thư mục.
    progress_report_snapshot: dict[str, Any] | None = None


@dataclass
class PatchHistory:
    """Manages patch history for a project, stored at .apply_patch/patch_history.json"""
    schema_version: str = HISTORY_SCHEMA_VERSION
    entries: dict[str, PatchHistoryEntry] = field(default_factory=dict)
    _corrupt: bool = False

    @property
    def is_corrupt(self) -> bool:
        """Trả về True nếu file history bị hỏng khi load."""
        return self._corrupt

    @classmethod
    def load(cls, history_path: Path) -> PatchHistory:
        """Load history from file. Returns empty history if file missing, or corrupt history if file is damaged."""
        if not history_path.exists():
            return cls()
        try:
            raw = json.loads(history_path.read_text(encoding="utf-8"))
            entries: dict[str, PatchHistoryEntry] = {}
            for fname, data in raw.get("entries", {}).items():
                if not isinstance(data, dict):
                    continue
                snapshot = data.get("progress_report_snapshot")
                # Ensure snapshot is dict or None (defensive)
                if snapshot is not None and not isinstance(snapshot, dict):
                    snapshot = None
                entries[fname] = PatchHistoryEntry(
                    filename=fname,
                    patch_id=str(data.get("patch_id", "")),
                    applied_at=str(data.get("applied_at", "")),
                    sha256=str(data.get("sha256", "")),
                    status=str(data.get("status", "applied")),
                    undone_at=str(data.get("undone_at", "")),
                    progress_report_snapshot=snapshot,
                )
            return cls(
                schema_version=str(raw.get("schema_version", "1.0")),
                entries=entries,
            )
        except Exception:
            # File tồn tại nhưng bị hỏng -> trả về object với cờ corrupt
            return cls(_corrupt=True)

    def save(self, history_path: Path) -> bool:
        """Save history to file. Returns True on success."""
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "schema_version": self.schema_version,
                "entries": {
                    fname: {
                        "patch_id": entry.patch_id,
                        "applied_at": entry.applied_at,
                        "sha256": entry.sha256,
                        "status": entry.status,
                        "undone_at": entry.undone_at,
                        "progress_report_snapshot": entry.progress_report_snapshot,
                    }
                    for fname, entry in self.entries.items()
                },
            }
            history_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def get_entry(self, filename: str) -> PatchHistoryEntry | None:
        """Get entry by filename. Returns None if not found."""
        return self.entries.get(filename)

    def record_success(
        self,
        filename: str,
        patch_id: str,
        sha256: str,
        progress_report_snapshot: dict[str, Any] | None = None,
    ) -> None:
        """Record a successfully applied patch, preserving progress_report if provided."""
        self.entries[filename] = PatchHistoryEntry(
            filename=filename,
            patch_id=patch_id,
            applied_at=datetime.now().isoformat(),
            sha256=sha256,
            status="applied",
            progress_report_snapshot=progress_report_snapshot,
        )

    def record_failure(
        self,
        filename: str,
        patch_id: str,
        sha256: str,
    ) -> None:
        """[GAP-7 FIX] Record a failed patch attempt for status display."""
        self.entries[filename] = PatchHistoryEntry(
            filename=filename,
            patch_id=patch_id,
            applied_at=datetime.now().isoformat(),
            sha256=sha256,
            status="failed",
            progress_report_snapshot=None,
        )

    def record_undo(self, filename: str, patch_id: str, undo_timestamp: str) -> None:
        """Mark entry as undone (status=undone, undo_timestamp set)."""
        entry = self.entries.get(filename)
        if entry is None:
            # Try matching by patch_id
            for existing in self.entries.values():
                if existing.patch_id == patch_id:
                    existing.status = "undone"
                    existing.undone_at = undo_timestamp
                    return
            return
        entry.status = "undone"
        entry.undone_at = undo_timestamp

    def remove_entry(self, filename: str) -> None:
        """Remove an entry (when patch file is deleted from directory)."""
        self.entries.pop(filename, None)


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_history_path(project_root: Path) -> Path:
    """Return path to history file inside project."""
    return project_root / ".apply_patch" / HISTORY_FILENAME


def get_patch_status(patch_file: Path, history: PatchHistory) -> tuple[str, str]:
    """
    Check status of a patch file against history.

    Returns:
        (status, detail)
        status: 'new' | 'applied_same' | 'applied_modified' | 'failed' | 'unknown'
        detail: human-readable description

    [GAP-7 FIX] Ưu tiên kiểm tra entry.status trước khi compare SHA:
    - status='failed'  → 'failed'           (patch lỗi lần cuối)
    - status='applied' + SHA khớp   → 'applied_same'
    - status='applied' + SHA khác   → 'applied_modified'
    - Không có entry     → 'new'
    """
    # [AUDIT-006 FIX] Kiểm tra history có bị hỏng không
    if history.is_corrupt:
        return (
            "unknown",
            "History file is corrupted. Cannot verify patch status. Re-applying may cause issues.",
        )

    entry = history.get_entry(patch_file.name)
    if entry is None:
        return ("new", "Not yet applied")

    # [GAP-7 FIX] Failed status ưu tiên cao nhất
    if entry.status == "failed":
        return ("failed", f"Failed at {entry.applied_at[:19]}")

    if entry.status == "undone":
        return ("undone", f"Undone at {entry.undone_at[:19]}")

    try:
        current_hash = compute_file_sha256(patch_file)
    except Exception:
        return ("unknown", "Cannot read file to compute hash")

    if current_hash == entry.sha256:
        return ("applied_same", f"Applied at {entry.applied_at[:19]}")
    else:
        return (
            "applied_modified",
            f"Applied at {entry.applied_at[:19]} but file has been modified since",
        )