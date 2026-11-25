"""
Profiles module - Quản lý thư mục profiles/ và 10 file PROFILE chuẩn.
Tự động khởi tạo khi load project lần đầu.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Tên thư mục PROFILE (viết thường, theo convention Unix/Linux)
PROFILES_DIR_NAME = "profiles"

# Danh sách 10 file PROFILE chuẩn với nội dung mẫu
PROFILES_TEMPLATE: dict[str, str] = {
    "00_PROJECT_OVERVIEW.md": """# PROJECT OVERVIEW

## Thông tin cơ bản
- **Tên dự án**: (Điền tên dự án)
- **Phiên bản**: 1.0.0
- **Mô tả ngắn**: (Mô tả mục đích dự án)

## Mục tiêu
(Điền mục tiêu chính của dự án)

## Đối tượng sử dụng
(Điền đối tượng người dùng mục tiêu)
""",

    "01_SYSTEM_ARCHITECTURE.md": """# SYSTEM ARCHITECTURE

## Kiến trúc tổng thể
(Mô tả kiến trúc hệ thống: Layered, Clean, Hexagonal, etc.)

## Các module chính
| Module | Trách nhiệm | File chính |
|---|---|---|
| (Module A) | (Mô tả) | (file.py) |

## Luồng xử lý dữ liệu
(Mô tả luồng dữ liệu từ input đến output)

## Công nghệ sử dụng
- Ngôn ngữ: Python 3.11+
- Framework: Tkinter (GUI)
- Build: Nuitka onefile
- Installer: Inno Setup
""",

    "02_BUSINESS_LOGIC.md": """# BUSINESS LOGIC

## Quy trình nghiệp vụ chính
(Mô tả quy trình từ lúc nhận input đến khi hoàn thành output)

## Quy tắc nghiệp vụ
- (Quy tắc 1)
- (Quy tắc 2)

## Các trạng thái nghiệp vụ
| Trạng thái | Mô tả | Điều kiện chuyển |
|---|---|---|
| (State A) | (Mô tả) | (Condition) |
""",

    "03_MODULE_REGISTRY.md": """# MODULE REGISTRY

## Danh sách module
| Module | File | Trạng thái | Ghi chú |
|---|---|---|---|
| Engine | src/apply_patch/engine.py | DONE | Thực thi operations |
| Schema | src/apply_patch/schema.py | DONE | Validate patch JSON |
| GUI | src/apply_patch/gui/ | DONE | Giao diện Tkinter |
""",

    "04_DATABASE_DESIGN.md": """# DATABASE DESIGN

## Tổng quan
Dự án không sử dụng database quan hệ. Dữ liệu persistent được lưu dưới dạng file JSON.

## Cấu trúc file dữ liệu
| File | Mục đích | Vị trí |
|---|---|---|
| project.json | Mô tả project | .apply_patch/project.json |
| patch_history.json | Lịch sử patch đã áp dụng | .apply_patch/patch_history.json |
| settings.json | Cấu hình ứng dụng | %APPDATA%/ApplyPatchCode/settings.json |
""",

    "05_API_DOCUMENTATION.md": """# API DOCUMENTATION

## CLI Commands

### apply_patch validate <patch.json>
Validate cú pháp và cấu trúc patch JSON.

### apply_patch apply <patch.json> [--project <path>]
Apply patch vào project.

### apply_patch auto <patch.json> [--project <path>]
Auto-detect project và apply patch.

### apply_patch detect [--project <path>]
Detect project type và cấu hình.

### apply_patch languages
Liệt kê các language handler đã đăng ký.

### apply_patch list-backups [--project <path>]
Liệt kê các backup đã tạo.

### apply_patch rollback <backup_path>
Rollback từ backup.

### apply_patch init-project [--path <dir>]
Khởi tạo project mới.

### apply_patch forget
Xóa cấu hình project hiện tại.
""",

    "06_TECHNICAL_DECISIONS.md": """# TECHNICAL DECISIONS

## Danh sách quyết định kỹ thuật

### TD-001: Chọn Python + Tkinter cho GUI
- **Ngày**: (YYYY-MM-DD)
- **Quyết định**: Sử dụng Python 3.11+ với Tkinter cho giao diện desktop
- **Lý do**: Đơn giản, cross-platform, không cần dependency nặng
- **Ảnh hưởng**: Dễ build với Nuitka, dung lượng nhỏ

