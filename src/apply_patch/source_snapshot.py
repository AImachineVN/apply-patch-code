"""Generate source snapshots for AI handoff.

Creates 2 files in profiles/:
  - source_tree.md         : ASCII tree + metadata (small, ~10 KB)
  - source_content.<ext>   : Full content of all source files, where <ext>
                              follows project's dominant language.

Non-dominant content is commented out using the dominant language's comment
marker (e.g., .py project → JSON content is prefixed with '#').
"""
from __future__ import annotations

import fnmatch
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .context import ProjectDescriptor
from .languages import get_handler_for_path

log = logging.getLogger(__name__)

TREE_FILENAME = 'source_tree.md'
CONTENT_FILENAME_BASE = 'source_content'

MAX_TOTAL_SIZE = 400 * 1024
MAX_PER_FILE_SIZE = 100 * 1024
WARN_FILE_COUNT = 200

DEFAULT_INCLUDE_EXTS: frozenset[str] = frozenset({
    '.py', '.pyw', '.pyi',
    '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx',
    '.json', '.jsonc', '.xml', '.yaml', '.yml', '.toml',
    '.ini', '.cfg', '.conf',
    '.md', '.rst', '.txt', '.adoc',
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    '.sql', '.sh', '.bash', '.zsh', '.bat', '.cmd', '.ps1',
    '.java', '.kt', '.scala', '.go', '.rs',
    '.c', '.h', '.cpp', '.hpp', '.cc', '.hh',
    '.cs', '.php', '.rb', '.swift', '.m', '.mm',
    '.vue', '.svelte',
})

DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset({
    '.git', '.hg', '.svn',
    '.venv', 'venv', 'env', '.env', '.tox',
    '__pycache__', '.mypy_cache', '.pytest_cache', '.ruff_cache',
    'node_modules', 'bower_components',
    'build', 'dist', 'release',
    '.apply_patch', 'apply_patch_backup',
    '.idea', '.vscode', '.vs',
    'target', 'bin', 'obj',
    '.next', '.nuxt', 'out',
    '.cache',
    # Garbage folders that waste snapshot budget
    'Doccuments', 'doccuments',
    'Documents', 'documents',
    'Logs', 'logs',
    'CrashReports', 'crashreports', 'crash_reports',
    'profiles',      # Output của chính tool
    'Patches',       # Patch recipes (không cần AI đọc trong snapshot)
    'patches',
})

DEFAULT_EXCLUDE_FILES: frozenset[str] = frozenset({
    '.DS_Store', 'Thumbs.db', 'desktop.ini',
    'package-lock.json', 'yarn.lock', 'poetry.lock', 'Pipfile.lock',
})

# Glob patterns for filename exclusion (via fnmatch). These match file NAME only,
# not path. Useful for garbage files that can appear anywhere in the tree.
DEFAULT_EXCLUDE_GLOBS: tuple[str, ...] = (
    '*.log',
    '*.tmp',
    '*.bak',
    '*.swp',
    '*.swo',
    'nuitka-crash-report.xml',
    'source_content.*',      # Output content của tool
    'source_tree.md',        # Output tree của tool
    'source_snapshot.json',  # Output cũ (legacy)
)

PROGRESS_FILENAME = 'source_progress.md'
PROGRESS_FILE_ORDER: tuple[str, ...] = (
    '00_PROJECT_OVERVIEW.md',
    '01_SYSTEM_ARCHITECTURE.md',
    '02_BUSINESS_LOGIC.md',
    '03_MODULE_REGISTRY.md',
    '04_DATABASE_DESIGN.md',
    '05_API_DOCUMENTATION.md',
    '06_TECHNICAL_DECISIONS.md',
    '07_TASK_TRACKER.md',
    '08_CHANGELOG.md',
    '09_AI_HANDOFF.md',
)
MAX_PROGRESS_SIZE = 200 * 1024

