"""Test module profiles.py - Auto-khởi tạo thư mục profiles/"""
from __future__ import annotations

from pathlib import Path

from apply_patch.profiles import (
    PROFILES_TEMPLATE,
    ensure_profiles_initialized,
    get_missing_profile_files,
    get_profiles_dir,
    list_profile_files,
)


def test_get_profiles_dir_returns_correct_path(tmp_path: Path) -> None:
    """get_profiles_dir trả về đường dẫn đúng."""
    profiles_dir = get_profiles_dir(tmp_path)
    assert profiles_dir == tmp_path / "profiles"


def test_ensure_profiles_creates_directory_and_files(tmp_path: Path) -> None:
    """ensure_profiles_initialized tạo thư mục và 10 file nếu chưa có."""
    profiles_dir = ensure_profiles_initialized(tmp_path)
    
    # Kiểm tra thư mục tồn tại
    assert profiles_dir.is_dir()
    
    # Kiểm tra 10 file đều được tạo
    for filename in PROFILES_TEMPLATE:
        file_path = profiles_dir / filename
        assert file_path.exists(), f"File {filename} should exist"
        assert file_path.is_file()
        
        # Kiểm tra nội dung không rỗng
        content = file_path.read_text(encoding="utf-8")
        assert len(content) > 0, f"File {filename} should not be empty"


def test_ensure_profiles_does_not_overwrite_existing_files(tmp_path: Path) -> None:
    """ensure_profiles_initialized KHÔNG ghi đè file đã tồn tại."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    
    # Tạo file 08_CHANGELOG.md với nội dung tùy chỉnh
    changelog_file = profiles_dir / "08_CHANGELOG.md"
    custom_content = "# CHANGELOG\n\n- 2026-01-01 | Custom entry\n"
    changelog_file.write_text(custom_content, encoding="utf-8")
    
    # Gọi ensure_profiles_initialized
    ensure_profiles_initialized(tmp_path)
    
    # Kiểm tra file không bị ghi đè
    assert changelog_file.read_text(encoding="utf-8") == custom_content


def test_ensure_profiles_creates_missing_files_only(tmp_path: Path) -> None:
    """ensure_profiles_initialized chỉ tạo file thiếu, giữ nguyên file đã có."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    
    # Tạo 3 file trước
    for filename in ["00_PROJECT_OVERVIEW.md", "01_SYSTEM_ARCHITECTURE.md", "08_CHANGELOG.md"]:
        (profiles_dir / filename).write_text(f"# {filename}\n", encoding="utf-8")
    
    # Gọi ensure_profiles_initialized
    ensure_profiles_initialized(tmp_path)
    
    # Kiểm tra tất cả 10 file đều tồn tại
    for filename in PROFILES_TEMPLATE:
        assert (profiles_dir / filename).exists()
    
    # Kiểm tra 3 file đã có vẫn giữ nội dung gốc
    assert (profiles_dir / "00_PROJECT_OVERVIEW.md").read_text(encoding="utf-8") == "# 00_PROJECT_OVERVIEW.md\n"
    assert (profiles_dir / "01_SYSTEM_ARCHITECTURE.md").read_text(encoding="utf-8") == "# 01_SYSTEM_ARCHITECTURE.md\n"
    assert (profiles_dir / "08_CHANGELOG.md").read_text(encoding="utf-8") == "# 08_CHANGELOG.md\n"


def test_list_profile_files_returns_existing_files(tmp_path: Path) -> None:
    """list_profile_files trả về danh sách file đã tồn tại."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    
    # Tạo 5 file
    for filename in list(PROFILES_TEMPLATE.keys())[:5]:
        (profiles_dir / filename).write_text("# Test\n", encoding="utf-8")
    
    existing = list_profile_files(tmp_path)
    assert len(existing) == 5


def test_list_profile_files_returns_empty_when_no_directory(tmp_path: Path) -> None:
    """list_profile_files trả về list rỗng nếu thư mục profiles/ không tồn tại."""
    existing = list_profile_files(tmp_path)
    assert existing == []


def test_get_missing_profile_files_returns_all_when_no_directory(tmp_path: Path) -> None:
    """get_missing_profile_files trả về tất cả 10 file nếu thư mục chưa có."""
    missing = get_missing_profile_files(tmp_path)
    assert len(missing) == 10
    assert set(missing) == set(PROFILES_TEMPLATE.keys())


def test_get_missing_profile_files_returns_only_missing(tmp_path: Path) -> None:
    """get_missing_profile_files chỉ trả về file thiếu."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    
    # Tạo 7 file
    for filename in list(PROFILES_TEMPLATE.keys())[:7]:
        (profiles_dir / filename).write_text("# Test\n", encoding="utf-8")
    
    missing = get_missing_profile_files(tmp_path)
    assert len(missing) == 3
    
    # Kiểm tra 3 file thiếu là 3 file cuối
    expected_missing = list(PROFILES_TEMPLATE.keys())[7:]
    assert set(missing) == set(expected_missing)


def test_ensure_profiles_idempotent(tmp_path: Path) -> None:
    """Gọi ensure_profiles_initialized nhiều lần không tạo file trùng."""
    # Gọi lần 1
    ensure_profiles_initialized(tmp_path)
    
    # Sửa nội dung 1 file
    changelog_file = tmp_path / "profiles" / "08_CHANGELOG.md"
    changelog_file.write_text("# Modified\n", encoding="utf-8")
    
    # Gọi lần 2
    ensure_profiles_initialized(tmp_path)
    
    # Kiểm tra file không bị ghi đè
    assert changelog_file.read_text(encoding="utf-8") == "# Modified\n"


def test_profiles_template_has_10_files() -> None:
    """PROFILES_TEMPLATE phải có đúng 10 file."""
    assert len(PROFILES_TEMPLATE) == 10


def test_profiles_template_all_files_have_content() -> None:
    """Tất cả file trong PROFILES_TEMPLATE phải có nội dung không rỗng."""
    for filename, content in PROFILES_TEMPLATE.items():
        assert len(content) > 0, f"File {filename} should have content"
        assert content.strip(), f"File {filename} should not be whitespace only"