### TD-002: Chọn Nuitka onefile cho build
- **Ngày**: (YYYY-MM-DD)
- **Quyết định**: Sử dụng Nuitka chế độ onefile để đóng gói
- **Lý do**: Single executable, dễ phân phối
- **Ảnh hưởng**: Thời gian khởi động chậm hơn PyInstaller nhưng dung lượng nhỏ hơn
""",

    "07_TASK_TRACKER.md": """# TASK TRACKER

## Danh sách task
| ID | Tên task | Trạng thái | File ảnh hưởng | Ghi chú |
|---|---|---|---|---|
| TASK-001 | (Tên task) | NOT_STARTED | (file.py) | (Ghi chú) |

## Trạng thái
- **NOT_STARTED**: Chưa bắt đầu
- **IN_PROGRESS**: Đang thực hiện
- **DONE_TESTED**: Hoàn thành và đã test
- **BLOCKED**: Bị chặn
""",

    "08_CHANGELOG.md": """# CHANGELOG

## Định dạng
- YYYY-MM-DD | PATCH-ID | Mô tả ngắn | files: file1, file2 | trang thai: DONE_TESTED

## Lịch sử thay đổi
(Thêm các entry mới ở đây)
""",

    "09_AI_HANDOFF.md": """# AI HANDOFF

## Thông tin bàn giao cho AI tiếp theo

### Trạng thái hiện tại
- (Mô tả trạng thái hiện tại của dự án)

### Công việc đã hoàn thành
- (Liệt kê các task đã hoàn thành)

### Công việc đang thực hiện
- (Liệt kê các task đang làm)

### Công việc cần làm tiếp
- (Liệt kê các task cần làm)

### Lưu ý quan trọng
- (Các thông tin AI tiếp theo bắt buộc phải biết)

### Quyết định kỹ thuật gần đây
- (Các quyết định đã đưa ra trong phiên làm việc)
""",
}


def get_profiles_dir(project_root: Path) -> Path:
    """Trả về đường dẫn thư mục profiles/ trong project."""
    return Path(project_root) / PROFILES_DIR_NAME


def ensure_profiles_initialized(project_root: Path) -> Path:
    """
    Đảm bảo thư mục profiles/ tồn tại với 10 file PROFILE chuẩn.
    
    Logic:
    - Nếu thư mục chưa có: tạo mới
    - Nếu file chưa có: tạo với nội dung mẫu
    - Nếu file đã có: giữ nguyên (KHÔNG ghi đè)
    
    Args:
        project_root: Đường dẫn gốc của project
        
    Returns:
        Path đến thư mục profiles/
        
    Raises:
        OSError: Nếu không thể tạo thư mục hoặc file (permission denied)
    """
    profiles_dir = get_profiles_dir(project_root)
    
    # Tạo thư mục profiles/ nếu chưa có
    try:
        profiles_dir.mkdir(parents=True, exist_ok=True)
        log.debug(f"Profiles directory ready: {profiles_dir}")
    except OSError as exc:
        log.error(f"Cannot create profiles directory: {exc}")
        raise
    
    # Tạo các file thiếu
    created_files = []
    for filename, content in PROFILES_TEMPLATE.items():
        file_path = profiles_dir / filename
        if not file_path.exists():
            try:
                file_path.write_text(content, encoding="utf-8")
                created_files.append(filename)
                log.info(f"Created profile file: {filename}")
            except OSError as exc:
                log.warning(f"Cannot create {filename}: {exc}")
                # Không raise, tiếp tục tạo các file khác
    
    if created_files:
        log.info(f"Initialized {len(created_files)} profile file(s): {', '.join(created_files)}")
    else:
        log.debug("All profile files already exist")
    
    return profiles_dir


def list_profile_files(project_root: Path) -> list[str]:
    """
    Liệt kê các file PROFILE đã tồn tại trong project.
    
    Args:
        project_root: Đường dẫn gốc của project
        
    Returns:
        Danh sách tên file đã tồn tại
    """
    profiles_dir = get_profiles_dir(project_root)
    if not profiles_dir.is_dir():
        return []
    
    existing = []
    for filename in PROFILES_TEMPLATE:
        if (profiles_dir / filename).exists():
            existing.append(filename)
    
    return existing


def get_missing_profile_files(project_root: Path) -> list[str]:
    """
    Liệt kê các file PROFILE còn thiếu trong project.
    
    Args:
        project_root: Đường dẫn gốc của project
        
    Returns:
        Danh sách tên file chưa tồn tại
    """
    profiles_dir = get_profiles_dir(project_root)
    if not profiles_dir.is_dir():
        return list(PROFILES_TEMPLATE.keys())
    
    missing = []
    for filename in PROFILES_TEMPLATE:
        if not (profiles_dir / filename).exists():
            missing.append(filename)
    
    return missing