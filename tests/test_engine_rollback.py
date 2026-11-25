"""Test rollback behavior for created files/dirs (C3 fix)."""
from __future__ import annotations

import json
from pathlib import Path

from apply_patch.context import ExecutionContext
from apply_patch.discovery import init_project, load_project_from_path
from apply_patch.engine import apply_patch_to_project
from apply_patch.schema import load_patch


def _make_progress(task_name: str = "Rollback test") -> dict:
    return {
        "task_name": task_name,
        "objective_and_scope": "Test rollback cleanup",
        "mandatory_info_for_next_ai": "Test context",
    }


def _setup_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    init_project(
        path=project_dir, project_id="proj", project_type="python",
        markers=[], overwrite=True,
    )
    return project_dir


def _apply_patch(
    project_dir: Path, patch_data: dict, patch_name: str = "patch.json"
):
    patch_path = project_dir.parent / patch_name
    patch_path.write_text(json.dumps(patch_data), encoding="utf-8")
    project = load_project_from_path(project_dir)
    context = ExecutionContext(
        project=project,
        dry_run=False,
        json_output=False,
        patch_path=patch_path,
    )
    return apply_patch_to_project(context, load_patch(patch_path))


def test_rollback_removes_created_files(tmp_path: Path) -> None:
    """Patch tạo file mới, sau đó fail → file mới phải bị xóa."""
    project_dir = _setup_project(tmp_path)

    patch = {
        "schema_version": "2.0",
        "patch_id": "test_rollback_created_file",
        "rollback_on_verify_failure": True,
        "progress_report": _make_progress(),
        "patches": [
            {
                "file": "new_A.py",
                "operations": [{"type": "write_content", "content": "x = 1\n"}],
            },
            {
                "file": "nonexistent_B.py",
                "operations": [{"type": "replace", "old_text": "a", "new_text": "b"}],
            },
        ],
    }

    report = _apply_patch(project_dir, patch)

    assert report.success is False
    assert not (project_dir / "new_A.py").exists(), (
        "File new_A.py must be removed during rollback"
    )


def test_rollback_removes_created_dirs(tmp_path: Path) -> None:
    """Patch tạo directory, sau đó fail → dir phải bị xóa."""
    project_dir = _setup_project(tmp_path)

    patch = {
        "schema_version": "2.0",
        "patch_id": "test_rollback_created_dir",
        "rollback_on_verify_failure": True,
        "progress_report": _make_progress(),
        "patches": [
            {"type": "create_directory", "path": "new_folder"},
            {
                "file": "nonexistent.py",
                "operations": [{"type": "replace", "old_text": "a", "new_text": "b"}],
            },
        ],
    }

    report = _apply_patch(project_dir, patch)

    assert report.success is False
    assert not (project_dir / "new_folder").exists(), (
        "Directory new_folder must be removed during rollback"
    )


def test_rollback_removes_nested_created_resources(tmp_path: Path) -> None:
    """Dir + file trong dir đều được tạo → rollback phải xóa cả 2."""
    project_dir = _setup_project(tmp_path)

    patch = {
        "schema_version": "2.0",
        "patch_id": "test_rollback_nested",
        "rollback_on_verify_failure": True,
        "progress_report": _make_progress(),
        "patches": [
            {"type": "create_directory", "path": "src/sub"},
            {
                "file": "src/sub/module.py",
                "operations": [{"type": "write_content", "content": "# new\n"}],
            },
            {
                "file": "nonexistent.py",
                "operations": [{"type": "replace", "old_text": "a", "new_text": "b"}],
            },
        ],
    }

    report = _apply_patch(project_dir, patch)

    assert report.success is False
    # File bên trong phải bị xóa trước, sau đó dir rỗng mới bị xóa
    assert not (project_dir / "src" / "sub" / "module.py").exists()
    assert not (project_dir / "src" / "sub").exists(), (
        "Directory src/sub must be removed after its contents are gone"
    )


def test_rollback_preserves_preexisting_files(tmp_path: Path) -> None:
    """File có từ trước được restore từ backup, không bị xóa."""
    project_dir = _setup_project(tmp_path)
    existing = project_dir / "existing.py"
    existing.write_text("original content\n", encoding="utf-8")

    patch = {
        "schema_version": "2.0",
        "patch_id": "test_rollback_preexisting",
        "rollback_on_verify_failure": True,
        "progress_report": _make_progress(),
        "patches": [
            {
                "file": "existing.py",
                "operations": [{"type": "replace", "old_text": "original", "new_text": "MODIFIED"}],
            },
            {
                "file": "nonexistent.py",
                "operations": [{"type": "replace", "old_text": "a", "new_text": "b"}],
            },
        ],
    }

    report = _apply_patch(project_dir, patch)

    assert report.success is False
    # File có từ trước phải được restore về nội dung gốc
    assert existing.exists()
    assert existing.read_text(encoding="utf-8") == "original content\n"


def test_no_cleanup_when_rollback_disabled(tmp_path: Path) -> None:
    """Regression: rollback_on_verify_failure=False → không cleanup (giữ behavior cũ)."""
    project_dir = _setup_project(tmp_path)

    patch = {
        "schema_version": "2.0",
        "patch_id": "test_no_rollback",
        "rollback_on_verify_failure": False,  # DISABLED
        "progress_report": _make_progress(),
        "patches": [
            {
                "file": "new_A.py",
                "operations": [{"type": "write_content", "content": "x = 1\n"}],
            },
            {
                "file": "nonexistent.py",
                "operations": [{"type": "replace", "old_text": "a", "new_text": "b"}],
            },
        ],
    }

    report = _apply_patch(project_dir, patch)

    assert report.success is False
    # File mới KHÔNG bị xóa vì rollback tắt
    assert (project_dir / "new_A.py").exists(), (
        "File new_A.py must remain when rollback_on_verify_failure=False"
    )