from __future__ import annotations

import os
import sys
from pathlib import Path


def is_compiled() -> bool:
    """Kiểm tra xem ứng dụng có đang chạy dưới dạng Nuitka .exe hay không."""
    return "__compiled__" in globals()


def get_base_dir() -> Path:
    """
    Trả về thư mục gốc chứa tài nguyên của ứng dụng.
    - Nuitka (.exe): Thư mục chứa file .exe (nơi các assets được bundle vào).
    - Dev (Python): Thư mục gốc của dự án (nơi chứa build.py, pyproject.toml).
    """
    if is_compiled():
        return Path(sys.executable).parent.resolve()
    else:
        # ĐÃ SỬA LỖI: Từ src/apply_patch/utils/path_resolver.py đi lên 4 cấp để ra root project
        # utils -> apply_patch -> src -> root_project
        return Path(__file__).parent.parent.parent.parent.resolve()


def get_resource_path(relative_path: str | Path) -> Path:
    """
    Lấy đường dẫn tuyệt đối đến một tài nguyên tĩnh (file json schema, icon, v.v.).
    Dùng cho các thao tác ĐỌC (Read-only).
    """
    return get_base_dir() / relative_path


def get_writable_dir(sub_dir: str = "") -> Path:
    """
    Trả về thư mục có quyền ghi để lưu dữ liệu động (logs, downloads, backups).
    Sử dụng %APPDATA% trên Windows để tránh lỗi Permission Denied trong Program Files.
    """
    app_data = os.environ.get("APPDATA")
    if app_data:
        base = Path(app_data)
    else:
        base = Path.home()
    
    writable_dir = base / "ApplyPatchCode"
    if sub_dir:
        writable_dir = writable_dir / sub_dir
        
    writable_dir.mkdir(parents=True, exist_ok=True)
    return writable_dir