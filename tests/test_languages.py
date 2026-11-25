from __future__ import annotations

from pathlib import Path

import pytest

from apply_patch.languages import external as external_mod
from apply_patch.languages import (
    get_handler_by_name,
    get_handler_for_path,
    list_languages,
    resolve_language,
)
from apply_patch.languages.external import JavaScriptHandler
from apply_patch.languages.json_lang import JsonHandler
from apply_patch.languages.plain import PlainHandler
from apply_patch.languages.python_lang import PythonHandler
from apply_patch.languages.xml_lang import XmlHandler

# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------

def test_registry_lookup_python():
    assert get_handler_for_path(Path("src/app.py")).name == "python"
    assert get_handler_for_path(Path("script.PYW")).name == "python"


def test_registry_lookup_json():
    assert get_handler_for_path(Path("config.json")).name == "json"


def test_registry_lookup_xml():
    assert get_handler_for_path(Path("data.xml")).name == "xml"
    assert get_handler_for_path(Path("icon.svg")).name == "xml"


def test_registry_lookup_html_falls_back_to_plain():
    # HTML cố ý loại khỏi XmlHandler để tránh dương tính giả
    assert get_handler_for_path(Path("index.html")).name == "plain"


def test_registry_lookup_unknown_falls_back_to_plain():
    assert get_handler_for_path(Path("main.rs")).name == "plain"
    assert get_handler_for_path(Path("App.java")).name == "plain"
    assert get_handler_for_path(Path("no_extension")).name == "plain"


def test_get_handler_by_name():
    assert get_handler_by_name("Python").name == "python"
    assert get_handler_by_name("javascript").name == "javascript"
    assert get_handler_by_name("unknown_lang").name == "plain"


# ---------------------------------------------------------------------------
# Resolution order
# ---------------------------------------------------------------------------

def test_resolve_order_explicit_wins():
    handler = resolve_language(Path("app.py"), explicit_language="json")
    assert handler.name == "json"


def test_resolve_order_extension():
    handler = resolve_language(Path("app.py"))
    assert handler.name == "python"


def test_resolve_order_project_default():
    handler = resolve_language(Path("notes.txt"), project_default="javascript")
    assert handler.name == "javascript"


def test_resolve_fallback_plain():
    handler = resolve_language(Path("notes.txt"))
    assert handler.name == "plain"


# ---------------------------------------------------------------------------
# Python handler
# ---------------------------------------------------------------------------

def test_python_handler_passes_valid_code():
    ok, err = PythonHandler().check_text("def f():\n    return 1\n")
    assert ok is True
    assert err is None


def test_python_handler_catches_syntax_error():
    ok, err = PythonHandler().check_text("def f(:\n")
    assert ok is False
    assert err is not None
    assert "syntax error" in err.lower()


def test_python_handler_check_file(tmp_path: Path):
    good = tmp_path / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")
    ok, _err = PythonHandler().check_file(good)
    assert ok is True

    bad = tmp_path / "bad.py"
    bad.write_text("x = = 1\n", encoding="utf-8")
    ok, _err = PythonHandler().check_file(bad)
    assert ok is False


def test_python_handler_check_file_bad_encoding(tmp_path: Path):
    p = tmp_path / "latin.py"
    p.write_bytes(b"x = '\xf3'\n")
    ok, err = PythonHandler().check_file(p, encoding="utf-8")
    assert ok is False
    assert "decode" in err.lower()


# ---------------------------------------------------------------------------
# JSON handler
# ---------------------------------------------------------------------------

def test_json_handler_passes_valid():
    ok, _err = JsonHandler().check_text('{"a": 1}')
    assert ok is True


def test_json_handler_catches_invalid():
    ok, err = JsonHandler().check_text('{"a": 1,}')
    assert ok is False
    assert "line" in err.lower()


# ---------------------------------------------------------------------------
# XML handler
# ---------------------------------------------------------------------------

def test_xml_handler_passes_valid():
    ok, _err = XmlHandler().check_text("<root><child/></root>")
    assert ok is True


def test_xml_handler_catches_invalid():
    ok, _err = XmlHandler().check_text("<root><child></root>")
    assert ok is False


# ---------------------------------------------------------------------------
# Plain handler
# ---------------------------------------------------------------------------

def test_plain_handler_always_passes():
    handler = PlainHandler()
    assert handler.check_text("anything at all")[0] is True
    assert handler.validates_syntax is False


# ---------------------------------------------------------------------------
# External handler
# ---------------------------------------------------------------------------

def test_external_skips_when_tool_missing(monkeypatch):
    monkeypatch.setattr(external_mod.shutil, "which", lambda name: None)
    handler = JavaScriptHandler()
    ok, err = handler.check_text("console.log('hi')")
    assert ok is True
    assert err is None


def test_external_skips_when_tool_crashes(monkeypatch):
    monkeypatch.setattr(external_mod.shutil, "which", lambda name: "fake-node")

    def boom(*args, **kwargs):
        raise OSError("binary not executable")

    monkeypatch.setattr(external_mod.subprocess, "run", boom)
    handler = JavaScriptHandler()
    ok, err = handler.check_text("console.log(")
    assert ok is True
    assert err is None


def test_external_reports_error_when_tool_fails(monkeypatch):
    monkeypatch.setattr(external_mod.shutil, "which", lambda name: "fake-node")

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "SyntaxError: unexpected token"

    monkeypatch.setattr(external_mod.subprocess, "run", lambda *a, **k: FakeProc())
    handler = JavaScriptHandler()
    ok, err = handler.check_text("console.log(")
    assert ok is False
    assert "SyntaxError" in err


def test_external_passes_when_tool_succeeds(monkeypatch):
    monkeypatch.setattr(external_mod.shutil, "which", lambda name: "fake-node")

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(external_mod.subprocess, "run", lambda *a, **k: FakeProc())
    handler = JavaScriptHandler()
    ok, _err = handler.check_text("console.log('ok')")
    assert ok is True


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------

def test_list_languages_contains_expected_entries():
    names = {row["name"] for row in list_languages()}
    assert {"python", "json", "xml", "javascript", "php", "go", "plain"} <= names


def test_duplicate_extension_registration_raises():
    from apply_patch.languages import register
    from apply_patch.languages.base import LanguageHandler

    class RogueHandler(LanguageHandler):
        name = "rogue"
        extensions = frozenset({".py"})  # trùng với PythonHandler

    with pytest.raises(ValueError):
        register(RogueHandler())


def test_duplicate_name_registration_raises():
    from apply_patch.languages import register
    from apply_patch.languages.base import LanguageHandler

    class CloneHandler(LanguageHandler):
        name = "python"  # trùng tên
        extensions = frozenset({".pyzzz"})

    with pytest.raises(ValueError):
        register(CloneHandler())