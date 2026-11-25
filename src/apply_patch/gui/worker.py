from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkerTask:
    """Mô tả một tác vụ batch cần thực thi."""
    task_type: str
    project_path: Path
    patch_paths: list[Path] = field(default_factory=list)


class PatchWorker(threading.Thread):
    """Luồng thực thi tác vụ patch và đẩy log qua queue."""

    def __init__(
        self,
        task: WorkerTask,
        log_queue: queue.Queue[str],
        result_callback: Callable[[bool, str, str | None], None],
    ):
        super().__init__(daemon=True)
        self.task = task
        self.log_queue = log_queue
        self.result_callback = result_callback

    def run(self) -> None:
        try:
            from .adapter import run_patch_batch_task
            success, message, failed_file = run_patch_batch_task(self.task, self.log_queue)
            self.result_callback(success, message, failed_file)
        except Exception as exc:
            self.log_queue.put(f"[CRITICAL ERROR] {type(exc).__name__}: {exc}")
            self.result_callback(False, str(exc), None)