from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateManifest:
    """
    Đại diện cho một bản cập nhật hợp lệ đã được xác thực chữ ký số.
    Sử dụng frozen=True để đảm bảo tính bất biến (immutable) sau khi khởi tạo.
    """
    version: str
    url: str
    sha256: str