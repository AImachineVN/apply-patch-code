from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .context import DiscoveryError, ProjectDescriptor
from .profiles import ensure_profiles_initialized
from .schema import normalize_keys

log = logging.getLogger(__name__)

CONFIG_DIR_NAME = ".apply_patch"
PROJECT_MANIFEST = "project.json"
WORKSPACE_MANIFEST = "workspace.json"
LAST_PROJECT_FILE = "last_project.json"
ENV_PROJECT = "APPLY_PATCH_PROJECT"

LEGACY_MARKERS = [
    "main_qt.py",
    "ui_app_qt.py",
    "automation_engine.py",
    "license_manager.py",
]

FALLBACK_MARKER = ".gdt_project"

DEFAULT_EXCLUDE = [
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".apply_patch",
]


def _as_str_list(value: Any, default: list[str] | None = None) -> list[str]:
    """Ép giá trị thành list[str], có strip."""
    if value is None:
        return list(default or [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise DiscoveryError("Value must be a string or a list of strings.")
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _clean_str(value: Any, default: str = "") -> str:
    """Ép giá trị thành chuỗi có strip."""
    if value is None:
        return default
    return str(value).strip()


def _search_upwards_for_config(start: Path, filename: str) -> Path | None:
    """Tìm file cấu hình .apply_patch/<filename> từ thư mục hiện tại lên thư mục cha."""
    start = start.resolve()
    for directory in [start, *start.parents]:
        candidate = directory / CONFIG_DIR_NAME / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def load_project_from_path(path: Path) -> ProjectDescriptor:
    """Load project configuration từ một thư mục."""
    path = Path(path).resolve()
    if not path.is_dir():
        raise DiscoveryError(f"Path is not a directory: {path}")

    # Auto-khởi tạo profiles/ nếu thiếu (tiện ích phụ, không raise nếu fail)
    try:
        ensure_profiles_initialized(path)
    except OSError as exc:
        log.warning(f"Cannot initialize profiles directory: {exc}")

    # Đọc project manifest nếu có
    manifest_path = path / CONFIG_DIR_NAME / PROJECT_MANIFEST
    if manifest_path.is_file():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscoveryError(
                f"Cannot read project manifest {manifest_path}: {exc}"
            ) from exc

        data = normalize_keys(raw)
        if not isinstance(data, dict):
            raise DiscoveryError(
                f"Project manifest {manifest_path} must be a JSON object."
            )

        project_id = _clean_str(data.get("project_id"), default=path.name)
        project_type = _clean_str(data.get("project_type"), default="python")
        default_language = _clean_str(data.get("default_language"), default="python")
        markers = _as_str_list(data.get("markers", []))
        source_roots = _as_str_list(data.get("source_roots", []), default=["."])
        exclude = _as_str_list(data.get("exclude", []), default=DEFAULT_EXCLUDE)

        if not project_id:
            project_id = path.name

        return ProjectDescriptor(
            root=path,
            project_id=project_id,
            project_type=project_type or "python",
            markers=markers,
            source_roots=source_roots or ["."],
            exclude=exclude,
            manifest_path=manifest_path,
            legacy=False,
            default_language=default_language or "python",
        )

    # Fallback: legacy detection
    markers = [marker for marker in LEGACY_MARKERS if (path / marker).exists()]
    return ProjectDescriptor(
        root=path,
        project_id=path.name,
        project_type="python",
        markers=markers,
        source_roots=["."],
        exclude=list(DEFAULT_EXCLUDE),
        manifest_path=None,
        legacy=True,
        default_language="python",
    )


def _load_workspace(manifest_path: Path) -> list[tuple[str, Path]]:
    """Nạp workspace manifest, trả về danh sách (project_id, path)."""
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DiscoveryError(
            f"Cannot read workspace manifest {manifest_path}: {exc}"
        ) from exc

    data = normalize_keys(raw)
    if not isinstance(data, dict):
        raise DiscoveryError(
            f"Workspace manifest {manifest_path} must be a JSON object."
        )

    projects_raw = data.get("projects", [])
    if not isinstance(projects_raw, list):
        raise DiscoveryError("Workspace manifest must have a 'projects' list.")

    base_dir = manifest_path.parent.parent
    projects: list[tuple[str, Path]] = []
    for index, item in enumerate(projects_raw):
        if not isinstance(item, dict):
            raise DiscoveryError(f"projects[{index}] in workspace must be an object.")
        project_id = _clean_str(item.get("project_id"))
        path_str = _clean_str(item.get("path"))
        if not path_str:
            raise DiscoveryError(f"projects[{index}] is missing 'path' field.")
        project_path = Path(path_str)
        if not project_path.is_absolute():
            project_path = base_dir / project_path
        project_path = project_path.resolve()
        if not project_id:
            project_id = project_path.name
        projects.append((project_id, project_path))
    return projects


def discover_project(
    explicit: str | None = None,
    project_id: str | None = None,
    interactive: bool = False,
) -> ProjectDescriptor:
    """
    Nhận diện dự án theo thứ tự ưu tiên:
    1. --project
    2. Biến môi trường APPLY_PATCH_PROJECT
    3. .apply_patch/project.json từ cwd trở lên
    4. .apply_patch/workspace.json từ cwd trở lên
    5. Legacy markers hoặc .gdt_project từ cwd trở lên
    """
    if explicit:
        return load_project_from_path(Path(explicit))

    env_value = os.getenv(ENV_PROJECT)
    if env_value:
        return load_project_from_path(Path(env_value))

    cwd = Path.cwd()

    project_manifest = _search_upwards_for_config(cwd, PROJECT_MANIFEST)
    if project_manifest:
        return load_project_from_path(project_manifest.parent.parent)

    workspace_manifest = _search_upwards_for_config(cwd, WORKSPACE_MANIFEST)
    if workspace_manifest:
        projects = _load_workspace(workspace_manifest)
        if project_id:
            for pid, path in projects:
                if pid == project_id:
                    return load_project_from_path(path)
            available = ", ".join(pid for pid, _ in projects)
            raise DiscoveryError(
                f"project_id '{project_id}' not found in workspace. "
                f"Available projects: {available}"
            )
        if len(projects) == 1:
            return load_project_from_path(projects[0][1])
        available = ", ".join(pid for pid, _ in projects)
        raise DiscoveryError(
            "Workspace has multiple projects. Please use --project or --project-id. "
            f"Available projects: {available}"
        )

    for directory in [cwd, *cwd.parents]:
        if (directory / FALLBACK_MARKER).exists():
            return load_project_from_path(directory)
        matches = sum(1 for marker in LEGACY_MARKERS if (directory / marker).exists())
        if matches >= 2:
            return load_project_from_path(directory)

    raise DiscoveryError(
        "Cannot auto-detect project directory.\n"
        "Suggestions:\n"
        "  - Use --project <path_to_project_directory>\n"
        "  - Set APPLY_PATCH_PROJECT environment variable\n"
        "  - Create .apply_patch/project.json in the project directory\n"
        "  - Run: apply_patch init-project"
    )


def init_project(
    path: Path,
    project_id: str | None = None,
    project_type: str = "python",
    default_language: str = "python",  # [MỚI]
    markers: list[str] | None = None,
    overwrite: bool = False,
) -> Path:
    """Tạo file .apply_patch/project.json cho một thư mục dự án."""
    path = path.resolve()
    if not path.exists():
        raise DiscoveryError(f"Directory does not exist: {path}")
    if not path.is_dir():
        raise DiscoveryError(f"Path is not a directory: {path}")

    config_dir = path / CONFIG_DIR_NAME
    manifest_path = config_dir / PROJECT_MANIFEST

    if manifest_path.exists() and not overwrite:
        raise DiscoveryError(
            f"Project manifest already exists: {manifest_path}. "
            "Use --force to overwrite."
        )

    if not project_id:
        project_id = path.name

    data = {
        "schema_version": "1.0",
        "project_id": project_id.strip(),
        "project_type": project_type.strip() or "python",
        "default_language": default_language.strip() or "python",  # [MỚI]
        "markers": [marker.strip() for marker in (markers or []) if marker.strip()],
        "source_roots": ["."],
        "exclude": list(DEFAULT_EXCLUDE),
    }

    config_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def forget_last_project() -> bool:
    """
    Xóa file ghi nhớ project nếu tồn tại.
    Hiện tại discovery v2 không phụ thuộc file này, nhưng giữ lệnh để tương thích CLI cũ.
    """
    candidate = Path.cwd() / CONFIG_DIR_NAME / LAST_PROJECT_FILE
    if candidate.exists():
        candidate.unlink()
        return True
    return False