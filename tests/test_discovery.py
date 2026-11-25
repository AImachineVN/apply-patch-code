"""Test discovery.py - Project manifest loading (fix AUDIT-001)."""
from __future__ import annotations

from pathlib import Path

import pytest

from apply_patch.context import DiscoveryError
from apply_patch.discovery import (
    CONFIG_DIR_NAME,
    PROJECT_MANIFEST,
    init_project,
    load_project_from_path,
)


def test_load_project_reads_project_id_from_manifest(tmp_path: Path) -> None:
    """Manifest project_id phải được đọc đúng (bug C1)."""
    project_dir = tmp_path / "my_folder"
    project_dir.mkdir()

    init_project(
        path=project_dir,
        project_id="custom_id_not_folder_name",
        project_type="custom_type",
        default_language="json",
        markers=[],
        overwrite=True,
    )

    descriptor = load_project_from_path(project_dir)

    assert descriptor.project_id == "custom_id_not_folder_name"
    assert descriptor.project_type == "custom_type"
    assert descriptor.default_language == "json"
    assert descriptor.legacy is False
    assert descriptor.manifest_path is not None
    assert descriptor.manifest_path.exists()


def test_load_project_falls_back_to_legacy_when_no_manifest(tmp_path: Path) -> None:
    """Không có manifest → legacy=True, project_id = folder name."""
    project_dir = tmp_path / "legacy_proj"
    project_dir.mkdir()

    descriptor = load_project_from_path(project_dir)

    assert descriptor.project_id == "legacy_proj"
    assert descriptor.project_type == "python"
    assert descriptor.default_language == "python"
    assert descriptor.legacy is True
    assert descriptor.manifest_path is None


def test_load_project_handles_profiles_init_oserror(
    tmp_path: Path, monkeypatch
) -> None:
    """ensure_profiles_initialized fail không được crash (bug NameError)."""
    project_dir = tmp_path / "readonly_proj"
    project_dir.mkdir()

    init_project(
        path=project_dir,
        project_id="custom",
        project_type="custom_type",
        default_language="json",
        markers=[],
        overwrite=True,
    )

    # Mock ensure_profiles_initialized để raise OSError
    import apply_patch.discovery as disc

    def _raise_oserror(path):
        raise OSError("Permission denied (simulated)")

    monkeypatch.setattr(disc, "ensure_profiles_initialized", _raise_oserror)

    # Không crash, vẫn load manifest đúng
    descriptor = load_project_from_path(project_dir)

    assert descriptor.project_id == "custom"
    assert descriptor.project_type == "custom_type"
    assert descriptor.default_language == "json"
    assert descriptor.legacy is False


def test_load_project_rejects_non_directory(tmp_path: Path) -> None:
    """Path là file (không phải dir) → DiscoveryError."""
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("hello", encoding="utf-8")

    with pytest.raises(DiscoveryError):
        load_project_from_path(file_path)


def test_load_project_rejects_invalid_json_manifest(tmp_path: Path) -> None:
    """Manifest JSON hỏng → DiscoveryError."""
    project_dir = tmp_path / "bad_manifest"
    project_dir.mkdir()
    config_dir = project_dir / CONFIG_DIR_NAME
    config_dir.mkdir()
    (config_dir / PROJECT_MANIFEST).write_text("{invalid json", encoding="utf-8")

    with pytest.raises(DiscoveryError):
        load_project_from_path(project_dir)