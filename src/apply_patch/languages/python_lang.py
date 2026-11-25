from __future__ import annotations

import ast

from .base import LanguageHandler


class PythonHandler(LanguageHandler):
    """Handler Python: kiểm tra cú pháp bằng ast.parse (built-in, không cần tool ngoài)."""

    name = "python"
    extensions = frozenset({".py", ".pyw"})
    validates_syntax = True
    validation_kind = "built-in"

    def check_text(self, content: str) -> tuple[bool, str | None]:
        try:
            ast.parse(content)
            return True, None
        except SyntaxError as exc:
            line = exc.lineno if exc.lineno else "?"
            return False, f"Python syntax error at line {line}: {exc.msg}"
        except ValueError as exc:
            return False, f"Python source error: {exc}"