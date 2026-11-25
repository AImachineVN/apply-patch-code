from __future__ import annotations

import queue
import re
import time
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import ClassVar

from ...patch_history import (
    PatchHistory,
    compute_file_sha256,
    get_history_path,
    get_patch_status,
)
from ...source_snapshot import generate_snapshot
from ...undo import undo_patch
from ...utils.path_resolver import get_resource_path
from ...utils.settings import AppSettings, load_settings, save_settings
from ..widgets.log_console import LogConsole
from ..worker import PatchWorker, WorkerTask

# [GAP-7 FIX v2] Map status → English display text (Treeview 2 columns auto-align).
STATUS_DISPLAY: dict[str, str] = {
    "new": "Not Patched",
    "in_progress": "Patching...",
    "applied_same": "Patched",
    "applied_modified": "Patched (file modified)",
    "failed": "Patch failed",
    "undone": "Undone",
    "unknown": "Unknown",
}

_PATCH_NUM_RE = re.compile(r"patch_(\d{1,3}(?:\.\d+)*)_", re.IGNORECASE)


def _patch_sort_key(p: Path) -> tuple[tuple[int, ...], str]:
    """Sort Patch_<num>[.sub]_<name>.json by numeric prefix.

    Patch_1 < Patch_2 < ... < Patch_9 < Patch_10 < Patch_10.1 < Patch_10.10 < Patch_11
    Used with reverse=True -> newest first.
    Non-matching files (e.g. Patch_2026_110_*, patch_xxx, other) sort to bottom.
    """
    m = _PATCH_NUM_RE.match(p.name)
    if m:
        parts = tuple(int(x) for x in m.group(1).split("."))
        return (parts, p.name.lower())
    return ((-1,), p.name.lower())


class _CustomDialog(tk.Toplevel):
    """
    Compact dialog replacing Tkinter's messagebox.
    - Fixed size: 260x110 pixels.
    - Tahoma 8pt font matching the app.
    - App icon (not default folder icon).
    - Message area is a scrollable Text widget for full content.
    """

    ICONS: ClassVar[dict[str, tuple[str, str]]] = {
        "success": ("\u2713", "#28a745"),
        "error": ("\u2717", "#dc3545"),
        "warning": ("\u26a0", "#b8860b"),
        "info": ("\u2139", "#1565c0"),
    }

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        message: str,
        kind: str = "info",
        auto_close_seconds: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("260x110")
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]

        try:
            icon_path = get_resource_path("assets/logo.ico")
            if icon_path.exists():
                self.wm_iconbitmap(default=str(icon_path))  # type: ignore[no-untyped-call]
        except Exception:
            pass

        self.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x = px + (pw - 260) // 2
        y = py + (ph - 110) // 2
        self.geometry(f"+{x}+{y}")

        icon_char, icon_color = self.ICONS.get(kind, self.ICONS["info"])
        tk.Label(
            self,
            text=icon_char,
            font=("Segoe UI", 16, "bold"),
            fg=icon_color,
        ).pack(pady=(4, 0))

        msg_frame = tk.Frame(self)
        msg_frame.pack(fill="both", expand=True, padx=8, pady=2)

        self.msg_text = tk.Text(
            msg_frame,
            font=("Tahoma", 8),
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=self.cget("background"),
            state="disabled",
            padx=2,
            pady=2,
        )
        self.msg_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(
            msg_frame,
            orient="vertical",
            command=self.msg_text.yview,
        )
        self.msg_text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.msg_text.config(state="normal")
        self.msg_text.delete("1.0", "end")
        self.msg_text.insert("1.0", message)
        self.msg_text.config(state="disabled")

        def close() -> None:
            if self.winfo_exists():
                self.destroy()

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(0, 4))

        tk.Button(
            btn_frame,
            text="OK",
            width=8,
            command=close,
            relief="raised",
            bd=1,
            font=("Tahoma", 8),
        ).pack(side="left", padx=2)

        if kind == "error":
            def copy_msg() -> None:
                self.clipboard_clear()
                self.clipboard_append(message)

            tk.Button(
                btn_frame,
                text="Copy",
                width=8,
                command=copy_msg,
                relief="raised",
                bd=1,
                font=("Tahoma", 8),
            ).pack(side="left", padx=2)

        self.bind("<Escape>", lambda e: close())

        if auto_close_seconds and auto_close_seconds > 0:
            self.after(auto_close_seconds * 1000, close)


