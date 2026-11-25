"""Tests for profiles_sync auto-update."""
from __future__ import annotations

import json
from pathlib import Path

from apply_patch.profiles import PROFILES_TEMPLATE
from apply_patch.profiles_sync import (
    MARKER_END,
    MARKER_START,
    SyncResult,
    _extract_ids,
    _split_sections,
    update_all_profiles,
)


def _write_history(root: Path, entries: dict) -> None:
    path = root / ".apply_patch" / "patch_history.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": "1.1", "entries": entries}),
        encoding="utf-8",
    )


def _make_progress_report(
    task_name: str = "Test task",
    td_id: str = "TD-001",
    patch_suffix: str = "",
) -> dict:
    return {
        "task_name": task_name + patch_suffix,
        "objective_and_scope": "Test scope",
        "mandatory_info_for_next_ai": "Test context",
        "completed_functions": [{"id": "F-001", "name": "Do thing", "completed_at": "2026-11-09"}],
        "uncompleted_functions": [],
        "files_created": ["test.py"],
        "files_modified_or_deleted": [{"path": "test.py", "action": "modified"}],
        "significant_changes": ["Changed thing" + patch_suffix],
        "api_and_interface_changes": [
            {"file": "test.py", "kind": "function", "change": "sig changed"}
        ],
        "affected_modules": ["engine"],
        "source_tree": "test/",
        "test_results": [{"command": "pytest", "result": "OK"}],
        "remaining_issues_and_risks": [
            {"id": "RISK-001", "severity": "LOW", "description": "minor"}
        ],
        "technical_decisions": [
            {"id": td_id, "decision": "Use X", "rationale": "Because Y"}
        ],
        "proposed_next_work": [{"id": "N-001", "name": "Next", "priority": "HIGH"}],
    }


def test_creates_all_10_files_when_missing(tmp_path: Path) -> None:
    _write_history(tmp_path, {})
    result = update_all_profiles(tmp_path)
    assert isinstance(result, SyncResult)
    assert len(result.files_updated) == 10
    assert not result.errors
    profiles_dir = tmp_path / "profiles"
    for fname in PROFILES_TEMPLATE:
        assert (profiles_dir / fname).is_file()


def test_appends_auto_section_to_existing_goc(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "00_PROJECT_OVERVIEW.md").write_text(
        "# My project\n\nUser content here.\n", encoding="utf-8"
    )
    _write_history(
        tmp_path,
        {
            "p1.json": {
                "patch_id": "PATCH-2026-001",
                "applied_at": "2026-11-09T10:00:00",
                "progress_report_snapshot": _make_progress_report(),
            }
        },
    )
    update_all_profiles(tmp_path)
    content = (profiles_dir / "00_PROJECT_OVERVIEW.md").read_text(encoding="utf-8")
    assert "User content here." in content
    assert MARKER_START in content
    assert MARKER_END in content
    assert "PATCH-2026-001" in content


def test_idempotent_rerun(tmp_path: Path) -> None:
    _write_history(
        tmp_path,
        {
            "p1.json": {
                "patch_id": "PATCH-2026-001",
                "applied_at": "2026-11-09T10:00:00",
                "progress_report_snapshot": _make_progress_report(),
            }
        },
    )
    update_all_profiles(tmp_path)
    first = {
        f: (tmp_path / "profiles" / f).read_text(encoding="utf-8")
        for f in PROFILES_TEMPLATE
    }
    update_all_profiles(tmp_path)
    second = {
        f: (tmp_path / "profiles" / f).read_text(encoding="utf-8")
        for f in PROFILES_TEMPLATE
    }
    for fname in PROFILES_TEMPLATE:
        a = first[fname]
        b = second[fname]
        a_parts = [p for p in a.split("\n") if "Last update:" not in p]
        b_parts = [p for p in b.split("\n") if "Last update:" not in p]
        assert a_parts == b_parts, f"{fname} not idempotent"


