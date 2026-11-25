from __future__ import annotations

# ĐÃ ĐIỀU CHỈNH: Sử dụng Absolute Import thay vì Relative Import 
# để Nuitka nhận diện đúng package context khi biên dịch Entry Point.
from apply_patch.gui.app import ApplyPatchApp


def main() -> None:
    """Điểm khởi chạy (Entry Point) của ứng dụng GUI."""
    app = ApplyPatchApp()
    app.mainloop()


if __name__ == "__main__":
    main()