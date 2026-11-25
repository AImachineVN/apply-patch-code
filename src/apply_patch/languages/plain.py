from __future__ import annotations

from .base import LanguageHandler


class PlainHandler(LanguageHandler):
    """
    Handler fallback cho mọi ngôn ngữ chưa được đăng ký.
    Không kiểm tra cú pháp: patch luôn được phép đi qua tầng này.
    """

    name = "plain"
    extensions = frozenset()
    validates_syntax = False
    validation_kind = "none"