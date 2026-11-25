from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import LanguageHandler


class XmlHandler(LanguageHandler):
    """
    Handler XML: kiểm tra well-formed bằng xml.etree (built-in).
    CHỈ áp dụng cho các định dạng XML nghiêm ngặt.
    HTML được cố ý loại trừ vì hiếm khi well-formed, tránh dương tính giả.
    """

    name = "xml"
    extensions = frozenset({".xml", ".svg", ".xsd", ".xsl"})
    validates_syntax = True
    validation_kind = "built-in"

    def check_text(self, content: str) -> tuple[bool, str | None]:
        try:
            ET.fromstring(content)
            return True, None
        except ET.ParseError as exc:
            return False, f"XML parse error: {exc}"