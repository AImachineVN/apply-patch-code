from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """
    Tự động hóa quá trình biên dịch Nuitka.
    Tạo ra bản build Standalone, tắt Console, bundle assets và tối ưu dung lượng.
    """
    root_dir = Path(__file__).parent.resolve()
    entry_point = root_dir / "src" / "apply_patch" / "gui" / "gui_main.py"
    icon_path = root_dir / "assets" / "logo.ico"
    assets_dir = root_dir / "assets"
    schemas_dir = root_dir / "src" / "apply_patch" / "core" / "schemas"

    if not entry_point.exists():
        print(f"[ERROR] Khong tim thay entry point: {entry_point}")
        sys.exit(1)

    if not assets_dir.is_dir():
        print(f"[ERROR] Khong tim thay thu muc assets: {assets_dir}")
        sys.exit(1)

    if not schemas_dir.is_dir():
        print(f"[ERROR] Khong tim thay thu muc schemas: {schemas_dir}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",                         # Nén toàn bộ thành 1 file .exe duy nhất để phân phối
        "--windows-console-mode=disable",    # Đã debug xong, tắt Console đen cho người dùng cuối
        "--assume-yes-for-downloads",
        "--lto=yes",
        "--remove-output",
        "--output-dir=dist",
        "--enable-plugin=tk-inter",
        # Metadata thương mại (Giúp Windows tin tưởng, giảm cảnh báo SmartScreen)
        "--windows-company-name=ApplyPatchCode",
        "--windows-product-name=Apply Patch Code",
        "--windows-file-version=1.0.0.0",
        "--windows-product-version=1.0.0.0",
        "--windows-file-description=Apply Patch Code",
        "--output-filename=ApplyPatchCode.exe",
        # Đóng gói assets (icon, hình ảnh tĩnh)
        # Cú pháp: --include-data-dir=<absolute_path>=<bundle_path>
        f"--include-data-dir={assets_dir}=assets",
        # [H1 FIX] Đóng gói JSON schemas — bắt buộc cho tầng 2 validation
        f"--include-data-dir={schemas_dir}=src/apply_patch/core/schemas",
        "--nofollow-import-to=pytest,setuptools,pip,distutils,tkinter.test",
        "--include-package=apply_patch",
    ]

    if icon_path.exists():
        cmd.append(f"--windows-icon-from-ico={icon_path}")
    else:
        print(f"[WARN] Khong tim thay icon: {icon_path}. Exe se khong co icon.")

    cmd.append(str(entry_point))

    print("[INFO] Bat dau qua trinh bien dich Nuitka (Release Mode)...")
    print(f"[INFO] Root dir   : {root_dir}")
    print(f"[INFO] Entry point: {entry_point}")
    print(f"[INFO] Assets dir : {assets_dir}")
    print(f"[INFO] Schemas dir: {schemas_dir}")
    print(f"[INFO] Icon path  : {icon_path}")

    try:
        subprocess.run(cmd, check=True)
        print("\n[SUCCESS] Bien dich thanh cong!")
        print(f"[OUTPUT] File .exe nam tai: {root_dir / 'dist' / 'ApplyPatchCode.exe'}")
    except subprocess.CalledProcessError as e:
        print(f"\n[FAILED] Bien dich that bai voi ma loi: {e.returncode}")
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()