import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from apply_patch.updater.network import (
    IntegrityError,
    NetworkTimeoutError,
    SizeLimitExceededError,
    download_file,
)


class MockHeaders:
    def __init__(self, d: dict):
        self.d = d

    def get(self, key: str):
        return self.d.get(key)


class MockResponse:
    def __init__(self, data: bytes, status: int = 200, headers: dict | None = None):
        self.data = data
        self.status = status
        self.headers = MockHeaders(headers or {})
        self.read_idx = 0

    def getcode(self) -> int:
        return self.status

    def read(self, size: int = -1) -> bytes:
        if size == -1:
            chunk = self.data[self.read_idx :]
            self.read_idx = len(self.data)
            return chunk
        if self.read_idx >= len(self.data):
            return b""
        chunk = self.data[self.read_idx : self.read_idx + size]
        self.read_idx += size
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_download_success(tmp_path: Path):
    """Luồng chuẩn: Tải thành công, SHA-256 khớp, file tmp được rename."""
    data = b"hello world patch data"
    expected_hash = hashlib.sha256(data).hexdigest()

    with patch("apply_patch.updater.network.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(
            data, headers={"Content-Length": str(len(data))}
        )

        result = download_file(
            url="http://test/patch.bin",
            dest_dir=tmp_path,
            expected_sha256=expected_hash,
            filename="patch.bin",
        )

        assert result == tmp_path / "patch.bin"
        assert result.read_bytes() == data
        assert not (tmp_path / "patch.bin.tmp").exists()


def test_integrity_fail(tmp_path: Path):
    """Bảo mật: SHA-256 sai lệch -> Xóa file tmp, ném IntegrityError."""
    data = b"hello world patch data"
    wrong_hash = "0" * 64

    with patch("apply_patch.updater.network.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(
            data, headers={"Content-Length": str(len(data))}
        )

        with pytest.raises(IntegrityError):
            download_file(
                url="http://test/patch.bin",
                dest_dir=tmp_path,
                expected_sha256=wrong_hash,
                filename="patch.bin",
            )

        assert not (tmp_path / "patch.bin.tmp").exists()
        assert not (tmp_path / "patch.bin").exists()


def test_size_limit_fail(tmp_path: Path):
    """Bảo mật: Server báo Content-Length vượt limit -> Hủy ngay, ném SizeLimitExceededError."""
    data = b"x" * 100
    expected_hash = hashlib.sha256(data).hexdigest()

    with patch("apply_patch.updater.network.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(data, headers={"Content-Length": "200"})

        with pytest.raises(SizeLimitExceededError):
            download_file(
                url="http://test/patch.bin",
                dest_dir=tmp_path,
                expected_sha256=expected_hash,
                max_size_bytes=100,
                filename="patch.bin",
            )


def test_size_limit_on_the_fly(tmp_path: Path):
    """Bảo mật: Server không gửi Content-Length, nhưng dữ liệu thực tế vượt limit."""
    data = b"x" * 200
    expected_hash = hashlib.sha256(data).hexdigest()

    with patch("apply_patch.updater.network.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(data, headers={})

        with pytest.raises(SizeLimitExceededError):
            download_file(
                url="http://test/patch.bin",
                dest_dir=tmp_path,
                expected_sha256=expected_hash,
                max_size_bytes=100,
                filename="patch.bin",
            )


def test_timeout_fail(tmp_path: Path):
    """Ổn định: Mất kết nối / Timeout -> Ném NetworkTimeoutError."""
    with patch("apply_patch.updater.network.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = TimeoutError("timed out")

        with pytest.raises(NetworkTimeoutError):
            download_file(
                url="http://test/patch.bin",
                dest_dir=tmp_path,
                expected_sha256="0" * 64,
                filename="patch.bin",
            )


def test_resume_download(tmp_path: Path):
    """Tính năng Resume: File tmp có sẵn -> Gửi Range header -> Tải tiếp và verify hash."""
    first_half = b"first_half_data"
    second_half = b"second_half_data"
    full_data = first_half + second_half
    expected_hash = hashlib.sha256(full_data).hexdigest()

    tmp_file = tmp_path / "patch.bin.tmp"
    tmp_file.write_bytes(first_half)

    with patch("apply_patch.updater.network.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(
            second_half,
            status=206,
            headers={"Content-Length": str(len(second_half))},
        )

        result = download_file(
            url="http://test/patch.bin",
            dest_dir=tmp_path,
            expected_sha256=expected_hash,
            filename="patch.bin",
        )

        assert result == tmp_path / "patch.bin"
        assert result.read_bytes() == full_data

        # Verify Range header was sent correctly
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Range") == f"bytes={len(first_half)}-"