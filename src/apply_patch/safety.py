from __future__ import annotations

from pathlib import Path

from .context import SafetyError


def validate_relative_path(relative_path: str) -> None:
    """
    Kiểm tra đường dẫn tương đối hợp lệ.
    Không cho phép đường dẫn tuyệt đối hoặc path traversal.
    """
    if not relative_path or not relative_path.strip():
        raise SafetyError("Đường dẫn file không được rỗng.")

    path = Path(relative_path)

    if path.is_absolute():
        raise SafetyError(f"Đường dẫn không được là absolute path: {relative_path}")

    if any(part == ".." for part in path.parts):
        raise SafetyError(f"Đường dẫn không được chứa '..': {relative_path}")


def safe_join(project_root: Path, relative_path: str) -> Path:
    """
    Kết nối project_root với đường dẫn tương đối, đảm bảo kết quả nằm trong project_root.
    """
    validate_relative_path(relative_path)

    root = project_root.resolve()
    candidate = (root / Path(relative_path)).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SafetyError(
            f"Đường dẫn '{relative_path}' thoát khỏi thư mục dự án: {root}"
        ) from exc

    return candidate