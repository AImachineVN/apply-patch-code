from __future__ import annotations

import queue
import tkinter as tk
from typing import Any


class LogConsole(tk.Text):
    """Khung hiển thị log real-time phong cách Hồ sơ mật (Declassified Dossier)."""

    def __init__(self, master: tk.Misc, log_queue: queue.Queue[str], **kwargs: Any):
        super().__init__(
            master,
            bg="#E8E4C9",                # Màu nền vàng ngà của giấy cũ
            fg="#2C2C2C",                # Màu chữ đen xám (như mực in máy đánh chữ)
            insertbackground="#2C2C2C",  # Màu con trỏ gõ đồng bộ với màu chữ
            font=("Courier New", 7),     # Font máy đánh chữ cổ điển, Monospace (size 7)
            relief="flat",               # ĐÃ ĐIỀU CHỈNH: Tắt viền 3D của Text widget
            bd=0,                        # ĐÃ ĐIỀU CHỈNH: Bỏ border
            highlightthickness=0,        # ĐÃ ĐIỀU CHỈNH: Bỏ viền focus mặc định
            wrap="word",
            state="disabled",
            **kwargs
        )
        self.log_queue = log_queue
        self.poll_queue()

    def poll_queue(self) -> None:
        """Đọc log từ queue và append vào textbox."""
        while True:
            try:
                msg = self.log_queue.get_nowait()
                self.configure(state="normal")
                self.insert("end", msg + "\n")
                self.see("end")
                self.configure(state="disabled")
            except queue.Empty:
                break
        self.after(100, self.poll_queue)

    def clear(self) -> None:
        """Xóa toàn bộ log hiện tại."""
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")