from __future__ import annotations

from pathlib import Path


class LanguageHandler:
    """
    Base class trừu tượng cho mọi language handler.
    Mỗi ngôn ngữ mới chỉ cần kế thừa class này và đăng ký vào registry.
    """

    name: str = "plain"
    extensions: frozenset[str] = frozenset()
    validates_syntax: bool = False
    # "built-in" | "external" | "none"
    validation_kind: str = "none"

    def check_text(self, content: str) -> tuple[bool, str | None]:
        """
        Kiểm tra cú pháp trên chuỗi nội dung.
        Trả về (ok, error_message_or_None).
        """
        return True, None

    def check_file(self, path: Path, encoding: str = "utf-8") -> tuple[bool, str | None]:
        """
        Kiểm tra cú pháp trên file.
        Mặc định đọc file rồi ủy quyền cho check_text.
        """
        try:
            content = path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            return False, f"Cannot decode file with encoding '{encoding}': {exc}"
        except OSError as exc:
            return False, f"Cannot read file: {exc}"
        return self.check_text(content)