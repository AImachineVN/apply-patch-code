from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import VerifyRules


def read_text(path: Path, encoding: str = "utf-8") -> str:
    """
    Đọc file văn bản mà KHÔNG dịch đổi ký tự xuống dòng.
    newline="" giữ nguyên CRLF/LF/CR đúng như trong file gốc.
    Đồng thời phát hiện file nhị phân và từ chối đọc.
    """
    # Lớp 1: Kiểm tra null byte trong 8KB đầu (dấu hiệu chắc chắn của binary)
    try:
        with open(path, "rb") as f_bin:
            chunk = f_bin.read(8192)
            if b"\x00" in chunk:
                raise ValueError(
                    f"File appears to be binary (contains null bytes): {path}. "
                    f"Apply Patch Code only supports text-based source files."
                )
    except OSError:
        pass  # Để lỗi đọc file được xử lý ở bước tiếp theo

    # Lớp 2: Đọc text, bắt UnicodeDecodeError nếu encoding sai
    try:
        with open(path, "r", encoding=encoding, newline="") as f:
            return f.read()
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"File appears to be binary or not decodable with "
            f"encoding '{encoding}': {path}. "
            f"Set the 'encoding' field correctly or exclude this file. "
            f"Details: {exc}"
        ) from exc


def check_python_syntax_text(source: str) -> tuple[bool, str]:
    """Kiểm tra cú pháp Python của chuỗi nguồn."""
    try:
        ast.parse(source)
        return True, ""
    except SyntaxError as exc:
        error_msg = (
            f"Dòng {exc.lineno}, Cột {exc.offset}: {exc.msg}. "
            f"Nội dung: {exc.text.strip() if exc.text else '(không xác định)'}"
        )
        return False, error_msg
    except Exception as exc:  # noqa: BLE001
        return False, f"Lỗi kiểm tra cú pháp: {type(exc).__name__}: {exc}"


def check_python_syntax_file(path: Path, encoding: str = "utf-8") -> tuple[bool, str]:
    """Kiểm tra cú pháp Python của file .py."""
    if path.suffix.lower() != ".py":
        return True, ""

    source = read_text(path, encoding=encoding)
    return check_python_syntax_text(source)


def verify_file_markers(
    path: Path,
    markers: list[str],
    encoding: str = "utf-8",
) -> list[str]:
    """
    Kiểm tra các marker phải có trong file.
    Trả về danh sách marker thiếu.
    """
    if not markers:
        return []

    if not path.exists():
        return list(markers)

    content = read_text(path, encoding=encoding)
    missing = [marker for marker in markers if marker not in content]
    return missing


def verify_content(content: str, rules: VerifyRules | None) -> list[str]:
    """
    Xác minh nội dung theo rules.contains và rules.not_contains.
    Trả về danh sách lỗi.
    """
    errors: list[str] = []

    if rules is None:
        return errors

    for text in rules.contains:
        if text not in content:
            errors.append(f"Thiếu nội dung mong đợi: {text[:120]}")

    for text in rules.not_contains:
        if text in content:
            errors.append(f"Vẫn còn nội dung cần loại bỏ: {text[:120]}")

    return errors