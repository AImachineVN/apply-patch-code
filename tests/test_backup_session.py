"""Test backup session layout (Gap 1 + Gap 4)."""
from __future__ import annotations

import json
from pathlib import Path

from apply_patch.backup import (
    SESSION_METADATA_FILENAME,
    create_backup,
    create_session_dir,
    list_backups,
    rollback_backup_path,
    write_session_metadata,
)
from apply_patch.context import ProjectDescriptor


def _make_project(root: Path) -> ProjectDescriptor:
    return ProjectDescriptor(
        root=root,
        project_id="test_proj",
        project_type="python",
        markers=[],
        source_roots=["."],
        exclude=[],
        manifest_path=None,
        legacy=True,
        default_language="python",
    )


def test_backup_dir_is_apply_patch_backup(tmp_path: Path) -> None:
    """[GAP-1] backup_dir must be <root>/apply_patch_backup (visible)."""
    project = _make_project(tmp_path)
    assert project.backup_dir == tmp_path / "apply_patch_backup"
    assert project.backup_dir != tmp_path / ".apply_patch" / "backups"


def test_create_session_dir_has_patch_id_and_timestamp(tmp_path: Path) -> None:
    """[GAP-4] Session dir name = <patch_id>_<timestamp>."""
    project = _make_project(tmp_path)
    session = create_session_dir(project, "PATCH-2026-001")

    assert session.exists()
    assert session.parent == project.backup_dir / "sessions"
    assert session.name.startswith("PATCH-2026-001_")


def test_create_session_dir_sanitizes_patch_id(tmp_path: Path) -> None:
    """[GAP-4] Patch ID with unsafe chars is sanitized."""
    project = _make_project(tmp_path)
    session = create_session_dir(project, "PATCH/2026:001")  # unsafe chars

    assert session.exists()
    assert "/" not in session.name
    assert ":" not in session.name


def test_create_backup_uses_session_dir(tmp_path: Path) -> None:
    """[GAP-4] All files share same session dir when passed explicitly."""
    project = _make_project(tmp_path)

    file_a = tmp_path / "src" / "a.py"
    file_a.parent.mkdir(parents=True)
    file_a.write_text("a = 1\n", encoding="utf-8")

    file_b = tmp_path / "src" / "b.py"
    file_b.write_text("b = 2\n", encoding="utf-8")

    session = create_session_dir(project, "PATCH-TEST")
    record_a = create_backup(project, file_a, "PATCH-TEST", session_dir=session)
    record_b = create_backup(project, file_b, "PATCH-TEST", session_dir=session)

    assert record_a.session_id == session.name
    assert record_b.session_id == session.name
    assert record_a.backup_file.parent == session / "src"
    assert record_b.backup_file.parent == session / "src"


def test_create_backup_preserves_project_structure(tmp_path: Path) -> None:
    """[GAP-3] Backup keeps relative path structure."""
    project = _make_project(tmp_path)
    nested = tmp_path / "src" / "sub" / "deep" / "module.py"
    nested.parent.mkdir(parents=True)
    nested.write_text("x = 1\n", encoding="utf-8")

    session = create_session_dir(project, "PATCH-NESTED")
    record = create_backup(project, nested, "PATCH-NESTED", session_dir=session)

    expected = session / "src" / "sub" / "deep" / "module.py"
    assert record.backup_file == expected.resolve()
    assert expected.exists()
    assert expected.read_text(encoding="utf-8") == "x = 1\n"


def test_write_session_metadata_creates_file(tmp_path: Path) -> None:
    """[GAP-4] Session metadata file is written at end of session."""
    project = _make_project(tmp_path)
    session = create_session_dir(project, "PATCH-META")

    path = write_session_metadata(
        session_dir=session,
        project=project,
        patch_id="PATCH-META",
        files=[
            {"file": "src/a.py", "status": "ok", "backup_path": None},
        ],
        success=True,
    )

    assert path.exists()
    assert path.name == SESSION_METADATA_FILENAME

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["patch_id"] == "PATCH-META"
    assert data["session_id"] == session.name
    assert data["success"] is True
    assert data["file_count"] == 1
    assert data["files"][0]["file"] == "src/a.py"


def test_list_backups_scans_session_layout(tmp_path: Path) -> None:
    """[GAP-1+4] list_backups works with new session layout."""
    project = _make_project(tmp_path)

    file_a = tmp_path / "a.py"
    file_a.write_text("x = 1\n", encoding="utf-8")

    session = create_session_dir(project, "PATCH-LIST")
    create_backup(project, file_a, "PATCH-LIST", session_dir=session)
    write_session_metadata(session, project, "PATCH-LIST", [], True)

    records = list_backups(project)
    assert len(records) == 1
    assert records[0].original_rel == "a.py"
    assert records[0].session_id == session.name


def test_rollback_from_session_layout(tmp_path: Path) -> None:
    """[GAP-5] Rollback restores from new layout correctly."""
    project = _make_project(tmp_path)

    file_a = tmp_path / "a.py"
    file_a.write_text("original\n", encoding="utf-8")

    session = create_session_dir(project, "PATCH-RB")
    record = create_backup(project, file_a, "PATCH-RB", session_dir=session)

    # Modify original, then rollback
    file_a.write_text("modified\n", encoding="utf-8")
    restored = rollback_backup_path(project, record.backup_file)

    assert restored == file_a.resolve()
    assert file_a.read_text(encoding="utf-8") == "original\n"


def test_backup_record_session_id_field(tmp_path: Path) -> None:
    """[GAP-4] BackupRecord stores session_id field."""
    project = _make_project(tmp_path)
    file_a = tmp_path / "a.py"
    file_a.write_text("x\n", encoding="utf-8")

    session = create_session_dir(project, "PATCH-SESSION-ID")
    record = create_backup(project, file_a, "PATCH-SESSION-ID", session_dir=session)

    assert hasattr(record, "session_id")
    assert record.session_id == session.name
    assert record.session_id in record.to_dict()["session_id"]