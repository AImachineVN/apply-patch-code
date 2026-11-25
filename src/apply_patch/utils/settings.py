from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from .path_resolver import get_writable_dir

logger = logging.getLogger(__name__)

SETTINGS_FILENAME = "settings.json"


@dataclass
class AppSettings:
    """Cấu hình ứng dụng được lưu persistent giữa các phiên làm việc."""
    last_project_path: str = ""
    last_patches_path: str = ""
    
    def is_valid(self) -> bool:
        """Kiểm tra xem ít nhất một đường dẫn có được thiết lập không."""
        return bool(self.last_project_path or self.last_patches_path)


def _get_settings_path() -> Path:
    """Trả về đường dẫn file settings.json."""
    return get_writable_dir() / SETTINGS_FILENAME


def load_settings() -> AppSettings:
    """
    Đọc settings từ file JSON.
    Defense in Depth: Nếu file lỗi, corrupt, hoặc không tồn tại, trả về settings rỗng.
    """
    settings_path = _get_settings_path()
    
    if not settings_path.exists():
        return AppSettings()
    
    try:
        raw_text = settings_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        
        if not isinstance(data, dict):
            logger.warning("Settings file is not a dict, using defaults")
            return AppSettings()
        
        return AppSettings(
            last_project_path=str(data.get("last_project_path", "")).strip(),
            last_patches_path=str(data.get("last_patches_path", "")).strip(),
        )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning(f"Failed to load settings: {exc}. Using defaults.")
        return AppSettings()


def save_settings(settings: AppSettings) -> bool:
    """
    Lưu settings xuống file JSON.
    Dùng atomic write để tránh corrupt file khi mất điện.
    Trả về True nếu thành công, False nếu có lỗi.
    """
    settings_path = _get_settings_path()
    
    try:
        # Atomic write: ghi vào file tmp rồi rename
        tmp_path = settings_path.with_suffix(".tmp")
        data = asdict(settings)
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        # Windows: cần xóa file đích trước khi rename
        if settings_path.exists():
            settings_path.unlink()
        tmp_path.rename(settings_path)
        return True
    except (OSError, ValueError) as exc:
        logger.warning(f"Failed to save settings: {exc}")
        if 'tmp_path' in locals() and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return False