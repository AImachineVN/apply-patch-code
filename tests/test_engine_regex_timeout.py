"""Test regex timeout protection (C2 - ReDoS prevention)."""
from __future__ import annotations

import pytest

from apply_patch.context import OperationError
from apply_patch.engine import _op_replace_regex


def test_regex_normal_operation_succeeds() -> None:
    """Regression: regex bình thường vẫn hoạt động."""
    content = "hello world, hello universe"
    op = {
        "type": "replace_regex",
        "pattern": r"\bhello\b",
        "replacement": "hi",
        "flags": "",
    }
    result, detail = _op_replace_regex(content, op, "test.py")
    assert result == "hi world, hi universe"
    assert "2 match" in detail


def test_regex_with_ignorecase_flag() -> None:
    """Regression: flags 'i' vẫn hoạt động."""
    content = "HELLO hello"
    op = {
        "type": "replace_regex",
        "pattern": r"hello",
        "replacement": "hi",
        "flags": "i",
    }
    result, detail = _op_replace_regex(content, op, "test.py")
    assert result == "hi hi"
    assert "2 match" in detail


def test_regex_invalid_pattern_raises() -> None:
    """Pattern không hợp lệ → OperationError."""
    op = {
        "type": "replace_regex",
        "pattern": r"[invalid(",
        "replacement": "x",
        "flags": "",
    }
    with pytest.raises(OperationError, match="[Ii]nvalid regex"):
        _op_replace_regex("test", op, "test.py")


def test_regex_no_match_raises() -> None:
    """Pattern không match → OperationError."""
    op = {
        "type": "replace_regex",
        "pattern": r"\bxyz\b",
        "replacement": "abc",
        "flags": "",
    }
    with pytest.raises(OperationError, match="did not match"):
        _op_replace_regex("hello world", op, "test.py")


def test_regex_timeout_converts_to_operation_error(monkeypatch) -> None:
    """TimeoutError từ regex library phải được convert thành OperationError.

    Test này verify CODE PATH xử lý timeout của chúng ta — không phụ thuộc
    vào việc 'regex' library có thực sự chậm với pattern nào hay không.
    Đây là cách test đúng: test logic của mình, không test third-party.
    """
    import regex as regex_mod

    class FakePatternThatTimesOut:
        """Mock compiled pattern luôn raise TimeoutError khi gọi subn."""

        def subn(self, replacement, content, timeout=None, **kwargs):
            raise TimeoutError("simulated ReDoS timeout")

    def fake_compile(pattern, flags=0):
        return FakePatternThatTimesOut()

    # Patch regex.compile trong engine.py
    monkeypatch.setattr(regex_mod, "compile", fake_compile)

    op = {
        "type": "replace_regex",
        "pattern": r"^(a+)+$",
        "replacement": "x",
        "flags": "",
    }

    with pytest.raises(OperationError, match="timed out"):
        _op_replace_regex("a" * 40 + "!", op, "test.py")


def test_regex_timeout_message_includes_pattern(monkeypatch) -> None:
    """Message lỗi timeout phải chứa pattern để user dễ debug."""
    import regex as regex_mod

    class FakePatternThatTimesOut:
        def subn(self, replacement, content, timeout=None, **kwargs):
            raise TimeoutError("simulated ReDoS timeout")

    monkeypatch.setattr(regex_mod, "compile", lambda p, flags=0: FakePatternThatTimesOut())

    op = {
        "type": "replace_regex",
        "pattern": r"malicious_pattern_here",
        "replacement": "x",
        "flags": "",
    }

    with pytest.raises(OperationError) as exc_info:
        _op_replace_regex("content", op, "test.py")

    error_msg = str(exc_info.value)
    assert "timed out" in error_msg
    assert "malicious_pattern_here" in error_msg
    assert "test.py" in error_msg