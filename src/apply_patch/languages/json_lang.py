from __future__ import annotations

import json

from .base import LanguageHandler


class JsonHandler(LanguageHandler):
    """Handler JSON: kiểm tra cú pháp bằng json.loads (built-in)."""

    name = "json"
    extensions = frozenset({".json"})
    validates_syntax = True
    validation_kind = "built-in"

    def check_text(self, content: str) -> tuple[bool, str | None]:
        try:
            json.loads(content)
            return True, None
        except json.JSONDecodeError as exc:
            return False, (
                f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            )