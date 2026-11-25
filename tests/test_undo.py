"""Tests for undo_patch (Undo Execute backend)."""
from __future__ import annotations

from pathlib import Path

from apply_patch.backup import (
    create_backup,
    create_session_dir,
    write_manifest,
)
from apply_patch.context import ProjectDescriptor
from apply_patch.patch_history import PatchHistory, get_history_path
from apply_patch.undo import undo_patch
from apply_patch.utils import sha256_file


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


def _record_history(tmp_path: Path, filename: str, patch_id: str) -> None:
    history = PatchHistory.load(get_history_path(tmp_path))
    history.record_success(filename, patch_id, "sha-xxx")
    history.save(get_history_path(tmp_path))


def _setup_modified(
    tmp_path: Path,
    patch_id: str = "PATCH-TEST",
    original: str = "OLD_CONTENT\n",
    new: str = "NEW_CONTENT\n",
) -> tuple[ProjectDescriptor, Path, Path]:
    """Setup: file originally = original, patch changed to new, backup exists."""
    project = _make_project(tmp_path)
    target = tmp_path / "src" / "main.py"
    _write(target, original)

    session_dir = create_session_dir(project, patch_id)
    create_backup(project, target, patch_id, session_dir=session_dir)

    # Simulate patch apply
    _write(target, new)
    post_sha = sha256_file(target)

    files_meta = [{
        "rel_path": "src/main.py",
        "action": "modified",
        "backup_rel": "src/main.py",
        "sha256": post_sha,
        "size": len(original.encode("utf-8")),
    }]
    write_manifest(session_dir, patch_id, project, files_meta)
    _record_history(tmp_path, "Patch_1_TEST.json", patch_id)
    return project, session_dir, target


def test_undo_modified_file_restores(tmp_path: Path) -> None:
    project, _session, target = _setup_modified(tmp_path)
    result = undo_patch(project, "PATCH-TEST")
    assert result.success
    assert "src/main.py" in result.restored_files
    assert target.read_text(encoding="utf-8") == "OLD_CONTENT\n"


