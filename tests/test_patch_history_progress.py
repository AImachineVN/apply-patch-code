"""Test patch history stores progress_report snapshot (H3 fix)."""
from __future__ import annotations

import json
from pathlib import Path

from apply_patch.patch_history import (
    HISTORY_SCHEMA_VERSION,
    PatchHistory,
)


def test_record_success_stores_progress_snapshot(tmp_path: Path) -> None:
    """record_success với progress_report_snapshot → lưu đúng."""
    history = PatchHistory()
    snapshot = {
        "task_name": "Test task",
        "objective_and_scope": "Test objective",
        "mandatory_info_for_next_ai": "Test info",
    }
    history.record_success(
        filename="patch_01.json",
        patch_id="P1",
        sha256="abc123",
        progress_report_snapshot=snapshot,
    )

    history_path = tmp_path / "history.json"
    history.save(history_path)

    loaded = PatchHistory.load(history_path)
    entry = loaded.get_entry("patch_01.json")
    assert entry is not None
    assert entry.progress_report_snapshot == snapshot
    assert loaded.schema_version == HISTORY_SCHEMA_VERSION


def test_record_success_without_progress_is_backward_compatible(
    tmp_path: Path,
) -> None:
    """Không truyền progress_report_snapshot → vẫn OK, field = None."""
    history = PatchHistory()
    history.record_success(
        filename="patch.json",
        patch_id="P",
        sha256="hash",
        # Không truyền progress_report_snapshot
    )

    entry = history.get_entry("patch.json")
    assert entry is not None
    assert entry.progress_report_snapshot is None


def test_load_old_history_without_snapshot(tmp_path: Path) -> None:
    """History cũ (schema 1.0, không có progress_report_snapshot) vẫn load được."""
    old_data = {
        "schema_version": "1.0",
        "entries": {
            "old_patch.json": {
                "patch_id": "P0",
                "applied_at": "2026-01-01T00:00:00",
                "sha256": "abc",
                "status": "applied",
            }
        },
    }
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps(old_data), encoding="utf-8")

    history = PatchHistory.load(history_path)
    assert history.schema_version == "1.0"
    assert not history.is_corrupt

    entry = history.get_entry("old_patch.json")
    assert entry is not None
    assert entry.patch_id == "P0"
    assert entry.progress_report_snapshot is None


def test_progress_report_full_roundtrip(tmp_path: Path) -> None:
    """Test roundtrip với ProgressReport dataclass thực tế."""
    from dataclasses import asdict

    from apply_patch.schema import ProgressReport

    report = ProgressReport(
        task_name="Full roundtrip",
        objective_and_scope="Objective X",
        mandatory_info_for_next_ai="Next AI must know Y",
    )
    snapshot = asdict(report)

    history = PatchHistory()
    history.record_success(
        filename="full.json",
        patch_id="P_FULL",
        sha256="hash_full",
        progress_report_snapshot=snapshot,
    )
    history_path = tmp_path / "history.json"
    history.save(history_path)

    loaded = PatchHistory.load(history_path)
    entry = loaded.get_entry("full.json")
    assert entry is not None
    assert entry.progress_report_snapshot is not None
    assert entry.progress_report_snapshot["task_name"] == "Full roundtrip"
    assert entry.progress_report_snapshot["objective_and_scope"] == "Objective X"
    assert entry.progress_report_snapshot["mandatory_info_for_next_ai"] == "Next AI must know Y"