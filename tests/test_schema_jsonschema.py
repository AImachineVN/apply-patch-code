"""Test _validate_with_jsonschema behavior (fix H2)."""
from __future__ import annotations

import logging

import pytest

from apply_patch import schema as schema_module
from apply_patch.context import SchemaError


def _make_minimal_valid_patch() -> dict:
    """Patch tối thiểu hợp lệ để pass layer 1."""
    return {
        "schema_version": "2.0",
        "patch_id": "test_patch",
        "progress_report": {
            "task_name": "Test",
            "objective_and_scope": "Test",
            "mandatory_info_for_next_ai": "Test",
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


def test_schema_missing_warns_once(monkeypatch, caplog, tmp_path) -> None:
    """Schema file missing → warn 1 lần, không raise (build issue)."""
    monkeypatch.setattr(schema_module, "_schema_missing_warned", False)
    fake_path = tmp_path / "nonexistent" / "patch_v2.json"
    # Không tạo file → exists() trả False

    import apply_patch.utils.path_resolver as pr
    monkeypatch.setattr(pr, "get_resource_path", lambda rel: fake_path)

    with caplog.at_level(logging.WARNING):
        schema_module._validate_with_jsonschema(_make_minimal_valid_patch())
        schema_module._validate_with_jsonschema(_make_minimal_valid_patch())

    # Chỉ warn 1 lần (không spam)
    schema_warns = [r for r in caplog.records if "JSON Schema file not found" in r.message]
    assert len(schema_warns) == 1


def test_schema_corrupt_raises_schema_error(monkeypatch, tmp_path) -> None:
    """Schema file tồn tại nhưng corrupt → raise SchemaError."""
    fake_schema = tmp_path / "patch_v2.json"
    fake_schema.write_text("{invalid json", encoding="utf-8")

    import apply_patch.utils.path_resolver as pr
    monkeypatch.setattr(pr, "get_resource_path", lambda rel: fake_schema)

    with pytest.raises(SchemaError, match="corrupt"):
        schema_module._validate_with_jsonschema(_make_minimal_valid_patch())


def test_jsonschema_unavailable_skips_silently(monkeypatch) -> None:
    """jsonschema không cài → skip hoàn toàn, không raise."""
    monkeypatch.setattr(schema_module, "_JSONSCHEMA_AVAILABLE", False)
    # Không raise
    schema_module._validate_with_jsonschema(_make_minimal_valid_patch())