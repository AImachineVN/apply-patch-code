"""Donate tab - show support information (PayPal, bank, GitHub).

All value fields are readonly Entry widgets: user can select text and press
Ctrl+C to copy. No borders, background matches parent frame - looks like plain
text but is still selectable.
"""
from __future__ import annotations

import tkinter as tk

from ... import __version__

# =============================================================================
# Author + contact constants (update here if needed)
# =============================================================================

AUTHOR_NAME = "Nguyễn Cao"
PAYPAL_EMAIL = "support.aimachine@gmail.com"
PAYPAL_ME_USER = "AImachine"
PAYPAL_ME_URL = f"https://paypal.me/{PAYPAL_ME_USER}"
BANK_NAME = "Vietcombank"
BANK_STK = "1073988400"
BANK_HOLDER = "NGUYEN XUAN CAO"
GITHUB_USER = "AImachineVN"
GITHUB_REPO = "apply-patch-code"
GITHUB_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}"

# Fonts
FONT_UI = "Segoe UI"
FONT_UI_BOLD = (FONT_UI, 9, "bold")
FONT_HEADER = (FONT_UI, 11, "bold")
FONT_VALUE = (FONT_UI, 9)
FONT_SMALL = (FONT_UI, 8)
FONT_THANK = (FONT_UI, 9, "italic")


class DonateView(tk.Frame):
    """Tab showing donate information. All values are selectable/copyable via Ctrl+C."""

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self._build_ui()

    def _build_ui(self) -> None:
        # Header
        tk.Label(
            self,
            text="\U0001f49d  Support Apply Patch Code Development",
            font=FONT_HEADER,
            fg="#B22222",
        ).pack(pady=(8, 4), anchor="w", padx=10)

        tk.Frame(self, height=1, bg="#CCCCCC").pack(fill="x", padx=10, pady=(0, 8))

        # PayPal section
        self._section_label("\U0001f4e7  PayPal")
        self._copyable_row("Email:", PAYPAL_EMAIL)
        self._copyable_row("PayPal.Me:", PAYPAL_ME_URL)

        # Bank section
        self._section_label(f"\U0001f3e6  {BANK_NAME}")
        self._copyable_row("Account:", BANK_STK)
        self._copyable_row("Holder:", BANK_HOLDER)

        # GitHub section
        self._section_label("\U0001f310  GitHub")
        self._copyable_row("Repository:", GITHUB_URL)

        # Separator
        tk.Frame(self, height=1, bg="#CCCCCC").pack(fill="x", padx=10, pady=(12, 6))

        # Footer
        tk.Label(
            self,
            text=f"Author: {AUTHOR_NAME}   |   Version: v{__version__}",
            font=FONT_SMALL,
            fg="#666666",
        ).pack(pady=(0, 2))

        tk.Label(
            self,
            text="Thank you for your support! \u2764\ufe0f",
            font=FONT_THANK,
            fg="#B22222",
        ).pack(pady=(4, 2))

        # Hint
        tk.Label(
            self,
            text="Tip: Select text and press Ctrl+C to copy",
            font=FONT_SMALL,
            fg="#999999",
        ).pack(pady=(4, 6))

    def _section_label(self, text: str) -> None:
        tk.Label(
            self,
            text=text,
            font=FONT_UI_BOLD,
            fg="#333333",
            anchor="w",
        ).pack(fill="x", padx=15, pady=(4, 2))

    def _copyable_row(self, label: str, value: str) -> None:
        """Readonly Entry - no border, bg matches parent frame. Select + Ctrl+C."""
        row = tk.Frame(self)
        row.pack(fill="x", padx=30, pady=2)

        tk.Label(
            row,
            text=label,
            font=FONT_SMALL,
            fg="#666666",
            width=11,
            anchor="w",
        ).pack(side="left")

        parent_bg = self.cget("background")
        entry = tk.Entry(
            row,
            font=FONT_VALUE,
            relief="flat",
            bd=0,
            highlightthickness=0,
            borderwidth=0,
            bg=parent_bg,
            readonlybackground=parent_bg,
            fg="#000000",
            takefocus=0,
        )
        entry.insert(0, value)
        entry.configure(state="readonly")
        entry.selection_clear()
        entry.pack(side="left", fill="x", expand=True)

        def _select_all(_event: tk.Event[tk.Misc]) -> str:
            entry.select_range(0, "end")
            entry.icursor("end")
            return "break"

        entry.bind("<Control-a>", _select_all)
