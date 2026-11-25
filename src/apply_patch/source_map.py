"""Source Map - track which files/folders are real source code.

Populated incrementally after each patch apply (from report.files) and migrated
from existing patch_history.json + sessions/*/_manifest.json on first run.

Used by source_snapshot.py to prioritize source files over data files when
chunking content for AI handoff.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .context import ProjectDescriptor

log = logging.getLogger(__name__)

SOURCE_MAP_FILENAME = "source_map.json"
CONFIG_DIR = ".apply_patch"

CODE_EXTS: frozenset[str] = frozenset({
    '.py', '.pyw', '.pyi',
    '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx',
    '.java', '.kt', '.scala', '.go', '.rs',
    '.c', '.h', '.cpp', '.hpp', '.cc', '.hh',
    '.cs', '.php', '.rb', '.swift',
})

DATA_EXTS: frozenset[str] = frozenset({
    '.html', '.htm', '.xml', '.json', '.csv', '.txt', '.log', '.yaml', '.yml',
    '.svg', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.bmp',
})

KNOWN_SOURCE_FOLDERS: frozenset[str] = frozenset({
    'src', 'lib', 'app', 'core', 'source', 'packages', 'modules',
    'backend', 'frontend', 'server', 'client', 'api',
})

MAX_SCAN_PER_FOLDER = 500


@dataclass
class SourceFolderStat:
    patch_count: int = 0
    first_seen: str = ""
    last_patched: str = ""
    file_count: int = 0


@dataclass
class SourceFileStat:
    patch_count: int = 0
    typical_size: int = 0
    last_patched: str = ""


@dataclass
class SourceMap:
    schema_version: str = "1.0"
    updated_at: str = ""
    is_migrated: bool = False
    source_folders: dict[str, SourceFolderStat] = field(default_factory=dict)
    source_files: dict[str, SourceFileStat] = field(default_factory=dict)


def _get_source_map_path(project: ProjectDescriptor) -> Path:
    return project.root / CONFIG_DIR / SOURCE_MAP_FILENAME


def load_source_map(project: ProjectDescriptor) -> SourceMap:
    """Load source_map.json. Return empty SourceMap if missing or corrupt."""
    path = _get_source_map_path(project)
    if not path.is_file():
        return SourceMap()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(f"[SOURCE-MAP] Cannot read {path}: {exc}")
        return SourceMap()
    if not isinstance(data, dict):
        return SourceMap()

    smap = SourceMap(
        schema_version=str(data.get("schema_version", "1.0")),
        updated_at=str(data.get("updated_at", "")),
        is_migrated=bool(data.get("is_migrated", False)),
    )
    raw_folders = data.get("source_folders")
    if isinstance(raw_folders, dict):
        for k, v in raw_folders.items():
            if isinstance(v, dict):
                smap.source_folders[str(k)] = SourceFolderStat(
                    patch_count=int(v.get("patch_count", 0)),
                    first_seen=str(v.get("first_seen", "")),
                    last_patched=str(v.get("last_patched", "")),
                    file_count=int(v.get("file_count", 0)),
                )
    raw_files = data.get("source_files")
    if isinstance(raw_files, dict):
        for k, v in raw_files.items():
            if isinstance(v, dict):
                smap.source_files[str(k)] = SourceFileStat(
                    patch_count=int(v.get("patch_count", 0)),
                    typical_size=int(v.get("typical_size", 0)),
                    last_patched=str(v.get("last_patched", "")),
                )
    return smap


def save_source_map(project: ProjectDescriptor, smap: SourceMap) -> bool:
    """Write source_map.json atomically. Return True on success."""
    path = _get_source_map_path(project)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": smap.schema_version,
            "updated_at": smap.updated_at,
            "is_migrated": smap.is_migrated,
            "source_folders": {k: asdict(v) for k, v in smap.source_folders.items()},
            "source_files": {k: asdict(v) for k, v in smap.source_files.items()},
        }
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return True
    except OSError as exc:
        log.warning(f"[SOURCE-MAP] Cannot save {path}: {exc}")
        return False


def _update_folder_stat(smap: SourceMap, top: str, now: str) -> None:
    if not top or top == ".":
        return
    if top not in smap.source_folders:
        smap.source_folders[top] = SourceFolderStat(first_seen=now)
    fstat = smap.source_folders[top]
    fstat.patch_count += 1
    fstat.last_patched = now
    prefix = top + "/"
    fstat.file_count = sum(1 for k in smap.source_files if k.startswith(prefix))


def update_from_apply(project: ProjectDescriptor, report: object) -> SourceMap:
    """Update source_map from a successful apply report.

    report should be a PatchReport (has .files attribute, each with .file, .status).
    Skips: failed/skipped/pending status, non-existent files (dir results).
    """
    smap = load_source_map(project)
    now = datetime.now(UTC).isoformat()

    report_files = getattr(report, "files", []) or []
    for f in report_files:
        status = str(getattr(f, "status", ""))
        if status != "ok":
            continue
        raw_file = str(getattr(f, "file", "") or "").strip()
        if not raw_file:
            continue
        rel = Path(raw_file.replace("\\", "/")).as_posix()
        target = project.root / rel
        if not target.is_file():
            continue

        try:
            file_size = target.stat().st_size
        except OSError:
            file_size = 0

        if rel in smap.source_files:
            stat = smap.source_files[rel]
        else:
            stat = SourceFileStat()
        stat.patch_count += 1
        stat.last_patched = now
        stat.typical_size = file_size
        smap.source_files[rel] = stat

        parts = Path(rel).parts
        if len(parts) > 1:
            _update_folder_stat(smap, parts[0], now)

    smap.updated_at = now
    save_source_map(project, smap)
    return smap


def migrate_from_history(project: ProjectDescriptor) -> int:
    """Seed source_map from existing patch_history.json + sessions/*/_manifest.json.

    Returns number of unique files migrated. Idempotent-ish: source files already
    in map are skipped (but counted as migrated for first run).
    """
    migrated: set[str] = set()

    try:
        from .patch_history import get_history_path
        history_path = get_history_path(project.root)
        if history_path.is_file():
            data = json.loads(history_path.read_text(encoding="utf-8"))
            entries = data.get("entries", {}) if isinstance(data, dict) else {}
            if isinstance(entries, dict):
                for entry in entries.values():
                    if not isinstance(entry, dict):
                        continue
                    pr = entry.get("progress_report_snapshot") or {}
                    if not isinstance(pr, dict):
                        continue
                    for path in pr.get("files_created", []) or []:
                        if path:
                            migrated.add(str(path).replace("\\", "/"))
                    for fa in pr.get("files_modified_or_deleted", []) or []:
                        if isinstance(fa, dict):
                            p = fa.get("path", "")
                            if p:
                                migrated.add(str(p).replace("\\", "/"))
    except Exception as exc:  # noqa: BLE001
        log.warning(f"[SOURCE-MAP] Migration from history failed: {exc}")

    try:
        from .backup import BACKUP_SESSIONS_SUBDIR
        sessions_root = project.backup_dir / BACKUP_SESSIONS_SUBDIR
        if sessions_root.is_dir():
            for manifest_path in sessions_root.rglob("_manifest.json"):
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    files_list = data.get("files", []) if isinstance(data, dict) else []
                    for fentry in files_list:
                        if isinstance(fentry, dict):
                            rel = fentry.get("rel_path")
                            if rel:
                                migrated.add(str(rel).replace("\\", "/"))
                except (OSError, json.JSONDecodeError):
                    continue
    except Exception as exc:  # noqa: BLE001
        log.warning(f"[SOURCE-MAP] Migration from sessions failed: {exc}")

    migrated.discard("")
    if not migrated:
        return 0

    smap = load_source_map(project)
    now = datetime.now(UTC).isoformat()
    for rel in sorted(migrated):
        if rel in smap.source_files:
            continue
        target = project.root / rel
        stat = SourceFileStat(patch_count=1, last_patched=now)
        if target.is_file():
            try:
                stat.typical_size = target.stat().st_size
            except OSError:
                pass
        smap.source_files[rel] = stat

        parts = Path(rel).parts
        if len(parts) > 1:
            _update_folder_stat(smap, parts[0], now)

    smap.updated_at = now
    smap.is_migrated = True
    save_source_map(project, smap)
    return len(migrated)


def heuristic_folders(project: ProjectDescriptor) -> set[str]:
    """Cold start: detect likely source folders.

    Returns folder names where:
    - Name is in KNOWN_SOURCE_FOLDERS, OR
    - code_ratio > 0.7 (code_count / (code_count + data_count)) with >= 3 files.
    """
    result: set[str] = set()
    try:
        for top in project.root.iterdir():
            if not top.is_dir() or top.name.startswith("."):
                continue
            if top.name in KNOWN_SOURCE_FOLDERS:
                result.add(top.name)
                continue

            code_count = 0
            data_count = 0
            try:
                for f in top.rglob("*"):
                    if not f.is_file():
                        continue
                    ext = f.suffix.lower()
                    if ext in CODE_EXTS:
                        code_count += 1
                    elif ext in DATA_EXTS:
                        data_count += 1
                    if code_count + data_count >= MAX_SCAN_PER_FOLDER:
                        break
            except OSError:
                continue

            total = code_count + data_count
            if total >= 3 and code_count / total > 0.7:
                result.add(top.name)
    except OSError:
        pass
    return result