PRIORITY_EXTENSIONS: list[frozenset[str]] = [
    frozenset({'.py', '.pyw', '.pyi', '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx',
               '.java', '.kt', '.scala', '.go', '.rs',
               '.c', '.h', '.cpp', '.hpp', '.cc', '.hh',
               '.cs', '.php', '.rb', '.swift', '.m', '.mm'}),
    frozenset({'.json', '.jsonc', '.yaml', '.yml', '.toml', '.xml', '.ini', '.cfg', '.conf'}),
    frozenset({'.sql', '.sh', '.bash', '.zsh', '.bat', '.cmd', '.ps1'}),
    frozenset({'.html', '.htm', '.css', '.scss', '.sass', '.less', '.vue', '.svelte'}),
    frozenset({'.md', '.rst', '.txt', '.adoc'}),
]

PROJECT_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    'python':     ('py',    '#',  ''),
    'javascript': ('js',    '//', ''),
    'typescript': ('ts',    '//', ''),
    'java':       ('java',  '//', ''),
    'kotlin':     ('kt',    '//', ''),
    'go':         ('go',    '//', ''),
    'rust':       ('rs',    '//', ''),
    'c':          ('c',     '//', ''),
    'cpp':        ('cpp',   '//', ''),
    'csharp':     ('cs',    '//', ''),
    'php':        ('php',   '//', ''),
    'ruby':       ('rb',    '#',  ''),
    'swift':      ('swift', '//', ''),
    'shell':      ('sh',    '#',  ''),
    'json':       ('json',  '//', ''),
    'xml':        ('xml',   '<!--', '-->'),
    'plain':      ('txt',   '#',  ''),
}


@dataclass
class SnapshotResult:
    tree_path: Path
    content_path: Path
    content_format: str = ''
    total_files: int = 0
    included_files: int = 0
    skipped_files: int = 0
    total_bytes: int = 0
    included_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    skipped_details: list[dict[str, Any]] = field(default_factory=list)
    progress_path: Path | None = None
    progress_bytes: int = 0
    progress_files_included: int = 0
    progress_files_missing: int = 0
    success: bool = True
    error: str = ''


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_binary(data: bytes, sample_size: int = 8192) -> bool:
    return b'\x00' in data[:sample_size]


def _decode_text(data: bytes) -> tuple[str, str] | None:
    for enc in ('utf-8', 'utf-8-sig'):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return None


def _should_skip_dir(rel_parts: tuple[str, ...], exclude_dirs: frozenset[str]) -> bool:
    return any(part in exclude_dirs for part in rel_parts)


def _detect_language_name(rel_path: str) -> str:
    try:
        return get_handler_for_path(Path(rel_path)).name
    except Exception:  # noqa: BLE001
        return 'plain'


def _priority_index(suffix: str) -> int:
    suffix = suffix.lower()
    for idx, group in enumerate(PRIORITY_EXTENSIONS):
        if suffix in group:
            return idx
    return len(PRIORITY_EXTENSIONS)


def _detect_dominant(project: ProjectDescriptor, files: list[dict[str, Any]]) -> tuple[str, str, str, str]:
    ptype = (project.project_type or '').strip().lower()
    if ptype and ptype in PROJECT_TYPE_MAP:
        ext, cp, cs = PROJECT_TYPE_MAP[ptype]
        return ptype, ext, cp, cs

    counts: dict[str, int] = {}
    for f in files:
        ext = Path(f['path']).suffix.lower()
        if ext:
            counts[ext] = counts.get(ext, 0) + 1
    if counts:
        top_ext = max(counts, key=lambda k: counts[k]).lstrip('.')
        for name, (ext, cp, cs) in PROJECT_TYPE_MAP.items():
            if ext == top_ext:
                return name, ext, cp, cs
        return 'plain', 'txt', '#', ''

    return 'plain', 'txt', '#', ''


