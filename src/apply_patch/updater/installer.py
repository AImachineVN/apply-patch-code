from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BATCH_TEMPLATE = """@echo off
:: Apply Patch Code Updater Helper
set "PID={app_pid}"
set "OLD_EXE={old_exe}"
set "NEW_EXE={new_exe}"
set "BACKUP_EXE={old_exe}.bak"

:WAIT_LOOP
tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >NUL
    goto WAIT_LOOP
)

:: 1. Backup file gốc
move /Y "%OLD_EXE%" "%BACKUP_EXE%" >NUL 2>&1

:: 2. Ghi đè file mới
copy /Y "%NEW_EXE%" "%OLD_EXE%" >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    :: Rollback nếu copy lỗi (do AV hoặc File Locking cứng)
    move /Y "%BACKUP_EXE%" "%OLD_EXE%" >NUL 2>&1
    goto SELF_DELETE
)

:: 3. Khởi chạy App mới
start "" "%OLD_EXE%"

:: 4. Xóa file Backup
del /F /Q "%BACKUP_EXE%" >NUL 2>&1

:SELF_DELETE
:: Thủ thuật tự xóa file .bat (Self-Deletion)
(goto) 2>nul & del "%~f0"
"""


def _is_writable(directory: Path) -> bool:
    """Kiểm tra xem thư mục có quyền ghi không (để quyết định có cần UAC Admin không)."""
    try:
        test_file = directory / ".apply_patch_write_test"
        test_file.touch()
        test_file.unlink()
        return True
    except OSError:
        return False


def _generate_helper_script(
    script_path: Path,
    app_pid: int,
    old_exe: Path,
    new_exe: Path,
) -> None:
    """Sinh ra file .bat với các tham số đã được format."""
    content = BATCH_TEMPLATE.format(
        app_pid=app_pid,
        old_exe=str(old_exe),
        new_exe=str(new_exe),
    )
    script_path.write_text(content, encoding="utf-8")


def prepare_and_execute_helper(
    old_exe: Path,
    new_exe: Path,
    app_pid: int | None = None,
) -> bool:
    """
    Tạo Helper Script và spawn nó thành một tiến trình độc lập.
    Tự động yêu cầu quyền Admin (UAC) nếu App nằm trong thư mục bị bảo vệ.
    
    Returns:
        bool: True nếu helper khởi chạy thành công, False nếu thất bại
              (bao gồm trường hợp user hủy UAC).
    """
    if app_pid is None:
        app_pid = os.getpid()
    
    temp_dir = Path(tempfile.gettempdir())
    script_path = temp_dir / "apply_patch_helper.bat"
    _generate_helper_script(script_path, app_pid, old_exe, new_exe)
    
    needs_admin = not _is_writable(old_exe.parent)
    
    if sys.platform == "win32" and needs_admin:
        # ShellExecuteW trả về > 32 nếu thành công, <= 32 nếu thất bại
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", str(script_path), "", None, 1
        )
        return int(result) > 32
    else:
        # Spawn độc lập (Detached) để không bị tắt theo khi App gốc sys.exit()
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        try:
            subprocess.Popen(
                [str(script_path)],
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                close_fds=True,
            )
            return True
        except Exception:
            return False