from __future__ import annotations

import json
from pathlib import Path

from apply_patch.context import ExecutionContext, ProjectDescriptor
from apply_patch.engine import apply_patch_to_project
from apply_patch.languages import get_handler_for_path
from apply_patch.schema import load_patch


def _make_progress(task_name: str = "Test task") -> dict:
    """Sinh progress_report tối giản hợp lệ cho test."""
    return {
        "task_name": task_name,
        "objective_and_scope": "Unit test objective",
        "mandatory_info_for_next_ai": "Test context info",
    }


def _write_json(tmp_path: Path, data: dict, filename: str = "patch.json") -> Path:
    p = tmp_path / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _make_project(root: Path, default_language: str = "python") -> ProjectDescriptor:
    return ProjectDescriptor(
        root=root,
        project_id="test",
        project_type="test",
        markers=[],
        source_roots=["."],
        exclude=[],
        manifest_path=None,
        legacy=True,
        default_language=default_language,
    )


def _make_context(project, patch_path, dry_run=True):
    return ExecutionContext(
        project=project,
        dry_run=dry_run,
        json_output=False,
        patch_path=patch_path,
    )


# ---------------------------------------------------------------------------
# 1. Python file with syntax error -> BLOCKED (built-in validator)
# ---------------------------------------------------------------------------
def test_python_syntax_error_blocks_patch(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    py_file = project_dir / "app.py"
    py_file.write_text("def f(:\n", encoding="utf-8")  # syntax error

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P1",
        "description": "test",
        "progress_report": _make_progress("Python syntax error"),
        "patches": [{
            "file": "app.py",
            "operations": [{
                "type": "replace",
                "old_text": "def f(:",
                "new_text": "def f():",
            }]
        }]
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    assert report.success is False
    assert any("python syntax error" in f.message.lower() for f in report.files)


# ---------------------------------------------------------------------------
# 2. Python file with valid syntax -> patch succeeds
# ---------------------------------------------------------------------------
def test_python_valid_syntax_allows_patch(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    py_file = project_dir / "app.py"
    py_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P2",
        "description": "test",
        "progress_report": _make_progress("Python valid syntax"),
        "patches": [{
            "file": "app.py",
            "operations": [{
                "type": "replace",
                "old_text": "return 1",
                "new_text": "return 2",
            }]
        }]
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    assert report.success is True


# ---------------------------------------------------------------------------
# 3. JavaScript file without node installed -> patch proceeds (no blocking)
# ---------------------------------------------------------------------------
def test_js_file_without_node_proceeds(tmp_path: Path, monkeypatch):
    # Force shutil.which to return None (simulate node not installed)
    import apply_patch.languages.external as ext
    monkeypatch.setattr(ext.shutil, "which", lambda name: None)

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    js_file = project_dir / "app.js"
    # Intentionally broken JS - would fail if validator ran
    js_file.write_text("function broken( {\n", encoding="utf-8")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P3",
        "description": "test",
        "progress_report": _make_progress("JS without node"),
        "patches": [{
            "file": "app.js",
            "operations": [{
                "type": "replace",
                "old_text": "function broken(",
                "new_text": "function fixed(",
            }]
        }]
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    # Patch MUST succeed because external validator is advisory
    assert report.success is True


# ---------------------------------------------------------------------------
# 4. JavaScript file with node available and reporting error -> advisory only
# ---------------------------------------------------------------------------
def test_js_file_with_node_error_is_advisory(tmp_path: Path, monkeypatch):
    import apply_patch.languages.external as ext
    monkeypatch.setattr(ext.shutil, "which", lambda name: "fake-node")

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "SyntaxError: unexpected token"

    monkeypatch.setattr(ext.subprocess, "run", lambda *a, **k: FakeProc())

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    js_file = project_dir / "app.js"
    js_file.write_text("broken js", encoding="utf-8")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P4",
        "description": "test",
        "progress_report": _make_progress("JS with node error"),
        "patches": [{
            "file": "app.js",
            "operations": [{
                "type": "replace",
                "old_text": "broken",
                "new_text": "fixed",
            }]
        }]
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    # Patch MUST still succeed - external error is advisory
    assert report.success is True


# ---------------------------------------------------------------------------
# 5. JSON file with invalid JSON -> BLOCKED (built-in)
# ---------------------------------------------------------------------------
def test_json_syntax_error_blocks_patch(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    json_file = project_dir / "config.json"
    json_file.write_text('{"broken": }', encoding="utf-8")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P5",
        "description": "test",
        "progress_report": _make_progress("JSON syntax error"),
        "patches": [{
            "file": "config.json",
            "operations": [{
                "type": "replace",
                "old_text": "broken",
                "new_text": "fixed",
            }]
        }]
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    assert report.success is False
    assert any("json syntax error" in f.message.lower() for f in report.files)


# ---------------------------------------------------------------------------
# 6. skip_syntax_check=True bypasses even built-in validators
# ---------------------------------------------------------------------------
def test_skip_syntax_check_bypasses_python(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    py_file = project_dir / "app.py"
    py_file.write_text("def f(:\n", encoding="utf-8")  # broken syntax

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P6",
        "description": "test",
        "progress_report": _make_progress("Skip syntax check"),
        "patches": [{
            "file": "app.py",
            "skip_syntax_check": True,  # <-- explicitly skip
            "operations": [{
                "type": "replace",
                "old_text": "def f(:",
                "new_text": "placeholder",
            }]
        }]
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    # Must succeed because syntax check was explicitly skipped
    assert report.success is True


# ---------------------------------------------------------------------------
# 7. Explicit `language` field overrides extension-based detection
# ---------------------------------------------------------------------------
def test_explicit_language_overrides_extension(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    # File has .txt extension but contains invalid JSON
    txt_file = project_dir / "data.txt"
    txt_file.write_text('{"broken": }', encoding="utf-8")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P7",
        "description": "test",
        "progress_report": _make_progress("Explicit language"),
        "patches": [{
            "file": "data.txt",
            "language": "json",  # force JSON validation on .txt file
            "operations": [{
                "type": "replace",
                "old_text": "broken",
                "new_text": "fixed",
            }]
        }]
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    # Must fail because we forced JSON validation on broken JSON content
    assert report.success is False
    assert any("json syntax error" in f.message.lower() for f in report.files)


# ---------------------------------------------------------------------------
# 8. Project default_language applies to files with unknown extension
# ---------------------------------------------------------------------------
def test_project_default_language_applies_to_unknown_extension(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    # File with unknown extension - would normally use PlainHandler
    weird_file = project_dir / "data.xyz"
    weird_file.write_text('{"broken": }', encoding="utf-8")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P8",
        "description": "test",
        "progress_report": _make_progress("Project default language"),
        "patches": [{
            "file": "data.xyz",
            "operations": [{
                "type": "replace",
                "old_text": "broken",
                "new_text": "fixed",
            }]
        }]
    })
    # Project declares JSON as default language
    project = _make_project(project_dir, default_language="json")
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    # Must fail because project default forces JSON validation
    assert report.success is False
    assert any("json syntax error" in f.message.lower() for f in report.files)


# ---------------------------------------------------------------------------
# 9. Unknown extension without default_language -> PlainHandler -> pass
# ---------------------------------------------------------------------------
def test_unknown_extension_without_default_uses_plain(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    weird_file = project_dir / "data.xyz"
    weird_file.write_text("any content at all", encoding="utf-8")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P9",
        "description": "test",
        "progress_report": _make_progress("Unknown extension plain"),
        "patches": [{
            "file": "data.xyz",
            "operations": [{
                "type": "replace",
                "old_text": "any",
                "new_text": "some",
            }]
        }]
    })
    project = _make_project(project_dir, default_language="plain")
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    assert report.success is True


# ---------------------------------------------------------------------------
# 10. XML file with malformed XML -> BLOCKED (built-in)
# ---------------------------------------------------------------------------
def test_xml_syntax_error_blocks_patch(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    xml_file = project_dir / "data.xml"
    xml_file.write_text("<root><child></root>", encoding="utf-8")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P10",
        "description": "test",
        "progress_report": _make_progress("XML syntax error"),
        "patches": [{
            "file": "data.xml",
            "operations": [{
                "type": "replace",
                "old_text": "child",
                "new_text": "item",
            }]
        }]
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    assert report.success is False
    assert any("xml syntax error" in f.message.lower() or "xml parse error" in f.message.lower()
               for f in report.files)


def test_ruby_and_shell_handlers_registered():
    from pathlib import Path as P
    assert get_handler_for_path(P("app.rb")).name == "ruby"
    assert get_handler_for_path(P("run.sh")).name == "shell"
    assert get_handler_for_path(P("run.bash")).name == "shell"


def test_crlf_line_endings_preserved(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    cs_file = project_dir / "Program.cs"
    cs_file.write_bytes(b"class Program {\r\n    // old\r\n}\r\n")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P11",
        "description": "crlf preservation",
        "progress_report": _make_progress("CRLF preservation"),
        "patches": [{
            "file": "Program.cs",
            "operations": [
                {"type": "replace", "old_text": "// old", "new_text": "// new"}
            ],
        }],
    })
    project = _make_project(project_dir, default_language="plain")
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path, dry_run=False)
    report = apply_patch_to_project(context, manifest)

    assert report.success is True
    raw = cs_file.read_bytes()
    assert raw.count(b"\r\n") == 3, "CRLF must be preserved exactly"


def test_binary_file_rejected_with_clear_message(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    bin_file = project_dir / "blob.dat"
    bin_file.write_bytes(b"\x00\x01\x02\xff\xfe")

    patch_path = _write_json(tmp_path, {
        "schema_version": "2.0",
        "patch_id": "P12",
        "description": "binary guard",
        "progress_report": _make_progress("Binary guard"),
        "patches": [{
            "file": "blob.dat",
            "operations": [
                {"type": "replace", "old_text": "x", "new_text": "y"}
            ],
        }],
    })
    project = _make_project(project_dir)
    manifest = load_patch(patch_path)
    context = _make_context(project, patch_path)
    report = apply_patch_to_project(context, manifest)

    assert report.success is False
    assert any("binary" in f.message.lower() for f in report.files)