def _build_ascii_tree(rel_paths: list[str], root_name: str = '.') -> str:
    if not rel_paths:
        return root_name + '/\n    (no files)'

    tree: dict[str, Any] = {}
    for rel in rel_paths:
        parts = Path(rel).parts
        node = tree
        for part in parts:
            node = node.setdefault(part, {})

    lines: list[str] = [root_name + '/']

    def walk(node: dict[str, Any], prefix: str) -> None:
        items = sorted(node.items(), key=lambda kv: (not kv[1], kv[0]))
        for i, (name, child) in enumerate(items):
            is_last = i == len(items) - 1
            branch = '└── ' if is_last else '├── '
            lines.append(prefix + branch + name + ('/' if child else ''))
            if child:
                walk(child, prefix + ('    ' if is_last else '│   '))

    walk(tree, '')
    return '\n'.join(lines)


def _comment_out(content: str, prefix: str, suffix: str) -> str:
    if suffix:
        return prefix + '\n' + content + '\n' + suffix
    out_lines: list[str] = []
    for line in content.splitlines():
        if line.strip():
            out_lines.append(prefix + ' ' + line)
        else:
            out_lines.append(prefix)
    if content.endswith('\n'):
        return '\n'.join(out_lines) + '\n'
    return '\n'.join(out_lines)


def _truncate(content: str, limit: int) -> tuple[str, bool, int]:
    encoded = content.encode('utf-8')
    original = len(encoded)
    if original <= limit:
        return content, False, original
    truncated_bytes = encoded[:limit]
    try:
        truncated = truncated_bytes.decode('utf-8')
    except UnicodeDecodeError:
        for cut in range(1, 5):
            try:
                truncated = truncated_bytes[:-cut].decode('utf-8')
                break
            except UnicodeDecodeError:
                continue
        else:
            truncated = truncated_bytes.decode('utf-8', errors='ignore')
    return truncated, True, original


def _render_tree_md(
    project: ProjectDescriptor,
    all_files: list[dict[str, Any]],
    included_set: set[str],
    skipped_details: list[dict[str, Any]],
    warnings: list[str],
    dominant: str,
    content_filename: str,
) -> str:
    lines: list[str] = []
    lines.append('# Source Tree — ' + project.project_id)
    lines.append('')
    lines.append('> Generated by ApplyPatchCode v' + __version__ + ' · ' + datetime.now(UTC).isoformat())
    lines.append('> Xem nội dung code tại: `' + content_filename + '`')
    lines.append('')

    lines.append('## Project Info')
    lines.append('')
    lines.append('| Field | Value |')
    lines.append('|---|---|')
    lines.append('| Project ID | ' + project.project_id + ' |')
    lines.append('| Project Type | ' + (project.project_type or '(unknown)') + ' |')
    lines.append('| Dominant Language | ' + dominant + ' |')
    lines.append('| Content File | ' + content_filename + ' |')
    lines.append('| Total Files | ' + str(len(all_files)) + ' |')
    lines.append('| Included Files | ' + str(len(included_set)) + ' |')
    lines.append('| Skipped Files | ' + str(len(skipped_details)) + ' |')
    total_bytes = sum(f.get('original_size', f['size']) for f in all_files)
    lines.append('| Total Bytes | ' + str(total_bytes) + ' |')
    lines.append('')

    included_files = [f for f in all_files if f['path'] in included_set]
    rel_paths = [f['path'] for f in included_files]
    lines.append('## Cây thư mục')
    lines.append('')
    lines.append('```')
    lines.append(_build_ascii_tree(rel_paths, project.project_id))
    lines.append('```')
    lines.append('')

    lines.append('## Danh sách file')
    lines.append('')
    lines.append('| # | Path | Language | Size | SHA-256 (8) | Trạng thái |')
    lines.append('|---|---|---|---|---|---|')
    for i, f in enumerate(all_files, start=1):
        status = '✅ Included' if f['path'] in included_set else '❌ Skipped'
        lines.append('| ' + str(i) + ' | `' + f['path'] + '` | ' + f['language'] + ' | ' + str(f['size']) + ' | `' + f['sha256'][:8] + '` | ' + status + ' |')
    lines.append('')

    if skipped_details:
        lines.append('## File bị bỏ')
        lines.append('')
        lines.append('| Path | Lý do | Size |')
        lines.append('|---|---|---|')
        for s in skipped_details:
            lines.append('| `' + s['path'] + '` | ' + s['reason'] + ' | ' + str(s.get('size', '?')) + ' |')
        lines.append('')

    if warnings:
        lines.append('## Cảnh báo')
        lines.append('')
        for w in warnings:
            lines.append('- ' + w)
        lines.append('')

    return '\n'.join(lines)


