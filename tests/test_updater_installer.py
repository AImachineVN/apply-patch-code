from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from apply_patch.updater.installer import (
    _generate_helper_script,
    _is_writable,
    prepare_and_execute_helper,
)


def test_generate_helper_script(tmp_path: Path):
    """Kiểm tra file .bat được sinh ra đúng cú pháp và chứa đủ tham số."""
    script_path = tmp_path / "helper.bat"
    old_exe = tmp_path / "old.exe"
    new_exe = tmp_path / "new.exe"

    _generate_helper_script(script_path, 1234, old_exe, new_exe)

    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")
    assert "1234" in content
    assert str(old_exe) in content
    assert str(new_exe) in content
    assert "tasklist" in content


def test_is_writable(tmp_path: Path):
    """Kiểm tra hàm _is_writable trả về True với thư mục có quyền ghi."""
    assert _is_writable(tmp_path) is True


@patch("apply_patch.updater.installer._is_writable", return_value=True)
@patch("apply_patch.updater.installer.subprocess.Popen")
def test_execute_helper_no_admin(mock_popen, mock_writable, tmp_path: Path):
    """Luồng chuẩn: Thư mục có quyền ghi -> Spawn ngầm không cần Admin."""
    old_exe = tmp_path / "app.exe"
    new_exe = tmp_path / "new.exe"
    old_exe.touch()
    new_exe.touch()

    with patch("apply_patch.updater.installer.tempfile.gettempdir", return_value=str(tmp_path)):
        result = prepare_and_execute_helper(old_exe, new_exe, app_pid=9999)
        assert result is True
        mock_popen.assert_called_once()


@patch("apply_patch.updater.installer._is_writable", return_value=False)
@patch("apply_patch.updater.installer.ctypes.windll.shell32.ShellExecuteW", return_value=42)
def test_execute_helper_with_admin(mock_shell_execute, mock_writable, tmp_path: Path):
    """Luồng UAC: Thư mục không có quyền ghi -> Gọi ShellExecuteW với verb 'runas'."""
    old_exe = tmp_path / "app.exe"
    new_exe = tmp_path / "new.exe"
    old_exe.touch()
    new_exe.touch()

    with patch("apply_patch.updater.installer.tempfile.gettempdir", return_value=str(tmp_path)):
        result = prepare_and_execute_helper(old_exe, new_exe, app_pid=9999)
        assert result is True
        mock_shell_execute.assert_called_once()


@patch("apply_patch.updater.installer._is_writable", return_value=False)
@patch("apply_patch.updater.installer.ctypes.windll.shell32.ShellExecuteW", return_value=5)
def test_execute_helper_with_admin_uac_cancelled(mock_shell_execute, mock_writable, tmp_path: Path):
    """Luồng UAC bị hủy: ShellExecuteW trả về <= 32 -> Hàm trả về False."""
    old_exe = tmp_path / "app.exe"
    new_exe = tmp_path / "new.exe"
    old_exe.touch()
    new_exe.touch()

    with patch("apply_patch.updater.installer.tempfile.gettempdir", return_value=str(tmp_path)):
        result = prepare_and_execute_helper(old_exe, new_exe, app_pid=9999)
        assert result is False
        mock_shell_execute.assert_called_once()