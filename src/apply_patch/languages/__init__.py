from __future__ import annotations

from pathlib import Path

from .base import LanguageHandler
from .external import (
    ExternalToolHandler,
    GoHandler,
    JavaScriptHandler,
    PhpHandler,
    RubyHandler,
    ShellHandler,
)
from .json_lang import JsonHandler
from .plain import PlainHandler
from .python_lang import PythonHandler
from .xml_lang import XmlHandler

__all__ = [
    "ExternalToolHandler",
    "GoHandler",
    "JavaScriptHandler",
    "JsonHandler",
    "LanguageHandler",
    "PhpHandler",
    "PlainHandler",
    "PythonHandler",
    "XmlHandler",
    "get_handler_by_name",
    "get_handler_for_path",
    "list_languages",
    "register",
    "require_handler_by_name",
    "resolve_language",
]

# Extension (lowercase, kèm dấu chấm) -> handler
_REGISTRY: dict[str, LanguageHandler] = {}
# Tên ngôn ngữ (lowercase) -> handler
_BY_NAME: dict[str, LanguageHandler] = {}

# Document-type extensions: ALWAYS plain, never overridden by project_default.
# These are definitively document formats, never source code.
_DOCUMENT_EXTENSIONS = frozenset({".md", ".markdown", ".rst", ".adoc"})


def register(handler: LanguageHandler) -> None:
    """
    Đăng ký một handler vào registry.
    Raise ValueError nếu trùng tên ngôn ngữ hoặc trùng extension,
    nhằm bắt lỗi cấu hình ngay lúc import.
    """
    key_name = handler.name.strip().lower()
    if not key_name:
        raise ValueError("Language handler must have a non-empty name.")
    if key_name in _BY_NAME:
        raise ValueError(f"Language handler already registered: {key_name}")

    _BY_NAME[key_name] = handler

    for ext in handler.extensions:
        key_ext = ext.lower()
        if not key_ext.startswith("."):
            raise ValueError(f"Extension must start with a dot: {ext}")
        if key_ext in _REGISTRY:
            raise ValueError(
                f"Extension '{key_ext}' already registered "
                f"by handler '{_REGISTRY[key_ext].name}'."
            )
        _REGISTRY[key_ext] = handler


def get_handler_by_name(name: str) -> LanguageHandler:
    """
    Lấy handler theo tên ngôn ngữ.
    Không tìm thấy thì trả về plain (fallback mềm dẻo).
    Dùng cho các trường hợp không quan trọng, backward compatibility.
    """
    return _BY_NAME.get(name.strip().lower(), _BY_NAME["plain"])


def require_handler_by_name(name: str) -> LanguageHandler:
    """
    Lấy handler theo tên ngôn ngữ.
    Raise ValueError nếu tên không hợp lệ (bắt lỗi cấu hình sớm).
    Dùng cho explicit_language và project_default.
    """
    handler = _BY_NAME.get(name.strip().lower())
    if handler is None:
        available = sorted(_BY_NAME.keys())
        raise ValueError(
            f"Unknown language '{name}'. Available languages: {available}"
        )
    return handler


def get_handler_for_path(path: Path) -> LanguageHandler:
    """Lấy handler theo đuôi file. Không khớp thì trả về plain."""
    return _REGISTRY.get(Path(path).suffix.lower(), _BY_NAME["plain"])


def resolve_language(
    path: Path,
    explicit_language: str | None = None,
    project_default: str | None = None,
) -> LanguageHandler:
    """
    Phân giải ngôn ngữ theo thứ tự ưu tiên đã phê duyệt:
    1. Trường 'language' khai báo tường minh trong FilePatch (bắt lỗi nếu không hợp lệ).
    2. Document extensions (.md, .rst, .adoc) luôn là plain.
    3. Ánh xạ theo đuôi file.
    4. Trường 'default_language' của project (bắt lỗi nếu không hợp lệ).
    5. PlainHandler (fallback cuối cùng).
    """
    # 1. Explicit language - bắt lỗi nếu không hợp lệ
    if explicit_language:
        return require_handler_by_name(explicit_language)

    ext = Path(path).suffix.lower()

    # 2. Document extensions are ALWAYS plain, never overridden by project_default.
    if ext in _DOCUMENT_EXTENSIONS:
        return _BY_NAME["plain"]

    # 3. Extension mapping
    handler = get_handler_for_path(path)
    if handler.name != "plain":
        return handler

    # 4. Project default - bắt lỗi nếu không hợp lệ
    if project_default:
        return require_handler_by_name(project_default)

    # 5. Fallback to plain
    return _BY_NAME["plain"]


def list_languages() -> list[dict[str, object]]:
    """
    Liệt kê toàn bộ ngôn ngữ đã đăng ký.
    Dùng cho subcommand CLI 'languages' ở Bước 3.
    """
    rows: list[dict[str, object]] = []
    for handler in _BY_NAME.values():
        rows.append(
            {
                "name": handler.name,
                "extensions": sorted(handler.extensions),
                "validates_syntax": handler.validates_syntax,
                "validation_kind": handler.validation_kind,
            }
        )
    rows.append(
        {
            "name": "plain (fallback)",
            "extensions": ["(everything else)"],
            "validates_syntax": False,
            "validation_kind": "none",
        }
    )
    return rows


# Đăng ký các handler built-in ngay lúc import.
# Thứ tự không quan trọng vì registry chặn trùng extension.
register(PlainHandler())
register(PythonHandler())
register(JsonHandler())
register(XmlHandler())
register(JavaScriptHandler())
register(PhpHandler())
register(GoHandler())
register(RubyHandler())
register(ShellHandler())