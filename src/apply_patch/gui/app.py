from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..utils.path_resolver import get_resource_path
from .views.donate_view import DonateView
from .views.main_view import MainView


class ApplyPatchApp(tk.Tk):
    """Cua so ung dung chinh phong cach Co dien - Fixed Size 430x330."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Apply Patch Code v1.0")

        default_font = ("Tahoma", 8)
        self.option_add("*Font", default_font)

        style = ttk.Style(self)
        try:
            style.theme_use("winnative")
        except tk.TclError:
            style.theme_use("clam")

        self._load_window_icon()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.main_view = MainView(notebook)
        notebook.add(self.main_view, text="Patch")

        self.donate_view = DonateView(notebook)
        notebook.add(self.donate_view, text="Donate")

        self.geometry("500x420")
        self.resizable(False, False)
        self.minsize(500, 420)
        self.maxsize(500, 420)

    def _load_window_icon(self) -> None:
        """
        Load icon cho cua so chinh.
        Hoat dong an toan trong 2 moi truong:
        - Dev mode (python -m apply_patch.gui.gui_main)
        - Nuitka onefile (.exe) - noi CWD khong phai la noi co assets
        Uu tien:
        1. File .ico (native Windows icon, nhe nhat, tot nhat cho title bar)
        2. File .png (fallback qua iconphoto)
        3. Neu ca 2 deu fail -> im lang bo qua, app van chay voi icon mac dinh
        """
        ico_path = get_resource_path("assets/logo.ico")
        if ico_path and ico_path.exists():
            try:
                self.iconbitmap(default=str(ico_path))  # type: ignore[no-untyped-call]
                return
            except tk.TclError:
                pass

        png_path = get_resource_path("assets/logo.png")
        if png_path and png_path.exists():
            try:
                icon_img = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, icon_img)
                self._icon_photo_ref = icon_img
                return
            except tk.TclError:
                pass


def main() -> None:
    """Entry point cho GUI."""
    app = ApplyPatchApp()
    app.mainloop()


if __name__ == "__main__":
    main()