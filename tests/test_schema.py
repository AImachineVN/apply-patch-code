import json
from pathlib import Path

import pytest

from apply_patch.context import SchemaError
from apply_patch.schema import load_patch


def _make_progress(task_name: str = "Test task") -> dict:
    """Sinh progress_report tối giản hợp lệ cho test."""
    return {
        "task_name": task_name,
        "objective_and_scope": "Unit test objective",
        "mandatory_info_for_next_ai": "Test context info",
    }


def test_load_legacy_patch_normalizes_keys_and_structural_values(tmp_path: Path) -> None:
    data = {
        "version ": "1.0 ",
        "description ": "Test legacy",
        "progress_report": _make_progress("Legacy normalize"),
        "patches ": [
            {
                "file ": "a.py ",
                "verify_markers ": [
                    "print ",
                ],
                "operations ": [
                    {
                        "type ": "replace ",
                        "old_text ": "print(1)",
                        "new_text ": "print(2)",
                    }
                ],
            }
        ],
    }
    patch_path = tmp_path / "legacy.json"
    patch_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    manifest = load_patch(patch_path)
    assert manifest.schema_version == "1.0"
    assert manifest.patches[0].file == "a.py"
    assert manifest.patches[0].verify_markers == ["print"]
    assert manifest.patches[0].operations[0]["type"] == "replace"
    assert manifest.patches[0].operations[0]["old_text"] == "print(1)"
    assert manifest.patches[0].operations[0]["new_text"] == "print(2)"
    assert manifest.progress_report is not None
    assert manifest.progress_report.task_name == "Legacy normalize"


def test_invalid_operation_type_raises_schema_error(tmp_path: Path) -> None:
    data = {
        "schema_version": "2.0",
        "patch_id": "test",
        "progress_report": _make_progress("Invalid op type"),
        "patches": [
            {
                "file": "a.py",
                "operations": [
                    {
                        "type": "invalid_operation",
                    }
                ],
            }
        ],
    }
    patch_path = tmp_path / "invalid.json"
    patch_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SchemaError):
        load_patch(patch_path)


def test_missing_progress_report_raises_schema_error(tmp_path: Path) -> None:
    """Patch thiếu progress_report phải bị reject (bắt buộc tuyệt đối)."""
    data = {
        "schema_version": "2.0",
        "patch_id": "test",
        "patches": [
            {
                "file": "a.py",
                "operations": [
                    {"type": "replace", "old_text": "x", "new_text": "y"}
                ],
            }
        ],
    }
    patch_path = tmp_path / "no_progress.json"
    patch_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SchemaError) as exc_info:
        load_patch(patch_path)
    assert "progress_report" in str(exc_info.value)


def test_progress_report_missing_required_field_raises_schema_error(tmp_path: Path) -> None:
    """progress_report thiếu field bắt buộc phải bị reject."""
    data = {
        "schema_version": "2.0",
        "patch_id": "test",
        "progress_report": {
            "task_name": "Task",
            # Thiếu objective_and_scope và mandatory_info_for_next_ai
        },
        "patches": [
            {
                "file": "a.py",
                "operations": [
                    {"type": "replace", "old_text": "x", "new_text": "y"}
                ],
            }
        ],
    }
    patch_path = tmp_path / "bad_progress.json"
    patch_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SchemaError):
        load_patch(patch_path)


def test_progress_report_empty_required_fields_raises_schema_error(tmp_path: Path) -> None:
    """progress_report có 3 trường bắt buộc nhưng rỗng phải bị reject."""
    data = {
        "schema_version": "2.0",
        "patch_id": "test",
        "progress_report": {
            "task_name": "",
            "objective_and_scope": "Valid",
            "mandatory_info_for_next_ai": "Valid",
        },
        "patches": [
            {
                "file": "a.py",
                "operations": [
                    {"type": "replace", "old_text": "x", "new_text": "y"}
                ],
            }
        ],
    }
    patch_path = tmp_path / "empty.json"
    patch_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SchemaError):
        load_patch(patch_path)