"""Tests for backup manifest and session subdirs."""
from __future__ import annotations

import json
from pathlib import Path

from apply_patch.backup import (
    BACKUP_INDEX_FILENAME,
    BACKUP_MANIFEST_FILENAME,
    BACKUP_PRE_FLIGHT_SUBDIR,
    BACKUP_SESSIONS_SUBDIR,
    create_backup,
    create_session_dir,
    delete_pre_flight_session,
    update_index,
    write_manifest,
)
from apply_patch.context import ProjectDescriptor


def _make_project(tmp_path: Path) -> ProjectDescriptor:
    return ProjectDescriptor(
        root=tmp_path,
        project_id="test_project",
        project_type="python",
        markers=[],
        source_roots=["."],
        exclude=[],
        manifest_path=None,
        legacy=True,
        default_language="python",
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_manifest_modified_action(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    target = tmp_path / "src" / "main.py"
    _write(target, "ORIG\n")
    session_dir = create_session_dir(project, "PATCH-1")
    create_backup(project, target, "PATCH-1", session_dir=session_dir)

    files_meta = [{
        "rel_path": "src/main.py",
        "action": "modified",
        "backup_rel": "src/main.py",
        "sha256": "abc123",
        "size": 5,
    }]
    manifest_path = write_manifest(session_dir, "PATCH-1", project, files_meta)

    assert manifest_path.exists()
    assert manifest_path.name == BACKUP_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["patch_id"] == "PATCH-1"
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["action"] == "modified"


def test_manifest_created_action(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    session_dir = create_session_dir(project, "PATCH-2")

    files_meta = [{
        "rel_path": "src/new.py",
        "action": "created",
        "backup_rel": None,
        "sha256": "def456",
        "size": 0,
    }]
    manifest_path = write_manifest(session_dir, "PATCH-2", project, files_meta)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["files"][0]["action"] == "created"
    assert manifest["files"][0]["backup_rel"] is None


def test_manifest_deleted_action(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    target = tmp_path / "src" / "old.py"
    _write(target, "OLD\n")
    session_dir = create_session_dir(project, "PATCH-3")
    create_backup(project, target, "PATCH-3", session_dir=session_dir)

    files_meta = [{
        "rel_path": "src/old.py",
        "action": "deleted",
        "backup_rel": "src/old.py",
        "sha256": None,
        "size": 4,
    }]
    manifest_path = write_manifest(session_dir, "PATCH-3", project, files_meta)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["files"][0]["action"] == "deleted"
    assert manifest["files"][0]["sha256"] is None


def test_index_updated_after_session(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    target = tmp_path / "src" / "main.py"
    _write(target, "X\n")
    session_dir = create_session_dir(project, "PATCH-4")
    create_backup(project, target, "PATCH-4", session_dir=session_dir)

    index_path = update_index(project)

    assert index_path.exists()
    assert index_path.name == BACKUP_INDEX_FILENAME
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(index["sessions"]) >= 1
    session_ids = [s["session_id"] for s in index["sessions"]]
    assert session_dir.name in session_ids


def test_session_created_in_sessions_subdir(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    session = create_session_dir(project, "PATCH-5")

    assert session.parent.name == BACKUP_SESSIONS_SUBDIR
    assert session.parent.parent == project.backup_dir


def test_pre_flight_created_and_deleted(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    session = create_session_dir(project, "PATCH-6", subdir=BACKUP_PRE_FLIGHT_SUBDIR)

    assert session.parent.name == BACKUP_PRE_FLIGHT_SUBDIR
    assert session.parent.parent == project.backup_dir
    assert session.exists()

    deleted = delete_pre_flight_session(project, session.name)
    assert deleted
    assert not session.exists()
