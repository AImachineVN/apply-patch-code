"""Tests for source_snapshot generation (2-file Markdown + content)."""
from __future__ import annotations

from pathlib import Path

from apply_patch.context import ProjectDescriptor
from apply_patch.source_snapshot import (
    CONTENT_FILENAME_BASE,
    MAX_PROGRESS_SIZE,
    MAX_TOTAL_SIZE,
    PROGRESS_FILENAME,
    TREE_FILENAME,
    generate_snapshot,
)


def _make_project(tmp_path: Path, project_type: str = 'python') -> ProjectDescriptor:
    return ProjectDescriptor(
        root=tmp_path,
        project_id='test_project',
        project_type=project_type,
        markers=[],
        source_roots=['.'],
        exclude=[],
        manifest_path=None,
        legacy=True,
        default_language='python',
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_basic_python_project(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', "print('hi')\n")
    _write(tmp_path / 'utils.py', 'def f():\n    return 1\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    assert result.content_format == 'py'
    assert result.tree_path.name == TREE_FILENAME
    assert result.content_path.name == CONTENT_FILENAME_BASE + '.py'
    assert result.tree_path.exists()
    assert result.content_path.exists()
    assert result.included_files == 2
    assert result.skipped_files == 0


def test_javascript_project(tmp_path: Path) -> None:
    _write(tmp_path / 'app.js', "console.log('hi');\n")
    project = _make_project(tmp_path, 'javascript')

    result = generate_snapshot(project)

    assert result.success
    assert result.content_format == 'js'
    assert result.content_path.suffix == '.js'


def test_dominant_fallback_manifest_missing(tmp_path: Path) -> None:
    _write(tmp_path / 'a.py', 'x = 1\n')
    _write(tmp_path / 'b.py', 'y = 2\n')
    _write(tmp_path / 'c.md', '# doc\n')
    project = _make_project(tmp_path, '')

    result = generate_snapshot(project)

    assert result.success
    assert result.content_format == 'py'


def test_comment_out_non_dominant(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    _write(tmp_path / 'config.toml', 'name = "test"\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    assert '# name = "test"' in content


def test_truncate_per_file(tmp_path: Path) -> None:
    big_content = 'x = 1\n' * 20000
    _write(tmp_path / 'big.py', big_content)
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    assert any('Truncated' in w for w in result.warnings)


def test_total_size_limit(tmp_path: Path) -> None:
    for i in range(10):
        _write(tmp_path / ('file_' + str(i) + '.py'), '# comment\n' * 5000)
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    assert result.skipped_files > 0
    assert result.included_bytes <= MAX_TOTAL_SIZE


def test_priority_ordering(tmp_path: Path) -> None:
    _write(tmp_path / 'doc.md', '# Header\n' * 1000)
    _write(tmp_path / 'code.py', 'x = 1\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    py_pos = content.find('code.py')
    md_pos = content.find('doc.md')
    assert py_pos != -1 and md_pos != -1 and py_pos < md_pos


def test_binary_skipped(tmp_path: Path) -> None:
    (tmp_path / 'binary.py').write_bytes(b'\x00\x01\x02\x03binary')
    _write(tmp_path / 'main.py', 'x = 1\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    assert 'binary.py' not in content


def test_encoding_skip(tmp_path: Path) -> None:
    (tmp_path / 'latin.py').write_bytes('cafe'.encode('latin-1') + b'\xe9\n')
    _write(tmp_path / 'main.py', 'x = 1\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success


def test_empty_project(tmp_path: Path) -> None:
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    assert result.tree_path.exists()
    assert result.content_path.exists()
    assert result.total_files == 0


def test_ascii_tree(tmp_path: Path) -> None:
    _write(tmp_path / 'src' / 'a.py', 'x = 1\n')
    _write(tmp_path / 'src' / 'b.py', 'y = 2\n')
    _write(tmp_path / 'tests' / 'c.py', 'z = 3\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    tree = result.tree_path.read_text(encoding='utf-8')
    assert 'src/' in tree
    assert 'tests/' in tree


def test_file_with_hash_chars(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    _write(tmp_path / 'notes.md', '# Header\n\n## Sub\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    assert 'notes.md' in content


def test_metadata_in_tree(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    tree = result.tree_path.read_text(encoding='utf-8')
    assert 'Project ID' in tree
    assert 'Dominant Language' in tree
    assert 'Content File' in tree
    assert 'source_content.py' in tree


def test_exclude_doccuments_dir(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    _write(tmp_path / 'Doccuments' / 'nuitka-crash-report.xml', '<crash/>\n')
    _write(tmp_path / 'Doccuments' / 'Log.txt', 'some log\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    assert 'nuitka-crash-report.xml' not in content
    assert 'Log.txt' not in content


def test_exclude_log_glob(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    _write(tmp_path / 'app.log', 'log line\n')
    _write(tmp_path / 'debug.log', 'another log\n')
    _write(tmp_path / 'backup.tmp', 'temp data\n')
    _write(tmp_path / 'old.bak', 'backup data\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    assert 'app.log' not in content
    assert 'debug.log' not in content
    assert 'backup.tmp' not in content
    assert 'old.bak' not in content


def test_exclude_nuitka_crash_report_at_root(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    _write(tmp_path / 'nuitka-crash-report.xml', '<crash/>\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    assert 'nuitka-crash-report.xml' not in content
    assert 'main.py' in content


def test_exclude_profiles_dir(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    _write(tmp_path / 'profiles' / 'source_content.py', '# huge tool output\n' * 5000)
    _write(tmp_path / 'profiles' / 'source_tree.md', '# tree output\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    assert 'profiles/source_content.py' not in content
    assert 'profiles/source_tree.md' not in content
    assert 'main.py' in content


def test_exclude_patches_dir(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    _write(tmp_path / 'Patches' / 'Patch_1_TEST.json', '{"patch_id":"x"}\n')
    _write(tmp_path / 'patches' / 'Patch_2_TEST.json', '{"patch_id":"y"}\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    content = result.content_path.read_text(encoding='utf-8')
    assert 'Patch_1_TEST.json' not in content
    assert 'Patch_2_TEST.json' not in content
    assert 'main.py' in content


def test_progress_md_generated(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    _write(tmp_path / 'profiles' / '00_PROJECT_OVERVIEW.md', '# My Project\n\nDescription here.\n')
    _write(tmp_path / 'profiles' / '09_AI_HANDOFF.md', '# Handoff\n\n## Status\n\nDONE: task 1\nTODO: task 2\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    assert result.progress_path is not None
    assert result.progress_path.name == PROGRESS_FILENAME
    assert result.progress_path.exists()
    progress = result.progress_path.read_text(encoding='utf-8')
    assert '00_PROJECT_OVERVIEW.md' in progress
    assert '# My Project' in progress
    assert '09_AI_HANDOFF.md' in progress
    assert 'TODO: task 2' in progress
    assert result.progress_files_included == 2
    assert result.progress_files_missing == 8


def test_progress_md_all_missing(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    assert result.progress_path is not None
    progress = result.progress_path.read_text(encoding='utf-8')
    assert 'profiles/ folder not found' in progress or '00_PROJECT_OVERVIEW.md' in progress
    assert result.progress_files_included == 0


def test_progress_md_truncated(tmp_path: Path) -> None:
    _write(tmp_path / 'main.py', 'x = 1\n')
    big = '# Big\n' + ('line of content here\n' * 20000)
    _write(tmp_path / 'profiles' / '00_PROJECT_OVERVIEW.md', big)
    _write(tmp_path / 'profiles' / '09_AI_HANDOFF.md', '# Handoff\n')
    project = _make_project(tmp_path, 'python')

    result = generate_snapshot(project)

    assert result.success
    assert result.progress_path is not None
    progress = result.progress_path.read_text(encoding='utf-8')
    assert len(progress.encode('utf-8')) <= MAX_PROGRESS_SIZE + 1000
    assert ('TRUNCATED' in progress) or ('SKIPPED' in progress)
    assert any('Truncated progress' in w or 'Skipped progress' in w for w in result.warnings)
