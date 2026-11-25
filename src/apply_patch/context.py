from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class ApplyPatchError(Exception):
    """Base exception for all apply_patch errors."""


class SchemaError(ApplyPatchError):
    """Patch file violates schema or cannot be parsed."""


class DiscoveryError(ApplyPatchError):
    """Cannot detect or load project directory."""


class OperationError(ApplyPatchError):
    """An operation cannot be executed on target content."""


class VerificationError(ApplyPatchError):
    """Marker or content verification failed."""


class BackupError(ApplyPatchError):
    """Error during backup creation, listing, or restoration."""


class SafetyError(ApplyPatchError):
    """Path safety violation."""


# ---------------------------------------------------------------------------
# Project descriptor
# ---------------------------------------------------------------------------

@dataclass
class ProjectDescriptor:
    """Descriptor for a detected project."""

    root: Path
    project_id: str
    project_type: str
    markers: list[str]
    source_roots: list[str]
    exclude: list[str]
    manifest_path: Path | None
    legacy: bool
    default_language: str = "python"

    @property
    def config_dir(self) -> Path:
        """Project config directory: <root>/.apply_patch"""
        return self.root / ".apply_patch"

    @property
    def backup_dir(self) -> Path:
        """[GAP-1 FIX] Backup root: <root>/apply_patch_backup (visible at project root)."""
        return self.root / "apply_patch_backup"

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "project_id": self.project_id,
            "project_type": self.project_type,
            "markers": list(self.markers),
            "source_roots": list(self.source_roots),
            "exclude": list(self.exclude),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "legacy": self.legacy,
            "default_language": self.default_language,
        }


# ---------------------------------------------------------------------------
# Execution context
# ---------------------------------------------------------------------------

@dataclass
class ExecutionContext:
    """Execution context for applying a patch to a project."""

    project: ProjectDescriptor
    dry_run: bool
    json_output: bool
    patch_path: Path


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class OperationResult:
    """Result of executing one operation."""

    index: int
    type: str
    detail: str
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "type": self.type,
            "detail": self.detail,
            "status": self.status,
        }


@dataclass
class FilePatchResult:
    """Result of applying a patch to one file."""

    file: str
    status: str = "pending"
    message: str = ""
    operations: list[OperationResult] = field(default_factory=list)
    backup_path: Path | None = None
    created: bool = False
    changed: bool = False
    verify_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "status": self.status,
            "message": self.message,
            "operations": [op.to_dict() for op in self.operations],
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "created": self.created,
            "changed": self.changed,
            "verify_errors": list(self.verify_errors),
        }


@dataclass
class PatchReport:
    """Aggregated report of one patch application."""

    patch_path: Path
    project_root: Path
    project_id: str
    dry_run: bool
    success: bool = False
    message: str = ""
    files: list[FilePatchResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_path": str(self.patch_path),
            "project_root": str(self.project_root),
            "project_id": self.project_id,
            "dry_run": self.dry_run,
            "success": self.success,
            "message": self.message,
            "files": [f.to_dict() for f in self.files],
        }