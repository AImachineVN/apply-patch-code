from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .crypto_utils import verify_signature
from .installer import prepare_and_execute_helper
from .models import UpdateManifest
from .network import download_file

logger = logging.getLogger(__name__)


def parse_version(version_str: str) -> tuple[int, ...]:
    """
    Chuyển đổi chuỗi version thành tuple số nguyên để so sánh chính xác.
    Ví dụ: "1.10.2" -> (1, 10, 2).
    Giúp tránh lỗi so sánh chuỗi alphabet (nơi "1.10" < "1.2").
    """
    parts = []
    for p in version_str.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


class UpdateManager:
    """
    Bộ não của phân hệ Auto-Updater.
    Framework Agnostic: Không tự vẽ UI, chỉ trả về Data Object và Callback.
    """
    
    def __init__(
        self,
        current_version: str,
        public_key: bytes,
        manifest_url: str,
        download_dir: Path,
    ):
        self.current_version = current_version
        self.public_key = public_key
        self.manifest_url = manifest_url
        self.download_dir = download_dir
        self.current_version_tuple = parse_version(current_version)
    
    def check_for_updates(self) -> UpdateManifest | None:
        """
        Kiểm tra phiên bản mới từ Server.
        Defense in Depth: Bắt mọi lỗi JSON, Network, Crypto và trả về None.
        """
        try:
            req = urllib.request.Request(self.manifest_url)
            req.add_header("User-Agent", "ApplyPatch-Updater/1.0")
            
            with urllib.request.urlopen(req, timeout=10) as response:
                raw_data = response.read()
                data = json.loads(raw_data.decode("utf-8"))
                
                signature_hex = data.get("signature")
                if not signature_hex:
                    logger.warning("Manifest missing signature field.")
                    return None
                
                signature_bytes = bytes.fromhex(signature_hex)
                payload_data = {k: v for k, v in data.items() if k != "signature"}
                payload_str = json.dumps(payload_data, sort_keys=True, separators=(",", ":"))
                
                if not verify_signature(self.public_key, signature_bytes, payload_str.encode("utf-8")):
                    logger.error("Manifest signature verification failed. Possible tampering.")
                    return None
                
                server_version = data.get("version")
                url = data.get("url")
                sha256 = data.get("sha256")
                
                if not all([server_version, url, sha256]):
                    logger.warning("Manifest missing required fields.")
                    return None
                
                if parse_version(server_version) <= self.current_version_tuple:
                    return None
                
                return UpdateManifest(version=server_version, url=url, sha256=sha256)
        
        except (urllib.error.URLError, json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug(f"Safe fail during update check: {e}")
            return None
        except Exception:
            logger.exception("Unexpected error during update check")
            return None
    
    def download_update(
        self,
        manifest: UpdateManifest,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        """
        Tải gói patch. Ném Exception chuyên biệt nếu lỗi mạng/integrity để App Host tự bắt và hiện Popup.
        """
        return download_file(
            url=manifest.url,
            dest_dir=self.download_dir,
            expected_sha256=manifest.sha256,
            progress_callback=progress_callback,
            filename=f"patch_v{manifest.version}.bin",
        )
    
    def install_and_restart(self, patch_path: Path, app_exe_path: Path) -> None:
        """
        Chuyển giao quyền kiểm soát cho Helper Process và kết thúc App hiện tại.
        Chỉ thoát app nếu helper khởi chạy thành công.
        """
        success = prepare_and_execute_helper(
            old_exe=app_exe_path,
            new_exe=patch_path,
        )
        
        if success:
            sys.exit(0)
        else:
            # Helper không khởi chạy được (user hủy UAC hoặc lỗi khác)
            # App tiếp tục chạy, không thoát
            logger.error("Failed to start updater helper. App will continue running.")