from __future__ import annotations

import logging
import queue
from typing import Any

from ..context import ExecutionContext, SchemaError
from ..discovery import load_project_from_path
from ..engine import apply_patch_to_project
from ..schema import load_patch


class QueueLogHandler(logging.Handler):
    """Custom logging handler to push log records into queue.Queue."""

    def __init__(self, log_queue: queue.Queue[str]):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            self.handleError(record)


def _format_schema_error(exc: SchemaError) -> str:
    """
    Format SchemaError into user-friendly message with actionable guidance.
    Pattern matching đã được cập nhật để match thông báo tiếng Anh mới từ schema.py.
    """
    base_msg = str(exc)
    guidance = ""
    lower_msg = base_msg.lower()
    
    if "utf-8" in lower_msg or "unicode" in lower_msg or "decode" in lower_msg:
        guidance = (
            "\n-> Hint: Open file with Notepad++, select menu Encoding -> "
            "Convert to UTF-8 (no BOM), then save."
        )
    elif "invalid json" in lower_msg or "json parse error" in lower_msg:
        guidance = (
            "\n-> Hint: Check commas, quotes, and braces in the JSON file. "
            "Use an online JSON Validator to locate the exact position."
        )
    elif "path traversal" in lower_msg or "must not contain '..'" in lower_msg:
        guidance = (
            "\n-> Hint: The 'file' field must not contain '..' to prevent "
            "Path Traversal attacks. Please fix the path to be relative within the project."
        )
    elif "patch_id" in lower_msg:
        guidance = (
            "\n-> Hint: 'patch_id' is required and must be a non-empty string "
            "(letters, numbers, underscore, hyphen only)."
        )
    elif "'patches' must be" in lower_msg or "non-empty list" in lower_msg:
        guidance = (
            "\n-> Hint: Patch file must contain at least one item in the 'patches' "
            "array (each item requires 'file' and 'operations' fields)."
        )
    elif "schema_version" in lower_msg:
        guidance = (
            "\n-> Hint: 'schema_version' is required and must be '1.0' or '2.0'."
        )
    elif "operation" in lower_msg and "type" in lower_msg:
        guidance = (
            "\n-> Hint: Each operation must have a valid 'type' field "
            "(replace, insert_after, insert_before, delete, replace_regex, write_content)."
        )
    elif "regex" in lower_msg:
        guidance = (
            "\n-> Hint: Check the regex pattern syntax. Supported flags: i, m, s, x."
        )
    elif "occurrence" in lower_msg:
        guidance = (
            "\n-> Hint: 'occurrence' must be -1 (all) or a positive integer."
        )
    elif "required" in lower_msg or "must be" in lower_msg:
        guidance = (
            "\n-> Hint: Patch file does not comply with the standard JSON Schema. "
            "Please refer to PATCH_AUTHOR_GUIDE.md for the correct structure."
        )
    else:
        guidance = (
            "\n-> Hint: Patch file does not comply with the standard JSON Schema. "
            "Please contact the patch release team for support."
        )
    
    return base_msg + guidance


def run_patch_batch_task(
    task: Any,
    log_queue: queue.Queue[str]
) -> tuple[bool, str, str | None]:
    """
    Execute batch pipeline: Validate -> Dry-run -> Apply for each file.
    Returns (success, summary_message, failed_file_name_or_None).
    Fail-fast mechanism: stops immediately on first error.
    """
    queue_handler = QueueLogHandler(log_queue)
    queue_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%H:%M:%S"
        )
    )

    logger = logging.getLogger("apply_patch")
    logger.addHandler(queue_handler)
    logger.setLevel(logging.INFO)

    failed_file_name = None
    
    try:
        log_queue.put(f"[INFO] Loading project: {task.project_path}")
        project = load_project_from_path(task.project_path)

        total_files = len(task.patch_paths)
        log_queue.put(
            f"[INFO] Found {total_files} patch file(s). Starting Batch Pipeline..."
        )

        for idx, patch_path in enumerate(task.patch_paths, start=1):
            file_name = patch_path.name
            log_queue.put(f"[BATCH] ({idx}/{total_files}) Processing: {file_name}")
            failed_file_name = file_name
            
            # 1. Read and Validate (bao gồm JSON Schema Validation)
            try:
                manifest = load_patch(patch_path)
                log_queue.put(f"[INFO] Validation passed: {file_name}")
            except SchemaError as exc:
                detailed_msg = _format_schema_error(exc)
                log_queue.put("[FAILED] JSON Schema validation error:")
                for line in detailed_msg.split("\n"):
                    log_queue.put(f"         {line}")
                return False, detailed_msg, file_name
            except Exception as exc:
                msg = f"Failed to read file: {type(exc).__name__}: {exc}"
                log_queue.put(f"[FAILED] {msg}")
                return False, msg, file_name

            # 2. Dry-run
            context_dry = ExecutionContext(
                project=project,
                dry_run=True,
                json_output=False,
                patch_path=patch_path,
            )
            report_dry = apply_patch_to_project(context_dry, manifest)
            if not report_dry.success:
                msg = f"Dry-run failed: {report_dry.message}"
                log_queue.put(f"[FAILED] {msg}")
                
                for f in report_dry.files:
                    if f.status == "failed":
                        log_queue.put(f"[FILE ERROR] {f.file}: {f.message}")
                        if f.verify_errors:
                            for err in f.verify_errors:
                                log_queue.put(f"[VERIFY ERROR] {err}")
                                
                return False, msg, file_name
            
            log_queue.put(f"[INFO] Dry-run passed: {file_name}")

            # 3. Apply thật
            context_apply = ExecutionContext(
                project=project,
                dry_run=False,
                json_output=False,
                patch_path=patch_path,
            )
            report_apply = apply_patch_to_project(context_apply, manifest)
            if not report_apply.success:
                msg = f"Apply failed: {report_apply.message}"
                log_queue.put(f"[FAILED] {msg}")
                
                for f in report_apply.files:
                    if f.status == "failed":
                        log_queue.put(f"[FILE ERROR] {f.file}: {f.message}")
                        if f.verify_errors:
                            for err in f.verify_errors:
                                log_queue.put(f"[VERIFY ERROR] {err}")
                                
                return False, msg, file_name

            log_queue.put(f"[SUCCESS] Apply succeeded: {file_name}")

        log_queue.put(
            f"[SUCCESS] COMPLETED. Successfully applied {total_files} patch file(s)."
        )
        return True, "Success.", None

    except Exception as exc:
        msg = f"Unexpected error: {type(exc).__name__}: {exc}"
        log_queue.put(f"[ERROR] {msg}")
        return False, msg, failed_file_name
    finally:
        logger.removeHandler(queue_handler)