def test_dedup_td_from_goc(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "06_TECHNICAL_DECISIONS.md").write_text(
        "# Decisions\n\n### TD-001: User wrote this\n", encoding="utf-8"
    )
    _write_history(
        tmp_path,
        {
            "p1.json": {
                "patch_id": "PATCH-2026-001",
                "applied_at": "2026-11-09T10:00:00",
                "progress_report_snapshot": _make_progress_report(td_id="TD-001"),
            }
        },
    )
    update_all_profiles(tmp_path)
    content = (profiles_dir / "06_TECHNICAL_DECISIONS.md").read_text(encoding="utf-8")
    parts = content.split(MARKER_START)
    assert len(parts) == 2
    auto_part = parts[1]
    assert "TD-001" not in auto_part


def test_new_td_appears(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "06_TECHNICAL_DECISIONS.md").write_text(
        "# Decisions\n", encoding="utf-8"
    )
    _write_history(
        tmp_path,
        {
            "p1.json": {
                "patch_id": "PATCH-2026-001",
                "applied_at": "2026-11-09T10:00:00",
                "progress_report_snapshot": _make_progress_report(td_id="TD-999"),
            }
        },
    )
    update_all_profiles(tmp_path)
    content = (profiles_dir / "06_TECHNICAL_DECISIONS.md").read_text(encoding="utf-8")
    assert "TD-999" in content


def test_database_design_note(tmp_path: Path) -> None:
    _write_history(tmp_path, {})
    update_all_profiles(tmp_path)
    content = (tmp_path / "profiles" / "04_DATABASE_DESIGN.md").read_text(encoding="utf-8")
    assert MARKER_START in content
    assert "No database schema" in content or "Database Changes" in content


def test_empty_history_no_crash(tmp_path: Path) -> None:
    result = update_all_profiles(tmp_path)
    assert not result.errors
    assert (tmp_path / "profiles" / "00_PROJECT_OVERVIEW.md").is_file()


def test_corrupt_history_no_crash(tmp_path: Path) -> None:
    path = tmp_path / ".apply_patch" / "patch_history.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json {{{", encoding="utf-8")
    result = update_all_profiles(tmp_path)
    assert not result.errors
    assert len(result.files_updated) == 10


def test_split_sections_no_marker() -> None:
    goc, auto = _split_sections("# Just content\n")
    assert auto == ""
    assert "Just content" in goc


def test_split_sections_with_marker() -> None:
    text = f"# Goc\n\n{MARKER_START}\nauto\n{MARKER_END}\n"
    goc, auto = _split_sections(text)
    assert "Goc" in goc
    assert "auto" in auto
    assert MARKER_START not in goc


def test_extract_ids() -> None:
    text = "PATCH-2026-001 and TD-100 and RISK-5 and N-1 and F-9"
    ids = _extract_ids(text)
    assert "PATCH-2026-001" in ids
    assert "TD-100" in ids
    assert "RISK-5" in ids
    assert "N-1" in ids
    assert "F-9" in ids


def test_changelog_contains_multiple_patches(tmp_path: Path) -> None:
    _write_history(
        tmp_path,
        {
            "p1.json": {
                "patch_id": "PATCH-2026-001",
                "applied_at": "2026-11-09T10:00:00",
                "progress_report_snapshot": _make_progress_report("Task A"),
            },
            "p2.json": {
                "patch_id": "PATCH-2026-002",
                "applied_at": "2026-11-09T11:00:00",
                "progress_report_snapshot": _make_progress_report("Task B"),
            },
        },
    )
    update_all_profiles(tmp_path)
    changelog = (tmp_path / "profiles" / "08_CHANGELOG.md").read_text(encoding="utf-8")
    assert "PATCH-2026-001" in changelog
    assert "PATCH-2026-002" in changelog


def test_affected_modules_dedup(tmp_path: Path) -> None:
    _write_history(
        tmp_path,
        {
            "p1.json": {
                "patch_id": "PATCH-2026-001",
                "applied_at": "2026-11-09T10:00:00",
                "progress_report_snapshot": _make_progress_report(),
            },
            "p2.json": {
                "patch_id": "PATCH-2026-002",
                "applied_at": "2026-11-09T11:00:00",
                "progress_report_snapshot": _make_progress_report(),
            },
        },
    )
    update_all_profiles(tmp_path)
    content = (tmp_path / "profiles" / "01_SYSTEM_ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    parts = content.split(MARKER_START)
    if len(parts) == 2:
        auto_part = parts[1]
        assert auto_part.count("`engine`") <= 1