def test_undo_created_file_deletes(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    target = tmp_path / "src" / "new.py"
    _write(target, "NEW_FILE\n")
    post_sha = sha256_file(target)

    session_dir = create_session_dir(project, "PATCH-TEST")
    files_meta = [{
        "rel_path": "src/new.py",
        "action": "created",
        "backup_rel": None,
        "sha256": post_sha,
        "size": 0,
    }]
    write_manifest(session_dir, "PATCH-TEST", project, files_meta)
    _record_history(tmp_path, "Patch_1_TEST.json", "PATCH-TEST")

    result = undo_patch(project, "PATCH-TEST")
    assert result.success
    assert "src/new.py" in result.deleted_files
    assert not target.exists()


def test_undo_deleted_file_restores(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    target = tmp_path / "src" / "main.py"
    _write(target, "ORIGINAL\n")

    session_dir = create_session_dir(project, "PATCH-TEST")
    create_backup(project, target, "PATCH-TEST", session_dir=session_dir)

    # Simulate patch: delete target
    target.unlink()

    files_meta = [{
        "rel_path": "src/main.py",
        "action": "deleted",
        "backup_rel": "src/main.py",
        "sha256": None,
        "size": 9,
    }]
    write_manifest(session_dir, "PATCH-TEST", project, files_meta)
    _record_history(tmp_path, "Patch_1_TEST.json", "PATCH-TEST")

    result = undo_patch(project, "PATCH-TEST")
    assert result.success
    assert "src/main.py" in result.restored_files
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "ORIGINAL\n"


def test_undo_no_session_fails(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    result = undo_patch(project, "PATCH-NOT-EXISTS")
    assert not result.success
    assert "not found" in result.message.lower()


def test_undo_no_manifest_fails(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    create_session_dir(project, "PATCH-NO-MANIFEST")
    result = undo_patch(project, "PATCH-NO-MANIFEST")
    assert not result.success
    assert "manifest" in result.message.lower()


def test_undo_modified_file_refused(tmp_path: Path) -> None:
    project, _session, target = _setup_modified(tmp_path)
    # User edits after apply
    _write(target, "USER_EDITED\n")
    result = undo_patch(project, "PATCH-TEST")
    assert not result.success
    assert "src/main.py" in result.modified_files
    assert target.read_text(encoding="utf-8") == "USER_EDITED\n"


def test_undo_missing_original_recreates(tmp_path: Path) -> None:
    project, _session, target = _setup_modified(tmp_path)
    target.unlink()
    result = undo_patch(project, "PATCH-TEST")
    assert result.success
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "OLD_CONTENT\n"


def test_undo_missing_backup_fails(tmp_path: Path) -> None:
    project, session, _target = _setup_modified(tmp_path)
    backup_file = session / "src" / "main.py"
    backup_file.unlink()
    result = undo_patch(project, "PATCH-TEST")
    assert not result.success


def test_undo_updates_history_status(tmp_path: Path) -> None:
    project, _session, _target = _setup_modified(tmp_path)
    undo_patch(project, "PATCH-TEST")
    history = PatchHistory.load(get_history_path(tmp_path))
    entry = history.get_entry("Patch_1_TEST.json")
    assert entry is not None
    assert entry.status == "undone"


def test_undo_sets_undone_at(tmp_path: Path) -> None:
    project, _session, _target = _setup_modified(tmp_path)
    undo_patch(project, "PATCH-TEST")
    history = PatchHistory.load(get_history_path(tmp_path))
    entry = history.get_entry("Patch_1_TEST.json")
    assert entry is not None
    assert entry.undone_at != ""


def test_undo_multiple_files_all_restored(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    f1 = tmp_path / "src" / "a.py"
    f2 = tmp_path / "src" / "b.py"
    _write(f1, "ORIG_A\n")
    _write(f2, "ORIG_B\n")

    session_dir = create_session_dir(project, "PATCH-MULTI")
    create_backup(project, f1, "PATCH-MULTI", session_dir=session_dir)
    create_backup(project, f2, "PATCH-MULTI", session_dir=session_dir)

    _write(f1, "NEW_A\n")
    _write(f2, "NEW_B\n")

    files_meta = [
        {"rel_path": "src/a.py", "action": "modified", "backup_rel": "src/a.py", "sha256": sha256_file(f1), "size": 7},
        {"rel_path": "src/b.py", "action": "modified", "backup_rel": "src/b.py", "sha256": sha256_file(f2), "size": 7},
    ]
    write_manifest(session_dir, "PATCH-MULTI", project, files_meta)
    _record_history(tmp_path, "Patch_1_TEST.json", "PATCH-MULTI")

    result = undo_patch(project, "PATCH-MULTI")
    assert result.success
    assert len(result.restored_files) == 2
    assert f1.read_text(encoding="utf-8") == "ORIG_A\n"
    assert f2.read_text(encoding="utf-8") == "ORIG_B\n"


def test_undo_result_message_reports_counts(tmp_path: Path) -> None:
    project, _session, _target = _setup_modified(tmp_path)
    result = undo_patch(project, "PATCH-TEST")
    assert result.success
    assert "restored" in result.message.lower() or "succeeded" in result.message.lower()


def test_undo_history_empty_still_works(tmp_path: Path) -> None:
    project, _session, target = _setup_modified(tmp_path)
    get_history_path(tmp_path).unlink()
    result = undo_patch(project, "PATCH-TEST")
    assert result.success
    assert target.read_text(encoding="utf-8") == "OLD_CONTENT\n"


def test_undo_user_recreated_deleted_file_refused(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    target = tmp_path / "src" / "main.py"
    _write(target, "ORIGINAL\n")

    session_dir = create_session_dir(project, "PATCH-TEST")
    create_backup(project, target, "PATCH-TEST", session_dir=session_dir)
    target.unlink()  # Patch deleted it

    files_meta = [{
        "rel_path": "src/main.py",
        "action": "deleted",
        "backup_rel": "src/main.py",
        "sha256": None,
        "size": 9,
    }]
    write_manifest(session_dir, "PATCH-TEST", project, files_meta)
    _record_history(tmp_path, "Patch_1_TEST.json", "PATCH-TEST")

    # User recreates the file
    _write(target, "USER_RECREATED\n")

    result = undo_patch(project, "PATCH-TEST")
    assert not result.success
    assert "src/main.py" in result.modified_files
    assert target.read_text(encoding="utf-8") == "USER_RECREATED\n"


def test_cli_record_patch_history_helper(tmp_path: Path) -> None:
    """_record_patch_history writes entry to patch_history.json (CLI path)."""
    from apply_patch.cli import _record_patch_history

    class _FakeManifest:
        patch_id = "PATCH-CLI-TEST"
        progress_report = None

    project = _make_project(tmp_path)
    patch_file = tmp_path / "Patches" / "Patch_CLI_TEST.json"
    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text('{"patch_id": "PATCH-CLI-TEST"}', encoding="utf-8")

    _record_patch_history(project, patch_file, _FakeManifest())

    history = PatchHistory.load(get_history_path(tmp_path))
    entry = history.get_entry("Patch_CLI_TEST.json")
    assert entry is not None
    assert entry.patch_id == "PATCH-CLI-TEST"
    assert entry.status == "applied"


def test_undo_noop_file_skipped(tmp_path: Path) -> None:
    """No-op files (not created, not changed) must not appear in manifest."""
    from apply_patch.backup import create_session_dir, read_manifest, write_manifest

    project = _make_project(tmp_path)
    session_dir = create_session_dir(project, "PATCH-NOOP")
    write_manifest(session_dir, "PATCH-NOOP", project, [])
    manifest = read_manifest(session_dir)
    assert manifest["files"] == []