class MainView(tk.Frame):
    """Main application window — Classic style with real-time auto-refresh."""

    POLL_INTERVAL_SECONDS = 1.5
    PATCH_LISTBOX_HEIGHT = 4
    TERMINAL_HEIGHT = 10

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: PatchWorker | None = None
        self.patch_files: list[Path] = []
        self._last_patch_dir: Path | None = None
        self._current_selection_name: str | None = None
        self._patch_history: PatchHistory = PatchHistory()
        self._patch_status_cache: dict[str, tuple[str, str]] = {}

        self._patch_in_progress: str | None = None
        self._polling_after_id: str | None = None
        self._last_known_state: set[tuple[str, float]] = set()
        self._last_change_time: float = 0.0
        self._debounce_seconds = 0.5

        self.grid_columnconfigure(1, weight=1)

        tk.Label(self, text="Project:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.project_entry = tk.Entry(self, relief="sunken", bd=2)
        self.project_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        tk.Button(
            self, text="Browse", relief="raised", bd=1, width=8,
            command=self.browse_project
        ).grid(row=0, column=2, padx=5, pady=3)

        tk.Label(self, text="Patches:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        self.patch_dir_entry = tk.Entry(self, relief="sunken", bd=2)
        self.patch_dir_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=3)
        tk.Button(
            self, text="Browse", relief="raised", bd=1, width=8,
            command=self.browse_patch_dir
        ).grid(row=1, column=2, padx=5, pady=3)

        tk.Label(
            self, text="Available Patches:"
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=5, pady=(8, 2))

        list_frame = tk.Frame(self)
        list_frame.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=5, pady=2)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style(self)
        style.configure("Patch.Treeview", font=("Consolas", 8), rowheight=20)
        # Heading: bold, larger, dark color for visibility
        style.configure(
            "Patch.Treeview.Heading",
            font=("Tahoma", 7),
            foreground="#000000",
            background="#E8E8E8",
            padding=(4, 4),
            relief="raised",
        )
        # Hover effect on heading
        style.map(
            "Patch.Treeview.Heading",
            background=[("active", "#D0D0D0")],
        )

        self.patch_tree = ttk.Treeview(
            list_frame,
            columns=("filename", "status"),
            show="headings",
            height=self.PATCH_LISTBOX_HEIGHT,
            selectmode="browse",
            style="Patch.Treeview",
        )
        self.patch_tree.heading("filename", text="Patch File", anchor="center")
        self.patch_tree.heading("status", text="Status", anchor="center")
        self.patch_tree.column("filename", width=280, anchor="w", minwidth=150, stretch=True)
        self.patch_tree.column("status", width=200, anchor="w", minwidth=150, stretch=False)
        self.patch_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.patch_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.patch_tree.config(yscrollcommand=scrollbar.set)

        # [STATUS PROTECTED] Prevent filename from ever hiding status column
        self._computed_status_min = 150
        self._pending_enforce_id: str | None = None
        self.patch_tree.bind("<Configure>", self._on_tree_configure)
        self.patch_tree.bind("<ButtonRelease-1>", self._on_tree_release)
        self.patch_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=6)

        self.btn_execute = tk.Button(
            btn_frame,
            text="Execute Selected Patch",
            relief="raised",
            bd=2,
            font=("Tahoma", 8),
            bg="#E0E0E0",
            pady=5,
            padx=5,
            command=self.execute_selected,
        )
        self.btn_execute.pack(side="left", padx=(0, 8))

        # [SNAPSHOT] Secondary button to generate source snapshot for AI handoff
        self.btn_snapshot = tk.Button(
            btn_frame,
            text="Snapshot Source",
            relief="raised",
            bd=2,
            font=("Tahoma", 8),
            bg="#E0E0E0",
            pady=5,
            padx=5,
            command=self.snapshot_source,
        )
        self.btn_snapshot.pack(side="left")
        # [HOVER] Bind mouse enter/leave for hover effect (same as btn_execute)
        self.btn_snapshot.bind("<Enter>", self._on_snapshot_hover_enter)
        self.btn_snapshot.bind("<Leave>", self._on_snapshot_hover_leave)
        # [HOVER] Bind mouse enter/leave for hover effect
        self.btn_execute.bind("<Enter>", self._on_execute_hover_enter)
        self.btn_execute.bind("<Leave>", self._on_execute_hover_leave)

        # [UNDO] Undo Execute button - restore files from backup session
        self.btn_undo = tk.Button(
            btn_frame,
            text="Undo Execute",
            relief="raised",
            bd=2,
            font=("Tahoma", 8),
            bg="#E0E0E0",
            pady=5,
            padx=5,
            state="disabled",
            command=self.undo_selected,
        )
        self.btn_undo.pack(side="left", padx=(8, 0))
        self.btn_undo.bind("<Enter>", self._on_undo_hover_enter)
        self.btn_undo.bind("<Leave>", self._on_undo_hover_leave)

        tk.Label(self, text="Terminal:").grid(
            row=5, column=0, columnspan=3, sticky="w", padx=5, pady=(4, 2)
        )
        terminal_frame = tk.Frame(self, relief="sunken", bd=2)
        terminal_frame.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=5, pady=(0, 5))
        terminal_frame.grid_columnconfigure(0, weight=1)
        terminal_frame.grid_rowconfigure(0, weight=1)

        self.log_console = LogConsole(
            terminal_frame,
            self.log_queue,
            height=self.TERMINAL_HEIGHT
        )
        self.log_console.grid(row=0, column=0, sticky="nsew")

        self.grid_rowconfigure(6, weight=1)

        self.winfo_toplevel().protocol("WM_DELETE_WINDOW", self._on_close)

        self._load_last_session()
        self._start_polling()
        # [POLL FIX] F5 = force refresh patches immediately
        self.winfo_toplevel().bind("<F5>", self._on_f5_pressed)

    def _show_dialog(
        self,
        title: str,
        message: str,
        kind: str = "info",
        auto_close_seconds: int | None = None,
    ) -> None:
        root = self.winfo_toplevel()
        _CustomDialog(root, title, message, kind, auto_close_seconds)

    def _load_last_session(self) -> None:
        settings = load_settings()
        if settings.last_project_path:
            project_path = Path(settings.last_project_path)
            if project_path.is_dir():
                self.project_entry.insert(0, settings.last_project_path)
                self.log_queue.put(
                    f"[INFO] Restored last project: {settings.last_project_path}"
                )
            else:
                self.log_queue.put(
                    f"[WARN] Last project path no longer exists: {settings.last_project_path}"
                )
        if settings.last_patches_path:
            patches_path = Path(settings.last_patches_path)
            if patches_path.is_dir():
                self.patch_dir_entry.insert(0, settings.last_patches_path)
                self._last_patch_dir = patches_path
                self.scan_patches(patches_path)
                self.log_queue.put(
                    f"[INFO] Restored last patches dir: {settings.last_patches_path}"
                )
            else:
                self.log_queue.put(
                    f"[WARN] Last patches path no longer exists: {settings.last_patches_path}"
                )

    def _save_current_session(self) -> None:
        project_str = self.project_entry.get().strip()
        patches_str = self.patch_dir_entry.get().strip()
        settings = AppSettings(
            last_project_path=project_str,
            last_patches_path=patches_str,
        )
        if save_settings(settings):
            self.log_queue.put("[INFO] Session saved successfully")
        else:
            self.log_queue.put("[WARN] Failed to save session settings")

    def _start_polling(self) -> None:
        """[M2 FIX] Start polling on the main thread via Tkinter.after().

        Previously used threading.Thread — violates Tkinter thread-safety rules
        (background threads must not call Tkinter APIs like Entry.get()).
        Polling now runs as a chain of after() callbacks on the main event loop.
        """
        self._schedule_next_poll()

    def _schedule_next_poll(self) -> None:
        """Schedule the next poll tick. Called from the main thread."""
        self._polling_after_id = self.after(
            int(self.POLL_INTERVAL_SECONDS * 1000),
            self._polling_tick,
        )

    def _polling_tick(self) -> None:
        """A single poll tick — runs on the main thread. Safe to call Tkinter APIs."""
        try:
            self._check_for_changes()
        except Exception as exc:
            self.log_queue.put(
                f"[WARN] Polling error: {type(exc).__name__}: {exc}"
            )
        self._schedule_next_poll()

    def _check_for_changes(self) -> None:
        patches_str = self.patch_dir_entry.get().strip()
        if not patches_str:
            return
        patches_path = Path(patches_str)
        if not patches_path.is_dir():
            # [POLL FIX] Force full diff next poll if folder recovers
            if self._last_known_state:
                self.log_queue.put(
                    f"[WARN] Patch folder not accessible: {patches_path}"
                )
                self._last_known_state = set()
            return

        current_state: set[tuple[str, float]] = set()
        try:
            for f in patches_path.glob("*.json"):
                if f.is_file():
                    try:
                        current_state.add((f.name, f.stat().st_mtime))
                    except OSError:
                        pass
        except OSError as exc:
            self.log_queue.put(f"[WARN] Polling error: {exc}")
            self._last_known_state = set()
            return

        if current_state != self._last_known_state:
            self._last_change_time = time.time()
            self._last_known_state = current_state
            self.after(
                int(self._debounce_seconds * 1000),
                self._scheduled_refresh
            )

    def _scheduled_refresh(self) -> None:
        elapsed = time.time() - self._last_change_time
        if elapsed < self._debounce_seconds:
            # [POLL FIX] Reschedule instead of dropping - prevents missing final refresh
            remaining_ms = int((self._debounce_seconds - elapsed) * 1000) + 50
            self.after(remaining_ms, self._scheduled_refresh)
            return
        self._auto_refresh()

    def _auto_refresh(self) -> None:
        patches_str = self.patch_dir_entry.get().strip()
        if not patches_str:
            return
        patches_path = Path(patches_str)
        if not patches_path.is_dir():
            return

        old_files = {f.name for f in self.patch_files}
        selection = self.patch_tree.selection()
        selected_file_name = None
        if selection:
            try:
                selected_idx = self.patch_tree.index(selection[0])
            except tk.TclError:
                selected_idx = -1
            if 0 <= selected_idx < len(self.patch_files):
                selected_file_name = self.patch_files[selected_idx].name

        try:
            current_files_sorted = sorted(
                patches_path.glob("*.json"),
                key=_patch_sort_key,
                reverse=True,
            )
        except OSError:
            return

        current_file_names = {f.name for f in current_files_sorted}
        added = current_file_names - old_files
        removed = old_files - current_file_names

        target_selection = None
        if added:
            for f in current_files_sorted:
                if f.name in added:
                    target_selection = f.name
                    break
        else:
            if selected_file_name and selected_file_name in current_file_names:
                target_selection = selected_file_name

        self.scan_patches(patches_path, restore_selection=target_selection)

        if added or removed:
            changes = []
            if added:
                changes.append(f"added {len(added)}")
            if removed:
                changes.append(f"removed {len(removed)}")
            self.log_queue.put(
                f"[INFO] Auto-refreshed patches: {', '.join(changes)}. "
                f"Total: {len(self.patch_files)} file(s)."
            )

    def _on_close(self) -> None:
        # [M2 FIX] Cancel pending polling after() callback
        if self._polling_after_id is not None:
            try:
                self.after_cancel(self._polling_after_id)
            except Exception:
                pass
            self._polling_after_id = None

        # [M1 FIX] Wait for worker thread before destroy.
        # Avoid killing the worker mid-patch when user closes the app.
        if self.worker and self.worker.is_alive():
            self.log_queue.put(
                "[WARN] Patch is running, waiting for completion before close (max 10s)..."
            )
            self.worker.join(timeout=10.0)
            if self.worker.is_alive():
                self.log_queue.put(
                    "[WARN] Worker did not finish within 10s, force closing. "
                    "Some files may not be fully written."
                )

        self.winfo_toplevel().destroy()

    def browse_project(self) -> None:
        path = filedialog.askdirectory(title="Select Project Directory")
        if path:
            self.project_entry.delete(0, "end")
            self.project_entry.insert(0, path)
            # [AUTO-FILL v2] Patches = <project>/Patches (auto-create if missing)
            project_path = Path(path)
            patches_path = project_path / "Patches"
            if not patches_path.is_dir():
                try:
                    patches_path.mkdir(parents=True, exist_ok=True)
                    self.log_queue.put(
                        f"[INFO] Created Patches folder: {patches_path}"
                    )
                except OSError as exc:
                    self.log_queue.put(
                        f"[WARN] Cannot create Patches folder: {exc}. "
                        f"Falling back to project root."
                    )
                    patches_path = project_path
            self.patch_dir_entry.delete(0, "end")
            self.patch_dir_entry.insert(0, str(patches_path))
            self._last_patch_dir = patches_path
            self._last_known_state = set()
            if patches_path.is_dir():
                self.scan_patches(patches_path)
            self._save_current_session()

    def browse_patch_dir(self) -> None:
        initial_dir: Path | None = None
        if self._last_patch_dir and self._last_patch_dir.exists():
            initial_dir = self._last_patch_dir
        else:
            project_str = self.project_entry.get().strip()
            if project_str and Path(project_str).exists():
                initial_dir = Path(project_str)
            else:
                initial_dir = Path.cwd()

        path = filedialog.askdirectory(
            title="Select Patches Directory",
            initialdir=str(initial_dir)
        )
        if path:
            parent_dir = Path(path)
            self.patch_dir_entry.delete(0, "end")
            self.patch_dir_entry.insert(0, str(parent_dir))
            self._last_patch_dir = parent_dir
            self._last_known_state = set()
            self.scan_patches(parent_dir)
            self._save_current_session()

    def _enforce_column_layout(self) -> None:
        """PRIORITY: Status fixed width first. Filename takes remaining. Idempotent."""
        self._pending_enforce_id = None
        tree_width = self.patch_tree.winfo_width()
        if tree_width <= 1:
            return

        status_fixed = getattr(self, "_status_fixed_width", 150)
        BUFFER = 20
        FILENAME_MIN = 150

        # 1. STATUS: force back to fixed width (user cannot change it)
        self.patch_tree.column("status", width=status_fixed, minwidth=status_fixed, stretch=False)

        # 2. FILENAME: fill ALL remaining space
        max_filename = max(FILENAME_MIN, tree_width - status_fixed - BUFFER)
        self.patch_tree.column("filename", width=max_filename, minwidth=FILENAME_MIN, stretch=True)

    def _on_f5_pressed(self, event: tk.Event[tk.Misc]) -> None:
        """Force immediate patch list refresh (F5 hotkey)."""
        self._auto_refresh()

    def _on_tree_configure(self, event: tk.Event[tk.Misc]) -> None:
        """Widget resize (window drag/maximize) — debounced enforcement."""
        if self._pending_enforce_id is not None:
            try:
                self.after_cancel(self._pending_enforce_id)
            except Exception:
                pass
        self._pending_enforce_id = self.after(20, self._enforce_column_layout)

    def _on_tree_release(self, event: tk.Event[tk.Misc]) -> None:
        """Mouse release (user may have dragged column divider) — debounced enforcement."""
        if self._pending_enforce_id is not None:
            try:
                self.after_cancel(self._pending_enforce_id)
            except Exception:
                pass
        self._pending_enforce_id = self.after(20, self._enforce_column_layout)

    def _apply_column_widths(self) -> None:
        """Fit columns to current tree width. Status fixed right, filename caps to remaining. No window resize."""
        import tkinter.font as tkfont
        heading_font = tkfont.Font(font=("Tahoma", 9))
        row_font = tkfont.Font(font=("Consolas", 8))

        # Measure status heading + longest content
        status_heading_w = heading_font.measure("Status")
        status_content_w = 0
        for item in self.patch_tree.get_children():
            vals = self.patch_tree.item(item, "values")
            if len(vals) >= 2:
                status_content_w = max(status_content_w, row_font.measure(str(vals[1])))

        # Status: FIXED right (never shrinks, always visible)
        STATUS_MIN = 90
        STATUS_PAD = 15
        status_width = max(STATUS_MIN, status_heading_w, status_content_w) + STATUS_PAD
        self._status_fixed_width = status_width
        self._computed_status_min = status_width

        # Filename: fit within current tree width (window stays fixed 430)
        tree_width = self.patch_tree.winfo_width()
        if tree_width <= 1:
            tree_width = 400
        FILENAME_MIN = 150
        BUFFER = 20
        filename_width = max(FILENAME_MIN, tree_width - status_width - BUFFER)

        # Apply
        self.patch_tree.column("status", width=status_width, minwidth=status_width, stretch=False)
        self.patch_tree.column("filename", width=filename_width, minwidth=FILENAME_MIN, stretch=True)

    def _smart_adjust_columns(self) -> None:
        """Auto-resize. STATUS fixed right. FILENAME grows with content. Window auto-expands if needed."""
        import tkinter.font as tkfont
        heading_font = tkfont.Font(font=("Tahoma", 9))
        row_font = tkfont.Font(font=("Consolas", 8))

        # STEP 1 - measure heading + longest content
        filename_heading_w = heading_font.measure("Patch File")
        status_heading_w = heading_font.measure("Status")
        filename_content_w = filename_heading_w
        status_content_w = 0
        for item in self.patch_tree.get_children():
            vals = self.patch_tree.item(item, "values")
            if len(vals) >= 1:
                filename_content_w = max(filename_content_w, row_font.measure(str(vals[0])))
            if len(vals) >= 2:
                status_content_w = max(status_content_w, row_font.measure(str(vals[1])))

        # STEP 2 - status width (fixed, right side)
        STATUS_MIN = 130
        STATUS_PAD = 15
        status_width = max(STATUS_MIN, status_heading_w, status_content_w) + STATUS_PAD
        self._status_fixed_width = status_width
        self._computed_status_min = status_width

        # STEP 3 - filename width (grows with content, min 200)
        FILENAME_MIN = 200
        FILENAME_PAD = 20
        filename_width = max(FILENAME_MIN, filename_content_w + FILENAME_PAD)

        # STEP 4 - auto-expand window if total columns overflow
        needed_tree_w = filename_width + status_width + 20
        needed_window_w = needed_tree_w + 60
        try:
            top = self.winfo_toplevel()
            current_w = top.winfo_width()
            current_h = top.winfo_height()
            screen_w = top.winfo_screenwidth()
            max_allowed = int(screen_w * 0.9)
            if needed_window_w > current_w and needed_window_w <= max_allowed:
                top.geometry(f"{needed_window_w}x{current_h}")
        except Exception:
            pass

        # STEP 5 - apply columns
        self.patch_tree.column("status", width=status_width, minwidth=status_width, stretch=False)
        self.patch_tree.column("filename", width=filename_width, minwidth=FILENAME_MIN, stretch=True)

    def _adjust_patch_columns(self) -> None:
        """Auto-resize columns: STATUS width first (locked), FILENAME fills remaining."""
        import tkinter.font as tkfont
        heading_font = tkfont.Font(font=("Tahoma", 9))
        row_font = tkfont.Font(font=("Consolas", 8))

        # STEP 1 (HEADING): measure Status heading width
        status_heading_w = heading_font.measure("Status")

        # STEP 2 (CONTENT): measure longest status content
        status_content_w = 0
        for item in self.patch_tree.get_children():
            vals = self.patch_tree.item(item, "values")
            if len(vals) >= 2:
                status_content_w = max(status_content_w, row_font.measure(str(vals[1])))

        # STEP 3 (STATUS WIDTH): combine, lock
        STATUS_MIN = 150
        STATUS_PAD = 30
        status_width = max(STATUS_MIN, status_heading_w, status_content_w) + STATUS_PAD
        self._status_fixed_width = status_width
        self._computed_status_min = status_width

        # STEP 4 (FILENAME WIDTH): fill remaining
        tree_width = self.patch_tree.winfo_width()
        if tree_width <= 1:
            tree_width = 600
        FILENAME_MIN = 100
        BUFFER = 20
        filename_width = max(FILENAME_MIN, tree_width - status_width - BUFFER)

        # STEP 5 (APPLY)
        self.patch_tree.column("status", width=status_width, minwidth=status_width, stretch=False)
        self.patch_tree.column("filename", width=filename_width, minwidth=FILENAME_MIN, stretch=True)

    def _auto_resize_patch_columns(self) -> None:
        """Auto-resize. PRIORITY: Status column width first, then filename fills remaining space."""
        import tkinter.font as tkfont
        heading_font = tkfont.Font(font=("Tahoma", 9))
        row_font = tkfont.Font(font=("Consolas", 8))

        # STEP 1 — HEADING: measure "Status" heading width (Tahoma 9, normal weight)
        status_heading_w = heading_font.measure("Status")

        # STEP 2 — CONTENT: measure longest status content (Consolas 8)
        status_content_w = 0
        for item in self.patch_tree.get_children():
            vals = self.patch_tree.item(item, "values")
            if len(vals) >= 2:
                status_content_w = max(status_content_w, row_font.measure(str(vals[1])))

        # STEP 3 — STATUS WIDTH (locked): max(heading, content) + padding, floor 150
        # Both "Status" heading AND longest content (e.g. "Patched (file modified)") fully visible
        STATUS_MIN = 150
        STATUS_PAD = 30
        status_width = max(STATUS_MIN, status_heading_w, status_content_w) + STATUS_PAD
        self._status_fixed_width = status_width
        self._computed_status_min = status_width

        # STEP 4 — FILENAME WIDTH: fills ALL remaining space (status takes priority)
        tree_width = self.patch_tree.winfo_width()
        if tree_width <= 1:
            tree_width = 600
        FILENAME_MIN = 100
        BUFFER = 20
        filename_width = max(FILENAME_MIN, tree_width - status_width - BUFFER)

        # STEP 5 — APPLY: status FIRST (fixed, cannot shrink/grow), filename SECOND (stretch)
        self.patch_tree.column("status", width=status_width, minwidth=status_width, stretch=False)
        self.patch_tree.column("filename", width=filename_width, minwidth=FILENAME_MIN, stretch=True)

    def scan_patches(
        self,
        directory: Path,
        restore_selection: str | None = None
    ) -> None:
        """[GAP-7 FIX v2] Display patch list in 2 columns: filename | status.

        Uses ttk.Treeview for automatic column alignment (no manual padding).
        Real-time state (Patching...) takes priority over persisted status.
        """
        for item in self.patch_tree.get_children():
            self.patch_tree.delete(item)
        self.patch_files.clear()

        if not directory.is_dir():
            return

        project_str = self.project_entry.get().strip()
        if project_str:
            project_path = Path(project_str)
            if project_path.is_dir():
                history_path = get_history_path(project_path)
                self._patch_history = PatchHistory.load(history_path)
                self._patch_status_cache.clear()

        json_files = sorted(
            directory.glob("*.json"),
            key=_patch_sort_key,
            reverse=True,
        )
        self.patch_files = list(json_files)

        if not json_files:
            self.patch_tree.insert("", "end", values=("(No .json files found)", ""))
        else:
            for f in json_files:
                if f.name == self._patch_in_progress:
                    status_text = STATUS_DISPLAY["in_progress"]
                else:
                    status, detail = get_patch_status(f, self._patch_history)
                    self._patch_status_cache[f.name] = (status, detail)
                    status_text = STATUS_DISPLAY.get(
                        status, STATUS_DISPLAY["unknown"]
                    )
                self.patch_tree.insert("", "end", values=(f.name, status_text))

        self._apply_column_widths()
        restored_item = None
        if restore_selection:
            for item in self.patch_tree.get_children():
                vals = self.patch_tree.item(item, "values")
                if vals and vals[0] == restore_selection:
                    restored_item = item
                    break

        children = self.patch_tree.get_children()
        if restored_item is not None:
            self.patch_tree.selection_set(restored_item)
            self.patch_tree.focus(restored_item)
        elif children:
            self.patch_tree.selection_set(children[0])
            self.patch_tree.focus(children[0])

    def _on_execute_hover_enter(self, event: tk.Event) -> None:
        """[HOVER] Change button background when mouse enters."""
        if self.btn_execute.cget("state") == "normal":
            self.btn_execute.configure(bg="#C8C8C8")

    def _on_execute_hover_leave(self, event: tk.Event) -> None:
        """[HOVER] Restore button background when mouse leaves."""
        self.btn_execute.configure(bg="#E0E0E0")

    def _on_snapshot_hover_enter(self, event: tk.Event) -> None:
        """[HOVER] Change Snapshot button background when mouse enters."""
        if self.btn_snapshot.cget("state") == "normal":
            self.btn_snapshot.configure(bg="#C8C8C8")

    def _on_snapshot_hover_leave(self, event: tk.Event) -> None:
        """[HOVER] Restore Snapshot button background when mouse leaves."""
        self.btn_snapshot.configure(bg="#E0E0E0")

    def snapshot_source(self) -> None:
        """[SNAPSHOT] Generate source_tree.md + source_content.<ext> for AI handoff."""
        project_str = self.project_entry.get().strip()
        if not project_str:
            self._show_dialog(
                "Missing Input",
                "Please select a Project Directory first.",
                kind="warning",
            )
            return

        project_path = Path(project_str)
        if not project_path.is_dir():
            self._show_dialog(
                "Invalid Path",
                f"Project directory does not exist:\n{project_path}",
                kind="error",
            )
            return

        try:
            from ...discovery import load_project_from_path
            project = load_project_from_path(project_path)
        except Exception as exc:
            self._show_dialog(
                "Load Project Failed",
                f"Cannot load project: {type(exc).__name__}: {exc}",
                kind="error",
            )
            return

        self.btn_snapshot.configure(state="disabled", relief="sunken")
        self.log_queue.put(
            f"[INFO] Generating source snapshot for {project_path}..."
        )
        try:
            result = generate_snapshot(project=project)
        except Exception as exc:
            self.btn_snapshot.configure(state="normal", relief="raised")
            self._show_dialog(
                "Snapshot Failed",
                f"Unexpected error: {type(exc).__name__}: {exc}",
                kind="error",
            )
            return

        self.btn_snapshot.configure(state="normal", relief="raised")

        if result.success:
            self.log_queue.put(f"[INFO] Tree file: {result.tree_path}")
            self.log_queue.put(f"[INFO] Content file: {result.content_path}")
            self.log_queue.put(f"[INFO] Format: .{result.content_format}")
            self.log_queue.put(
                f"[INFO] Files: {result.included_files}/{result.total_files} "
                f"included, {result.skipped_files} skipped"
            )
            self.log_queue.put(
                f"[INFO] Bytes: {result.included_bytes}/{result.total_bytes} included"
            )
            for w in result.warnings:
                self.log_queue.put(f"[WARN] {w}")
            msg = (
                f"Snapshot generated successfully.\n\n"
                f"Tree: {result.tree_path.name}\n"
                f"Content: {result.content_path.name}\n"
                f"Format: .{result.content_format}\n"
                f"Included: {result.included_files}/{result.total_files} files\n"
                f"Skipped: {result.skipped_files} files\n"
                f"Size: {result.included_bytes} bytes"
            )
            if result.warnings:
                msg += f"\n\nWarnings: {len(result.warnings)} (see terminal)"
            self._show_dialog(
                title="Snapshot Complete",
                message=msg,
                kind="success",
                auto_close_seconds=6,
            )
        else:
            self._show_dialog(
                "Snapshot Failed",
                f"Error: {result.error}",
                kind="error",
            )


    def execute_selected(self) -> None:
        project_str = self.project_entry.get().strip()
        if not project_str:
            self._show_dialog(
                "Missing Input",
                "Please select a Project Directory first.",
                kind="warning",
            )
            return

        project_path = Path(project_str)
        if not project_path.is_dir():
            self._show_dialog(
                "Invalid Path",
                f"Project directory does not exist:\n{project_path}",
                kind="error",
            )
            return

        if not self.patch_files:
            self._show_dialog(
                "Missing Input",
                "No patch files available.\nPlease select a Patches Directory.",
                kind="warning",
            )
            return

        selection = self.patch_tree.selection()
        if not selection:
            self._show_dialog(
                "No Selection",
                "Please click to select a patch file from the list before executing.",
                kind="warning",
            )
            return

        try:
            selected_index = self.patch_tree.index(selection[0])
        except tk.TclError:
            return
        if selected_index < 0 or selected_index >= len(self.patch_files):
            return
        selected_file = self.patch_files[selected_index]

        if self.worker and self.worker.is_alive():
            self._show_dialog(
                "Task In Progress",
                "A task is currently running.\nPlease wait for it to complete.",
                kind="info",
            )
            return

        status_info = self._patch_status_cache.get(selected_file.name)
        if status_info:
            status, detail = status_info
            if status == "applied_same":
                confirm = messagebox.askyesno(
                    "Patch Already Applied",
                    f"File '{selected_file.name}' has already been applied.\n\n"
                    f"{detail}\n\n"
                    f"Re-apply this patch?",
                )
                if not confirm:
                    return
            elif status == "applied_modified":
                confirm = messagebox.askyesno(
                    "WARNING: Patch File Modified",
                    f"File '{selected_file.name}' was previously applied,\n"
                    f"but the file has been MODIFIED since then.\n\n"
                    f"{detail}\n\n"
                    f"Re-applying a modified patch may cause errors.\n"
                    f"Are you sure you want to continue?",
                )
                if not confirm:
                    return

        self.log_console.clear()
        self.btn_execute.configure(state="disabled", relief="sunken")

        # [GAP-7 FIX] Persist selection name — Treeview rebuild loses selection
        self._current_selection_name = selected_file.name

        # [GAP-7 FIX] Set real-time state → refresh tree to show "Patching..."
        self._patch_in_progress = selected_file.name
        patches_str = self.patch_dir_entry.get().strip()
        if patches_str and Path(patches_str).is_dir():
            self.scan_patches(Path(patches_str))

        task = WorkerTask(
            task_type="batch_execute",
            project_path=project_path,
            patch_paths=[selected_file],
        )

        # [AUDIT-005 FIX] Thread-safe callback: schedule on main Tk thread
        def _thread_safe_callback(
            success: bool, message: str, failed_file: str | None
        ) -> None:
            self.after(
                0, lambda: self.on_task_complete(success, message, failed_file)
            )

        self.worker = PatchWorker(task, self.log_queue, _thread_safe_callback)
        self.worker.start()

    def on_task_complete(
        self,
        success: bool,
        message: str,
        failed_file: str | None
    ) -> None:
        # [GAP-7 FIX] Reset real-time state before refresh
        self._patch_in_progress = None
        self.btn_execute.configure(state="normal", relief="raised")

        if success:
            self._record_and_refresh()

            display_message = f"Patch applied successfully.\n\n{message}"
            self._show_dialog(
                title="Patch Completed",
                message=display_message,
                kind="success",
                auto_close_seconds=5,
            )
        else:
            # [GAP-7 FIX] Record failure so status displays "Patch failed"
            self._record_failure(failed_file)

            error_msg = f"File: {failed_file}\n\n{message}"
            self._show_dialog(
                title="Execution Aborted",
                message=error_msg,
                kind="error",
            )

    def _record_and_refresh(self) -> None:
        patches_str = self.patch_dir_entry.get().strip()
        project_str = self.project_entry.get().strip()
        if not patches_str or not project_str:
            return

        project_path = Path(project_str)
        patches_path = Path(patches_str)
        if not project_path.is_dir() or not patches_path.is_dir():
            return

        selected_file_name = self._current_selection_name
        if not selected_file_name:
            return
        selected_file = next(
            (f for f in self.patch_files if f.name == selected_file_name),
            None,
        )
        if selected_file is None:
            return

        try:
            history_path = get_history_path(project_path)
            history = PatchHistory.load(history_path)
            from ...schema import load_patch
            manifest = load_patch(selected_file)
            sha256 = compute_file_sha256(selected_file)

            # [H3 FIX] Snapshot progress_report to preserve audit trail
            progress_snapshot = None
            if manifest.progress_report is not None:
                try:
                    progress_snapshot = asdict(manifest.progress_report)
                except Exception as exc:
                    self.log_queue.put(
                        f"[WARN] Cannot serialize progress_report: {exc}"
                    )

            history.record_success(
                filename=selected_file.name,
                patch_id=manifest.patch_id,
                sha256=sha256,
                progress_report_snapshot=progress_snapshot,
            )
            history.save(history_path)
            self.log_queue.put(
                f"[INFO] Recorded patch history: {selected_file.name}"
            )
        except Exception as exc:
            self.log_queue.put(
                f"[WARN] Failed to record patch history: {exc}"
            )

        self.scan_patches(patches_path)

    def undo_selected(self) -> None:
        """Undo the currently selected applied patch (restore files from backup)."""
        if self.worker and self.worker.is_alive():
            self._show_dialog(
                "Task In Progress",
                "Cannot undo while a patch is running.",
                kind="info",
            )
            return

        project_str = self.project_entry.get().strip()
        if not project_str:
            self._show_dialog(
                "Missing Input",
                "Please select a Project Directory first.",
                kind="warning",
            )
            return

        project_path = Path(project_str)
        if not project_path.is_dir():
            self._show_dialog(
                "Invalid Path",
                f"Project directory does not exist:\n{project_path}",
                kind="error",
            )
            return

        if not self.patch_files:
            self._show_dialog(
                "Missing Input",
                "No patch files available.",
                kind="warning",
            )
            return

        selection = self.patch_tree.selection()
        if not selection:
            self._show_dialog(
                "No Selection",
                "Please select a patch file to undo.",
                kind="warning",
            )
            return

        try:
            selected_index = self.patch_tree.index(selection[0])
        except tk.TclError:
            return
        if selected_index < 0 or selected_index >= len(self.patch_files):
            return
        selected_file = self.patch_files[selected_index]

        status_info = self._patch_status_cache.get(selected_file.name)
        if not status_info:
            self._show_dialog(
                "Cannot Undo",
                f"Patch '{selected_file.name}' has no applied record.",
                kind="warning",
            )
            return
        status, _detail = status_info
        if status not in ("applied_same", "applied_modified"):
            self._show_dialog(
                "Cannot Undo",
                f"Patch status is '{status}'. Only applied patches can be undone.",
                kind="warning",
            )
            return

        try:
            from ...discovery import load_project_from_path
            project = load_project_from_path(project_path)
            from ...schema import load_patch
            patch_manifest = load_patch(selected_file)
            patch_id = patch_manifest.patch_id
        except Exception as exc:
            self._show_dialog(
                "Load Failed",
                f"Cannot load patch: {type(exc).__name__}: {exc}",
                kind="error",
            )
            return

        confirm = messagebox.askyesno(
            "Confirm Undo",
            f"Undo patch: {patch_id}\n\n"
            f"Files changed by this patch will be restored from backup.\n"
            f"Files created by the patch will be deleted.\n\n"
            f"Continue?",
        )
        if not confirm:
            return

        self.log_console.clear()
        self.log_queue.put(f"[INFO] Undoing patch: {patch_id}...")
        self.btn_undo.configure(state="disabled", relief="sunken")
        self.btn_execute.configure(state="disabled")

        try:
            result = undo_patch(project, patch_id)
        except Exception as exc:
            result = None
            self.log_queue.put(f"[ERROR] Unexpected: {type(exc).__name__}: {exc}")

        self.btn_execute.configure(state="normal")
        self._update_undo_button_state()

        if result is None or not result.success:
            msg = result.message if result else "Unexpected error"
            if result and result.modified_files:
                msg += "\n\nModified files (refused):\n- " + "\n- ".join(result.modified_files)
            self.log_queue.put(f"[FAILED] {msg}")
            self._show_dialog("Undo Failed", msg, kind="error")
            return

        self.log_queue.put(f"[SUCCESS] {result.message}")
        if result.restored_files:
            self.log_queue.put(f"[INFO] Restored: {', '.join(result.restored_files)}")
        if result.deleted_files:
            self.log_queue.put(f"[INFO] Deleted: {', '.join(result.deleted_files)}")

        patches_str = self.patch_dir_entry.get().strip()
        if patches_str and Path(patches_str).is_dir():
            self.scan_patches(Path(patches_str))

        self._show_dialog(
            title="Undo Complete",
            message=(
                f"Patch {patch_id} undone.\n\n"
                f"Restored: {len(result.restored_files)} file(s)\n"
                f"Deleted: {len(result.deleted_files)} file(s)"
            ),
            kind="success",
            auto_close_seconds=5,
        )

    def _update_undo_button_state(self) -> None:
        """Enable Undo button only when selected patch is applied."""
        # Always reset relief - undo_selected sets "sunken" during operation
        self.btn_undo.configure(relief="raised")
        selection = self.patch_tree.selection()
        if not selection:
            self.btn_undo.configure(state="disabled")
            return
        try:
            idx = self.patch_tree.index(selection[0])
        except tk.TclError:
            self.btn_undo.configure(state="disabled")
            return
        if idx < 0 or idx >= len(self.patch_files):
            self.btn_undo.configure(state="disabled")
            return
        patch_file = self.patch_files[idx]
        status_info = self._patch_status_cache.get(patch_file.name)
        if not status_info:
            self.btn_undo.configure(state="disabled")
            return
        status, _ = status_info
        if status in ("applied_same", "applied_modified"):
            self.btn_undo.configure(state="normal")
        else:
            self.btn_undo.configure(state="disabled")

    def _on_tree_select(self, event: tk.Event) -> None:
        self._update_undo_button_state()

    def _on_undo_hover_enter(self, event: tk.Event) -> None:
        if self.btn_undo.cget("state") == "normal":
            self.btn_undo.configure(bg="#C8C8C8")

    def _on_undo_hover_leave(self, event: tk.Event) -> None:
        if self.btn_undo.cget("state") == "normal":
            self.btn_undo.configure(bg="#E0E0E0")

    def _record_failure(self, failed_file: str | None) -> None:
        """[GAP-7 FIX] Record a failed patch attempt + refresh tree.

        Important: must record even when the patch is invalid (schema error).
        Previously called load_patch() which fails → no record → GUI shows
        Not Patched instead of Patch failed. Fix via fallback: use filename
        as patch_id when the patch cannot be loaded.

        Best-effort: if recording fails entirely, only log warning and still
        refresh the tree (status remains unchanged).
        """
        patches_str = self.patch_dir_entry.get().strip()
        project_str = self.project_entry.get().strip()

        if failed_file and patches_str and project_str:
            project_path = Path(project_str)
            patches_path = Path(patches_str)
            if project_path.is_dir() and patches_path.is_dir():
                patch_file = patches_path / failed_file
                if patch_file.exists():
                    # Fallback patch_id = filename without .json
                    patch_id = failed_file.rsplit(".", 1)[0]
                    sha256 = ""

                    # sha256 always computable (just reads file, no JSON parse)
                    try:
                        sha256 = compute_file_sha256(patch_file)
                    except Exception as exc:
                        self.log_queue.put(
                            f"[WARN] Cannot compute sha256 for {failed_file}: {exc}"
                        )

                    # Try to load manifest for a "nicer" patch_id — optional.
                    # If patch is invalid (schema error), load_patch() raises →
                    # fallback uses filename as patch_id.
                    try:
                        from ...schema import load_patch
                        manifest = load_patch(patch_file)
                        patch_id = manifest.patch_id
                    except Exception:
                        # Patch invalid — use fallback patch_id from filename
                        pass

                    # Record failure — must succeed regardless of patch validity
                    try:
                        history_path = get_history_path(project_path)
                        history = PatchHistory.load(history_path)
                        history.record_failure(
                            filename=failed_file,
                            patch_id=patch_id,
                            sha256=sha256,
                        )
                        history.save(history_path)
                        self.log_queue.put(
                            f"[INFO] Recorded patch failure: {failed_file} "
                            f"(patch_id={patch_id})"
                        )
                    except Exception as exc:
                        self.log_queue.put(
                            f"[WARN] Failed to save patch failure to history: {exc}"
                        )

        # Refresh tree — real-time state reset, now shows status from history
        if patches_str:
            patches_path = Path(patches_str)
            if patches_path.is_dir():
                self.scan_patches(patches_path)