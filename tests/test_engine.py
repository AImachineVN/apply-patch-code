from __future__ import annotations

import json
from pathlib import Path

from apply_patch.context import ExecutionContext
from apply_patch.discovery import init_project, load_project_from_path
from apply_patch.engine import apply_patch_to_project
from apply_patch.schema import PatchManifest, load_patch


def _make_progress(task_name: str = "Test task") -> dict:
    """Sinh progress_report tối giản hợp lệ cho test."""
    return {
        "task_name": task_name,
        "objective_and_scope": "Unit test objective",
        "mandatory_info_for_next_ai": "Test context info",
    }


def test_apply_replace_operation_and_create_backup(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    target_file = project_dir / "a.py"
    target_file.write_text("print('old')\n", encoding="utf-8")
    init_project(
        path=project_dir,
        project_id="proj",
        project_type="python",
        markers=[],
        overwrite=True,
    )

    manifest = PatchManifest.from_dict(
        {
            "schema_version": "2.0",
            "patch_id": "test_patch",
            "progress_report": _make_progress("Replace and backup"),
            "patches": [
                {
                    "file": "a.py",
                    "operations": [
                        {
                            "type": "replace",
                            "old_text": "old",
                            "new_text": "new",
                        }
                    ],
                    "verify_after": {
                        "contains": ["print('new')"],
                        "not_contains": ["print('old')"],
                    },
                }
            ],
        }
    )

    project = load_project_from_path(project_dir)
    context = ExecutionContext(
        project=project,
        dry_run=False,
        json_output=False,
        patch_path=tmp_path / "test_patch.json",
    )

    report = apply_patch_to_project(context, manifest)
    assert report.success is True
    assert target_file.read_text(encoding="utf-8") == "print('new')\n"
    assert report.files[0].status == "ok"
    assert report.files[0].changed is True
    assert report.files[0].backup_path is not None
    assert report.files[0].backup_path.exists()


def test_dry_run_does_not_modify_file(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    target_file = project_dir / "a.py"
    original_content = "print('old')\n"
    target_file.write_text(original_content, encoding="utf-8")
    init_project(
        path=project_dir,
        project_id="proj",
        project_type="python",
        markers=[],
        overwrite=True,
    )

    manifest = PatchManifest.from_dict(
        {
            "schema_version": "2.0",
            "patch_id": "test_patch",
            "progress_report": _make_progress("Dry-run test"),
            "patches": [
                {
                    "file": "a.py",
                    "operations": [
                        {
                            "type": "replace",
                            "old_text": "old",
                            "new_text": "new",
                        }
                    ],
                }
            ],
        }
    )

    project = load_project_from_path(project_dir)
    context = ExecutionContext(
        project=project,
        dry_run=True,
        json_output=False,
        patch_path=tmp_path / "test_patch.json",
    )

    report = apply_patch_to_project(context, manifest)
    assert report.success is True
    assert target_file.read_text(encoding="utf-8") == original_content
    assert report.files[0].changed is True


def test_auto_create_file_with_write_content(tmp_path: Path) -> None:
    """Auto-create: file + parent dirs created when first op is write_content."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    init_project(
        path=project_dir, project_id="proj", project_type="python",
        markers=[], overwrite=True,
    )

    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "schema_version": "2.0",
        "patch_id": "auto-create-test",
        "progress_report": _make_progress("Auto-create test"),
        "patches": [{
            "file": "src/new_module/utils.py",
            "operations": [{
                "type": "write_content",
                "content": "def helper(): pass\n"
            }]
        }]
    }), encoding="utf-8")

    project = load_project_from_path(project_dir)
    context = ExecutionContext(
        project=project, dry_run=False, json_output=False,
        patch_path=patch_path,
    )

    report = apply_patch_to_project(context, load_patch(patch_path))
    assert report.success is True
    created_file = project_dir / "src" / "new_module" / "utils.py"
    assert created_file.exists()
    assert created_file.read_text(encoding="utf-8") == "def helper(): pass\n"


def test_create_directory_operation(tmp_path: Path) -> None:
    """Operation create_directory creates an empty directory tree."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    init_project(
        path=project_dir, project_id="proj", project_type="python",
        markers=[], overwrite=True,
    )

    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "schema_version": "2.0",
        "patch_id": "dir-create-test",
        "progress_report": _make_progress("Dir create test"),
        "patches": [
            {"type": "create_directory", "path": "docs/api/v2"},
            {"type": "create_directory", "path": "logs"}
        ]
    }), encoding="utf-8")

    project = load_project_from_path(project_dir)
    context = ExecutionContext(
        project=project, dry_run=False, json_output=False,
        patch_path=patch_path,
    )

    report = apply_patch_to_project(context, load_patch(patch_path))
    assert report.success is True
    assert (project_dir / "docs" / "api" / "v2").is_dir()
    assert (project_dir / "logs").is_dir()