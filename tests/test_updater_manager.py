import json
import urllib.error
from pathlib import Path
from unittest.mock import patch

from apply_patch.updater.crypto_utils import generate_keypair, sign_data
from apply_patch.updater.manager import UpdateManager, parse_version
from apply_patch.updater.models import UpdateManifest


def test_parse_version_logic():
    """Kiểm tra thuật toán so sánh tuple version."""
    assert parse_version("1.0.0") == (1, 0, 0)
    assert parse_version("1.10.2") == (1, 10, 2)
    assert parse_version("1.10.2") > parse_version("1.9.9")
    assert parse_version("1.2.0") < parse_version("1.10.0")
    assert parse_version("2.0.0") > parse_version("1.99.99")
    # Xử lý chuỗi lỗi
    assert parse_version("1.0.beta") == (1, 0, 0)


def _create_signed_manifest(priv_key: bytes, version: str, url: str, sha256: str) -> bytes:
    """Hàm phụ trợ tạo JSON manifest đã ký số."""
    payload = {"sha256": sha256, "url": url, "version": version}
    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sig = sign_data(priv_key, payload_str.encode("utf-8"))
    
    data = payload.copy()
    data["signature"] = sig.hex()
    return json.dumps(data).encode("utf-8")


class MockResponse:
    def __init__(self, data: bytes):
        self.data = data

    def read(self) -> bytes:
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@patch("apply_patch.updater.manager.urllib.request.urlopen")
def test_check_for_updates_success(mock_urlopen, tmp_path: Path):
    """Luồng chuẩn: Server trả về manifest hợp lệ, version mới hơn."""
    priv, pub = generate_keypair()
    manifest_json = _create_signed_manifest(priv, "1.0.1", "http://test/patch.bin", "a" * 64)
    mock_urlopen.return_value = MockResponse(manifest_json)

    mgr = UpdateManager("1.0.0", pub, "http://test/manifest.json", tmp_path)
    result = mgr.check_for_updates()

    assert result is not None
    assert isinstance(result, UpdateManifest)
    assert result.version == "1.0.1"
    assert result.url == "http://test/patch.bin"


@patch("apply_patch.updater.manager.urllib.request.urlopen")
def test_check_for_updates_bad_signature(mock_urlopen, tmp_path: Path):
    """Bảo mật: Chữ ký sai (Server bị hack / MITM) -> Trả về None."""
    priv, _ = generate_keypair()
    _, wrong_pub = generate_keypair()
    manifest_json = _create_signed_manifest(priv, "1.0.1", "http://test/patch.bin", "a" * 64)
    mock_urlopen.return_value = MockResponse(manifest_json)

    mgr = UpdateManager("1.0.0", wrong_pub, "http://test/manifest.json", tmp_path)
    result = mgr.check_for_updates()
    assert result is None


@patch("apply_patch.updater.manager.urllib.request.urlopen")
def test_check_for_updates_older_version(mock_urlopen, tmp_path: Path):
    """Logic: Server trả về version cũ hơn hoặc bằng -> Trả về None."""
    priv, pub = generate_keypair()
    manifest_json = _create_signed_manifest(priv, "0.9.0", "http://test/patch.bin", "a" * 64)
    mock_urlopen.return_value = MockResponse(manifest_json)

    mgr = UpdateManager("1.0.0", pub, "http://test/manifest.json", tmp_path)
    result = mgr.check_for_updates()
    assert result is None


@patch("apply_patch.updater.manager.urllib.request.urlopen")
def test_check_for_updates_network_error(mock_urlopen, tmp_path: Path):
    """Ổn định: Mất mạng / Server sập -> Trả về None, không crash App."""
    mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable")
    _, pub = generate_keypair()

    mgr = UpdateManager("1.0.0", pub, "http://test/manifest.json", tmp_path)
    result = mgr.check_for_updates()
    assert result is None


@patch("apply_patch.updater.manager.urllib.request.urlopen")
def test_check_for_updates_malformed_json(mock_urlopen, tmp_path: Path):
    """Defense in Depth: Server trả về rác (không phải JSON) -> Trả về None."""
    mock_urlopen.return_value = MockResponse(b"this is not json")
    _, pub = generate_keypair()

    mgr = UpdateManager("1.0.0", pub, "http://test/manifest.json", tmp_path)
    result = mgr.check_for_updates()
    assert result is None


@patch("apply_patch.updater.manager.download_file")
def test_download_update(mock_download, tmp_path: Path):
    """Tích hợp: Gọi đúng hàm download_file với tham số từ Manifest."""
    manifest = UpdateManifest(version="1.0.1", url="http://test/p", sha256="abc")
    mock_download.return_value = tmp_path / "patch.bin"
    
    mgr = UpdateManager("1.0.0", b"0" * 32, "http://test/m", tmp_path)
    res = mgr.download_update(manifest)
    
    assert res == tmp_path / "patch.bin"
    mock_download.assert_called_once()