def _render_content_file(
    project: ProjectDescriptor,
    all_files: list[dict[str, Any]],
    included_set: set[str],
    skipped_details: list[dict[str, Any]],
    dominant: str,
    comment_prefix: str,
    comment_suffix: str,
    content_filename: str,
) -> str:
    lines: list[str] = []
    cp = comment_prefix
    bar = cp + ' ' + '=' * 77
    sub = cp + ' ' + '-' * 77

    lines.append(bar)
    lines.append(cp + ' SOURCE CONTENT SNAPSHOT')
    lines.append(cp + ' Project: ' + project.project_id)
    lines.append(cp + ' Generated by ApplyPatchCode v' + __version__ + ' · ' + datetime.now(UTC).isoformat())
    lines.append(cp + ' Dominant language: ' + dominant + '  |  Content file: ' + content_filename)
    lines.append(cp + ' Total: ' + str(len(all_files)) + ' files  |  Included: ' + str(len(included_set)) + '  |  Skipped: ' + str(len(skipped_details)))
    lines.append(cp + " See 'source_tree.md' for file structure")
    lines.append(bar)
    lines.append('')

    for f in all_files:
        if f['path'] not in included_set:
            continue
        rel = f['path']
        lines.append('')
        lines.append(sub)
        lines.append(cp + ' FILE: ' + rel)
        lines.append(cp + ' LANGUAGE: ' + f['language'] + '  |  SIZE: ' + str(f['size']) + ' bytes  |  SHA-256: ' + f['sha256'][:16] + '...')
        if f.get('truncated'):
            lines.append(cp + ' TRUNCATED: original ' + str(f['original_size']) + ' bytes > ' + str(MAX_PER_FILE_SIZE) + ' bytes limit')
        if f['language'].lower() != dominant.lower():
            lines.append(cp + " NOTE: non-" + dominant + " content commented-out with '" + cp + "'")
        lines.append(sub)

        content = f['content']
        if f['language'].lower() == dominant.lower():
            body = content
        else:
            body = _comment_out(content, cp, comment_suffix)
        if not body.endswith('\n'):
            body += '\n'
        lines.append(body)

    if skipped_details:
        lines.append('')
        lines.append(bar)
        lines.append(cp + ' SKIPPED FILES (không đưa vào content vì vượt ngưỡng)')
        lines.append(bar)
        for s in skipped_details:
            lines.append(cp + ' - ' + s['path'] + '  (' + str(s.get('size', '?')) + ' bytes, lý do: ' + s['reason'] + ')')
        lines.append(bar)

    return '\n'.join(lines) + '\n'


