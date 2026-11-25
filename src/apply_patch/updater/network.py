from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path


class NetworkTimeoutError(Exception):
    """Lỗi kết nối mạng hoặc timeout."""


class SizeLimitExceededError(Exception):
    """Lỗi vượt quá giới hạn dung lượng cho phép."""


class IntegrityError(Exception):
    """Lỗi sai lệch mã băm SHA-256 (dữ liệu bị giả mạo hoặc lỗi)."""


def download_file(
    url: str,
    dest_dir: Path,
    expected_sha256: str,
    max_size_bytes: int = 100 * 1024 * 1024,
    progress_callback: Callable[[int, int], None] | None = None,
    filename: str = "patch.bin",
) -> Path:
    """
    Tải file từ URL về dest_dir với cơ chế Resume, giới hạn dung lượng và verify SHA-256.
    Trả về đường dẫn file thật nếu thành công. Ném Exception chuyên biệt nếu thất bại.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_dir / f"{filename}.tmp"
    final_path = dest_dir / filename

    downloaded_size = 0
    mode = "wb"

    # Kiểm tra file tmp để hỗ trợ tải tiếp (Resume)
    if tmp_path.exists():
        downloaded_size = tmp_path.stat().st_size
        mode = "ab"

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "ApplyPatchCode-Updater/1.0")
    
    if downloaded_size > 0:
        req.add_header("Range", f"bytes={downloaded_size}-")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status_code = response.getcode()
            
            # Nếu server không hỗ trợ Range và trả về 200 (tải lại từ đầu)
            if downloaded_size > 0 and status_code == 200:
                downloaded_size = 0
                mode = "wb"

            headers = response.headers
            content_length = headers.get("Content-Length") if hasattr(headers, "get") else None
            
            if content_length is not None:
                total_size = int(content_length) + downloaded_size
                if total_size > max_size_bytes:
                    raise SizeLimitExceededError(
                        f"File size {total_size} exceeds limit {max_size_bytes}"
                    )
            else:
                total_size = 0  # Không biết trước dung lượng

            sha256 = hashlib.sha256()

            # Nếu tải tiếp, phải băm lại phần đã tải để đảm bảo tính toàn vẹn cuối cùng
            if downloaded_size > 0 and mode == "ab":
                with open(tmp_path, "rb") as f:
                    while chunk := f.read(65536):
                        sha256.update(chunk)

            bytes_read = downloaded_size
            with open(tmp_path, mode) as f:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    sha256.update(chunk)
                    bytes_read += len(chunk)

                    # Kiểm tra giới hạn dung lượng on-the-fly (phòng hờ server không gửi Content-Length)
                    if bytes_read > max_size_bytes:
                        raise SizeLimitExceededError(
                            f"Downloaded size exceeds limit {max_size_bytes}"
                        )

                    if progress_callback and total_size > 0:
                        progress_callback(bytes_read, total_size)

    # ĐÃ SỬA LỖI: Bẫy tường minh các Custom Exception để re-raise, tránh bị nuốt bởi Exception tổng quát
    except (SizeLimitExceededError, IntegrityError):
        raise
    except TimeoutError as e:
        raise NetworkTimeoutError(f"Timeout: {e}") from e
    except urllib.error.URLError as e:
        if "timed out" in str(e).lower():
            raise NetworkTimeoutError(f"Network timeout: {e}") from e
        raise NetworkTimeoutError(f"Network error: {e}") from e
    except Exception as e:
        raise NetworkTimeoutError(f"Unexpected network error: {e}") from e

    # Verify SHA-256
    if sha256.hexdigest().lower() != expected_sha256.lower():
        if tmp_path.exists():
            tmp_path.unlink()
        raise IntegrityError("SHA-256 mismatch. File might be tampered or corrupted.")

    # Atomic rename
    if final_path.exists():
        final_path.unlink()
    tmp_path.rename(final_path)

    return final_path