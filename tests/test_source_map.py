"""Tests for source_map module."""
from __future__ import annotations

import json
from pathlib import Path

from apply_patch.context import FilePatchResult, PatchReport, ProjectDescriptor
from apply_patch.source_map import (
    SourceFileStat,
    SourceFolderStat,
    SourceMap,
    heuristic_folders,
    load_source_map,
    migrate_from_history,
    save_source_map,
    update_from_apply,
)


def _make_project(tmp_path: Path, project_id: str = "test_project") -> ProjectDescriptor:
    return ProjectDescriptor(
        root=tmp_path,
        project_id=project_id,
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


def _make_report(project: ProjectDescriptor, files_data: list[dict]) -> PatchReport:
    report = PatchReport(
        patch_path=Path("dummy.json"),
        project_root=project.root,
        project_id=project.project_id,
        dry_run=False,
        success=True,
    )
    report.files = [
        FilePatchResult(
            file=fd["file"],
            status=str(fd.get("status", "ok")),
            created=bool(fd.get("created", False)),
            changed=bool(fd.get("changed", True)),
        )
        for fd in files_data
    ]
    return report


def test_load_empty_returns_default(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    smap = load_source_map(project)
    assert smap.schema_version == "1.0"
    assert smap.source_files == {}
    assert smap.source_folders == {}
    assert smap.is_migrated is False


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    smap = SourceMap()
    smap.source_files["src/main.py"] = SourceFileStat(
        patch_count=3, typical_size=994, last_patched="2026-11-20T"
    )
    smap.source_folders["src"] = SourceFolderStat(
        patch_count=3, first_seen="2026-11-01T", last_patched="2026-11-20T", file_count=1
    )
    assert save_source_map(project, smap)

    loaded = load_source_map(project)
    assert loaded.source_files["src/main.py"].patch_count == 3
    assert loaded.source_files["src/main.py"].typical_size == 994
    assert loaded.source_folders["src"].file_count == 1


def test_update_from_apply_new_file(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _write(project.root / "src" / "main.py", "print('hi')\n" * 100)

    report = _make_report(project, [{"file": "src/main.py", "created": True, "changed": True}])
    smap = update_from_apply(project, report)

    assert "src/main.py" in smap.source_files
    assert smap.source_files["src/main.py"].patch_count == 1
    assert smap.source_files["src/main.py"].typical_size > 0


def test_update_from_apply_existing_increments(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _write(project.root / "src" / "main.py", "x = 1\n" * 100)

    report1 = _make_report(project, [{"file": "src/main.py", "changed": True}])
    update_from_apply(project, report1)

    report2 = _make_report(project, [{"file": "src/main.py", "changed": True}])
    smap = update_from_apply(project, report2)

    assert smap.source_files["src/main.py"].patch_count == 2


def test_update_from_apply_typical_size(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    content = "hello world " * 500
    _write(project.root / "src" / "main.py", content)

    report = _make_report(project, [{"file": "src/main.py", "changed": True}])
    smap = update_from_apply(project, report)

    expected_size = (project.root / "src" / "main.py").stat().st_size
    assert smap.source_files["src/main.py"].typical_size == expected_size


def test_update_from_apply_folder_count(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _write(project.root / "src" / "a.py", "x = 1")
    _write(project.root / "src" / "b.py", "y = 2")

    report = _make_report(project, [
        {"file": "src/a.py", "changed": True},
        {"file": "src/b.py", "changed": True},
    ])
    smap = update_from_apply(project, report)

    assert "src" in smap.source_folders
    assert smap.source_folders["src"].file_count == 2


def test_update_from_apply_skips_failed(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _write(project.root / "src" / "main.py", "x = 1")

    report = _make_report(project, [{"file": "src/main.py", "status": "failed"}])
    smap = update_from_apply(project, report)

    assert "src/main.py" not in smap.source_files


def test_migrate_from_history_patch_history(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _write(project.root / "src" / "main.py", "x = 1")

    history_data = {
        "schema_version": "1.2",
        "entries": {
            "Patch_1.json": {
                "patch_id": "PATCH-1",
                "progress_report_snapshot": {
                    "files_created": ["src/main.py"],
                    "files_modified_or_deleted": [],
                },
            }
        },
    }
    _write(project.root / ".apply_patch" / "patch_history.json", json.dumps(history_data))

    count = migrate_from_history(project)
    assert count == 1

    smap = load_source_map(project)
    assert "src/main.py" in smap.source_files
    assert smap.is_migrated is True


def test_migrate_from_history_session_manifest(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _write(project.root / "src" / "engine.py", "x = 1")

    manifest_data = {
        "schema_version": "1.0",
        "files": [{"rel_path": "src/engine.py", "action": "modified"}],
    }
    _write(
        project.root / "apply_patch_backup" / "sessions" / "PATCH_1_x" / "_manifest.json",
        json.dumps(manifest_data),
    )

    count = migrate_from_history(project)
    assert count == 1

    smap = load_source_map(project)
    assert "src/engine.py" in smap.source_files


def test_migrate_from_history_dedupe(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _write(project.root / "src" / "main.py", "x = 1")

    history_data = {
        "entries": {
            "P1.json": {
                "progress_report_snapshot": {"files_created": ["src/main.py"]}
            }
        }
    }
    _write(project.root / ".apply_patch" / "patch_history.json", json.dumps(history_data))

    manifest_data = {"files": [{"rel_path": "src/main.py"}]}
    _write(
        project.root / "apply_patch_backup" / "sessions" / "P1_x" / "_manifest.json",
        json.dumps(manifest_data),
    )

    count = migrate_from_history(project)
    assert count == 1


def test_migrate_from_history_no_history(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    count = migrate_from_history(project)
    assert count == 0


def test_heuristic_folders_known_src(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _write(project.root / "src" / "main.py", "x = 1")

    folders = heuristic_folders(project)
    assert "src" in folders


def test_heuristic_folders_data_folder_not_boosted(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    for i in range(10):
        _write(project.root / "exports" / f"data_{i}.html", "<html></html>")
    _write(project.root / "exports" / "helper.py", "x = 1")

    folders = heuristic_folders(project)
    assert "exports" not in folders