def _render_progress_md(
    project: ProjectDescriptor,
    profiles_dir: Path,
    max_size: int = MAX_PROGRESS_SIZE,
) -> tuple[str, int, int, list[str]]:
    """Render source_progress.md from 10 profiles/*.md files in fixed order.

    Returns: (content, included_count, missing_count, warnings)
    """
    lines: list[str] = []
    warnings: list[str] = []
    included = 0
    missing = 0

    lines.append('# Source Progress — ' + project.project_id)
    lines.append('')
    lines.append('> Generated by ApplyPatchCode v' + __version__ + ' · ' + datetime.now(UTC).isoformat())
    lines.append('> Tổng hợp từ ' + str(len(PROGRESS_FILE_ORDER)) + ' file profiles/*.md')
    lines.append('> Mục đích: báo cáo tiến độ — đã làm gì, đang làm gì, cần làm gì tiếp.')
    lines.append('')

    if not profiles_dir.is_dir():
        lines.append('## ⚠️ profiles/ folder not found')
        lines.append('')
        lines.append('_(Không có thư mục `profiles/` trong dự án này.)_')
        return '\n'.join(lines) + '\n', 0, len(PROGRESS_FILE_ORDER), warnings

    for idx, filename in enumerate(PROGRESS_FILE_ORDER, start=1):
        file_path = profiles_dir / filename
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## ' + str(idx) + '. ' + filename)
        lines.append('')

        if not file_path.is_file():
            missing += 1
            lines.append('_(File không tồn tại: `profiles/' + filename + '`)_')
            continue

        try:
            content = file_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            missing += 1
            warnings.append('Cannot read profiles/' + filename + ': ' + str(exc))
            lines.append('_(File không đọc được: ' + type(exc).__name__ + ')_')
            continue

        current_bytes = len('\n'.join(lines).encode('utf-8'))
        content_bytes_len = len(content.encode('utf-8'))

        if current_bytes + content_bytes_len > max_size:
            remaining = max_size - current_bytes - 200
            if remaining > 100:
                truncated, _was_truncated, orig_size = _truncate(content, remaining)
                lines.append(truncated)
                lines.append('')
                lines.append('_⚠️ TRUNCATED: original ' + str(orig_size) + ' bytes, showing first ' + str(remaining) + ' bytes. Đọc trực tiếp `profiles/' + filename + '` để xem đầy đủ._')
                warnings.append('Truncated progress file profiles/' + filename + ': ' + str(orig_size) + ' bytes > ' + str(remaining) + ' available')
                included += 1
            else:
                missing += 1
                lines.append('_(SKIPPED: vượt ngân sách ' + str(max_size) + ' bytes — đọc trực tiếp `profiles/' + filename + '`)_')
                warnings.append('Skipped progress file profiles/' + filename + ' (budget exceeded)')
            continue

        lines.append(content)
        included += 1

    return '\n'.join(lines) + '\n', included, missing, warnings


def generate_snapshot(
    project: ProjectDescriptor,
    output_dir: Path | None = None,
    max_total_size: int = MAX_TOTAL_SIZE,
    max_per_file_size: int = MAX_PER_FILE_SIZE,
    include_exts: frozenset[str] | None = None,
    exclude_dirs: frozenset[str] | None = None,
) -> SnapshotResult:
    if include_exts is None:
        include_exts = DEFAULT_INCLUDE_EXTS
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS

    if output_dir is None:
        output_dir = project.root / 'profiles'
    else:
        output_dir = Path(output_dir)

    root = project.root.resolve()
    all_files: list[dict[str, Any]] = []
    warnings: list[str] = []

    try:
        for file_path in root.rglob('*'):
            if not file_path.is_file():
                continue
            try:
                rel_path = file_path.relative_to(root)
            except ValueError:
                continue
            if _should_skip_dir(rel_path.parts[:-1], exclude_dirs):
                continue
            if file_path.name in DEFAULT_EXCLUDE_FILES:
                continue
            if any(fnmatch.fnmatch(file_path.name, pat) for pat in DEFAULT_EXCLUDE_GLOBS):
                continue
            if file_path.suffix.lower() not in include_exts:
                continue
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                warnings.append('Cannot read ' + rel_path.as_posix() + ': ' + str(exc))
                continue
            if _is_binary(data):
                continue
            decoded = _decode_text(data)
            if decoded is None:
                warnings.append('Skipped (non-utf8): ' + rel_path.as_posix())
                continue
            content, encoding = decoded
            rel_str = rel_path.as_posix()
            all_files.append({
                'path': rel_str,
                'size': size,
                'sha256': _sha256_bytes(data),
                'encoding': encoding,
                'language': _detect_language_name(rel_str),
                'content': content,
            })
    except Exception as exc:  # noqa: BLE001
        return SnapshotResult(
            tree_path=output_dir / TREE_FILENAME,
            content_path=output_dir / (CONTENT_FILENAME_BASE + '.txt'),
            success=False,
            error='Scan failed: ' + type(exc).__name__ + ': ' + str(exc),
        )

    dominant_name, output_ext, comment_prefix, comment_suffix = _detect_dominant(project, all_files)
    content_filename = CONTENT_FILENAME_BASE + '.' + output_ext

    all_files.sort(key=lambda f: (_priority_index(Path(f['path']).suffix), f['path']))

    included_set: set[str] = set()
    skipped_details: list[dict[str, Any]] = []
    total_bytes_selected = 0

    for f in all_files:
        if f['size'] > max_per_file_size:
            truncated_content, was_truncated, original_size = _truncate(f['content'], max_per_file_size)
            if was_truncated:
                f['content'] = truncated_content
                f['truncated'] = True
                f['original_size'] = original_size
                f['size'] = len(truncated_content.encode('utf-8'))
                warnings.append('Truncated ' + f['path'] + ': ' + str(original_size) + ' bytes > ' + str(max_per_file_size) + ' limit')

        if total_bytes_selected + f['size'] > max_total_size:
            skipped_details.append({
                'path': f['path'],
                'reason': 'total_size_limit',
                'size': f['size'],
            })
            continue

        included_set.add(f['path'])
        total_bytes_selected += f['size']

    if len(all_files) > WARN_FILE_COUNT:
        warnings.append('High file count: ' + str(len(all_files)) + ' (soft threshold ' + str(WARN_FILE_COUNT) + ')')

    tree_md = _render_tree_md(
        project=project,
        all_files=all_files,
        included_set=included_set,
        skipped_details=skipped_details,
        warnings=warnings,
        dominant=dominant_name,
        content_filename=content_filename,
    )
    content_text = _render_content_file(
        project=project,
        all_files=all_files,
        included_set=included_set,
        skipped_details=skipped_details,
        dominant=dominant_name,
        comment_prefix=comment_prefix,
        comment_suffix=comment_suffix,
        content_filename=content_filename,
    )

    tree_path = output_dir / TREE_FILENAME
    content_path = output_dir / content_filename

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        tree_path.write_text(tree_md, encoding='utf-8')
        content_path.write_text(content_text, encoding='utf-8')
    except OSError as exc:
        return SnapshotResult(
            tree_path=tree_path,
            content_path=content_path,
            content_format=output_ext,
            total_files=len(all_files),
            included_files=len(included_set),
            skipped_files=len(skipped_details),
            success=False,
            error='Cannot write snapshot: ' + str(exc),
        )

    progress_text, progress_included, progress_missing, progress_warnings = _render_progress_md(
        project=project,
        profiles_dir=project.root / 'profiles',
        max_size=MAX_PROGRESS_SIZE,
    )
    warnings.extend(progress_warnings)

    progress_path: Path | None = output_dir / PROGRESS_FILENAME
    progress_bytes = 0
    assert progress_path is not None
    try:
        progress_path.write_text(progress_text, encoding='utf-8')
        progress_bytes = len(progress_text.encode('utf-8'))
    except OSError as exc:
        warnings.append('Cannot write ' + PROGRESS_FILENAME + ': ' + str(exc))
        progress_path = None

    log.info(
        '[SNAPSHOT] Generated ' + tree_path.name + ' + ' + content_path.name + ' + ' + PROGRESS_FILENAME + ': '
        + str(len(included_set)) + '/' + str(len(all_files)) + ' files, '
        + str(total_bytes_selected) + ' bytes code, '
        + str(progress_included) + '/' + str(len(PROGRESS_FILE_ORDER)) + ' progress files'
    )

    return SnapshotResult(
        tree_path=tree_path,
        content_path=content_path,
        content_format=output_ext,
        total_files=len(all_files),
        included_files=len(included_set),
        skipped_files=len(skipped_details),
        total_bytes=sum(f.get('original_size', f['size']) for f in all_files),
        included_bytes=total_bytes_selected,
        warnings=warnings,
        skipped_details=skipped_details,
        progress_path=progress_path,
        progress_bytes=progress_bytes,
        progress_files_included=progress_included,
        progress_files_missing=progress_missing,
        success=True,
    )
