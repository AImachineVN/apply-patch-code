from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import regex

from .backup import (
    create_backup,
    create_session_dir,
    rollback_backup_path,
    write_session_metadata,
)
from .context import (
    ApplyPatchError,
    BackupError,
    ExecutionContext,
    FilePatchResult,
    OperationError,
    OperationResult,
    PatchReport,
    VerificationError,
)
from .languages import resolve_language
from .safety import safe_join
from .schema import DirectoryPatch, PatchManifest
from .utils import write_text_atomic
from .verification import (
    read_text,
    verify_content,
    verify_file_markers,
)

log = logging.getLogger(__name__)

# Timeout cho phép tính regex (giây). Regex chạy quá thời gian này bị kill
# và trả OperationError thay vì treo app (ReDoS prevention).
_REGEX_TIMEOUT_SECONDS = 10.0


def _count_occurrences(content: str, needle: str) -> int:
    if not needle:
        return 0
    count = 0
    start = 0
    while True:
        index = content.find(needle, start)
        if index == -1:
            break
        count += 1
        start = index + 1
    return count


def _op_replace(content: str, op: dict[str, Any], file_name: str) -> tuple[str, str]:
    old_text = op["old_text"]
    new_text = op["new_text"]
    occurrence = int(op.get("occurrence", 1))
    total = _count_occurrences(content, old_text)

    if total == 0:
        raise OperationError(f"old_text not found in {file_name}")

    if occurrence == -1:
        new_content = content.replace(old_text, new_text)
        return new_content, f"replaced all ({total} occurrence(s))"

    if occurrence < 1:
        raise OperationError("'occurrence' must be -1 or a positive integer.")

    index = -1
    for _ in range(occurrence):
        index = content.find(old_text, index + 1)
        if index == -1:
            raise OperationError(
                f"occurrence={occurrence} is invalid. "
                f"Only {total} occurrence(s) found in {file_name}."
            )

    new_content = content[:index] + new_text + content[index + len(old_text):]
    return new_content, f"replaced occurrence {occurrence}/{total}"


def _op_insert_after(content: str, op: dict[str, Any], file_name: str) -> tuple[str, str]:
    anchor = op["anchor"]
    new_text = op["new_text"]

    index = content.find(anchor)
    if index == -1:
        raise OperationError(f"Anchor not found in {file_name}: {anchor[:120]}")

    if not new_text.endswith("\n"):
        new_text += "\n"

    line_end = content.find("\n", index)
    if line_end == -1:
        new_content = content + "\n" + new_text
        return new_content, "insert_after at end of file"

    insert_position = line_end + 1
    new_content = content[:insert_position] + new_text + content[insert_position:]
    return new_content, f"insert_after at line containing anchor (char position {index})"


def _op_insert_before(content: str, op: dict[str, Any], file_name: str) -> tuple[str, str]:
    anchor = op["anchor"]
    new_text = op["new_text"]

    index = content.find(anchor)
    if index == -1:
        raise OperationError(f"Anchor not found in {file_name}: {anchor[:120]}")

    if not new_text.endswith("\n"):
        new_text += "\n"

    line_start = content.rfind("\n", 0, index) + 1
    new_content = content[:line_start] + new_text + content[line_start:]
    return new_content, f"insert_before at line containing anchor (char position {index})"


def _op_delete(content: str, op: dict[str, Any], file_name: str) -> tuple[str, str]:
    old_text = op["old_text"]
    if old_text not in content:
        raise OperationError(f"old_text not found for deletion in {file_name}")

    new_content = content.replace(old_text, "")
    return new_content, "deleted"


def _op_replace_regex(content: str, op: dict[str, Any], file_name: str) -> tuple[str, str]:
    pattern = op["pattern"]
    replacement = op["replacement"]
    flags_str = str(op.get("flags", "")).strip()
    flags = 0

    if "i" in flags_str:
        flags |= regex.IGNORECASE
    if "m" in flags_str:
        flags |= regex.MULTILINE
    if "s" in flags_str:
        flags |= regex.DOTALL
    if "x" in flags_str:
        flags |= regex.VERBOSE

    try:
        compiled = regex.compile(pattern, flags=flags)
    except regex.error as exc:
        raise OperationError(f"Invalid regex in {file_name}: {exc}") from exc

    # Defense in Depth: regex.subn với timeout thực sự kill được computation
    # (khác với ThreadPoolExecutor future.result(timeout) — vẫn chờ worker kết thúc).
    # Ngăn ReDoS: pattern như (a+)+$ trên input dài sẽ bị timeout, không treo app.
    try:
        new_content, count = compiled.subn(
            replacement, content, timeout=_REGEX_TIMEOUT_SECONDS
        )
    except TimeoutError:
        raise OperationError(
            f"Regex operation timed out after {_REGEX_TIMEOUT_SECONDS}s in {file_name}. "
            f"Pattern may be too complex or vulnerable to ReDoS: {pattern[:120]}"
        )

    if count == 0:
        raise OperationError(f"Regex did not match in {file_name}: {pattern[:120]}")

    return new_content, f"replace_regex ({count} match(es))"


def _op_write_content(content: str, op: dict[str, Any], file_name: str) -> tuple[str, str]:
    new_content = op.get("content", "")
    return new_content, f"write_content ({len(new_content)} bytes)"


OPERATIONS = {
    "replace": _op_replace,
    "insert_after": _op_insert_after,
    "insert_before": _op_insert_before,
    "delete": _op_delete,
    "replace_regex": _op_replace_regex,
    "write_content": _op_write_content,
}


def apply_operations(
    content: str,
    operations: list[dict[str, Any]],
    file_name: str,
) -> tuple[str, list[OperationResult]]:
    results: list[OperationResult] = []

    for index, op in enumerate(operations, start=1):
        op_type = str(op.get("type", "")).strip()
        if op_type not in OPERATIONS:
            raise OperationError(
                f"Operation #{index}: operation type '{op_type}' is not supported."
            )

        handler = OPERATIONS[op_type]

        try:
            content, detail = handler(content, op, file_name)
        except OperationError:
            raise
        except Exception as exc:
            raise OperationError(
                f"Operation #{index} [{op_type}] failed: {type(exc).__name__}: {exc}"
            ) from exc

        results.append(
            OperationResult(index=index, type=op_type, detail=detail, status="ok")
        )

    return content, results


def _check_syntax_pre(target: Path, file_patch: Any, project: Any) -> None:
    if file_patch.skip_syntax_check:
        return

    handler = resolve_language(
        target,
        explicit_language=file_patch.language,
        project_default=getattr(project, "default_language", None),
    )

    if not handler.validates_syntax:
        return

    syntax_ok, syntax_error = handler.check_file(target, encoding=file_patch.encoding)

    if syntax_ok:
        return

    if handler.validation_kind == "built-in":
        raise VerificationError(
            f"Original file has {handler.name} syntax error before patch: {syntax_error}"
        )
    else:
        log.warning(
            "[WARN] External validator '%s' reported error on %s: %s. Continuing.",
            getattr(handler, "tool_name", handler.name), file_patch.file, syntax_error,
        )


def _check_syntax_post(target: Path, content: str, file_patch: Any, project: Any) -> None:
    if file_patch.skip_syntax_check:
        return

    handler = resolve_language(
        target,
        explicit_language=file_patch.language,
        project_default=getattr(project, "default_language", None),
    )

    if not handler.validates_syntax:
        return

    syntax_ok, syntax_error = handler.check_text(content)

    if syntax_ok:
        return

    if handler.validation_kind == "built-in":
        raise VerificationError(
            f"Invalid {handler.name} syntax after patch: {syntax_error}"
        )
    else:
        log.warning(
            "[WARN] External validator '%s' reported error on patched %s: %s. Continuing.",
            getattr(handler, "tool_name", handler.name), file_patch.file, syntax_error,
        )


def _rollback_created_resources(
    created_files: list[Path],
    created_dirs: list[Path],
) -> None:
    """Xóa các file/dir được tạo trong Phase 2 nếu patch fail.

    Thứ tự cleanup:
    1. Files trước (để dir có thể rỗng sau khi xóa file).
    2. Directories sau (chỉ xóa nếu rỗng — không xóa dir có file khác).

    Best-effort: log warning nếu xóa fail, không raise (vì đang trong tình huống rollback).
    """
    # Bước 1: Xóa files đã tạo (reversed = tạo sau xóa trước)
    for created_file in reversed(created_files):
        try:
            if created_file.exists():
                created_file.unlink()
                log.info(f"[ROLLBACK] Removed created file: {created_file}")
        except OSError as cleanup_exc:
            log.error(
                f"[ROLLBACK FAILED] Cannot remove created file {created_file}: {cleanup_exc}"
            )

    # Bước 2: Xóa directories đã tạo (reversed, chỉ nếu rỗng)
    for created_dir in reversed(created_dirs):
        try:
            if not created_dir.exists():
                continue
            if not created_dir.is_dir():
                continue
            if any(created_dir.iterdir()):
                log.warning(
                    f"[ROLLBACK] Skip non-empty directory: {created_dir}"
                )
                continue
            created_dir.rmdir()
            log.info(f"[ROLLBACK] Removed created directory: {created_dir}")
        except OSError as cleanup_exc:
            log.error(
                f"[ROLLBACK FAILED] Cannot remove created dir {created_dir}: {cleanup_exc}"
            )


def apply_patch_to_project(
    context: ExecutionContext,
    manifest: PatchManifest,
) -> PatchReport:
    project = context.project
    report = PatchReport(
        patch_path=context.patch_path,
        project_root=project.root,
        project_id=project.project_id,
        dry_run=context.dry_run,
    )

    # =========================================================================
    # Phase 0: CREATE BACKUP SESSION [GAP-1+4 FIX]
    # All backups of this patch apply go into the same session directory.
    # =========================================================================
    session_dir: Path | None = None
    pre_flight_dir: Path | None = None
    if not context.dry_run:
        try:
            session_dir = create_session_dir(project, manifest.patch_id)
            log.info(f"[SESSION] Backup session: {session_dir}")
            pre_flight_dir = create_session_dir(
                project, manifest.patch_id, subdir="pre_flight"
            )
            log.info(f"[PRE-FLIGHT] Backup session: {pre_flight_dir}")
        except BackupError as exc:
            report.success = False
            report.message = f"Failed to create backup session: {exc}"
            return report

    if manifest.target_projects:
        allowed = manifest.target_projects
        if "*" not in allowed and project.project_id not in allowed:
            report.message = (
                f"Patch does not target the current project. "
                f"target_projects={allowed}, project_id={project.project_id}"
            )
            return report

    # [FIX SIM102] Combine nested if
    if (
        manifest.project_types
        and "*" not in manifest.project_types
        and project.project_type not in manifest.project_types
    ):
        report.message = (
            f"Patch does not target the current project_type. "
            f"project_types={manifest.project_types}, "
            f"project_type={project.project_type}"
        )
        return report

    # =========================================================================
    # Phase 1: PRE-FLIGHT BACKUP
    # =========================================================================
    pre_flight_backups = []
    if manifest.rollback_on_verify_failure and not context.dry_run:
        try:
            for patch_entry in manifest.patches:
                if isinstance(patch_entry, DirectoryPatch):
                    continue
                file_patch = patch_entry
                try:
                    target = safe_join(project.root, file_patch.file)
                except ApplyPatchError:
                    continue
                if not target.exists():
                    continue
                try:
                    record = create_backup(
                        project=project,
                        file_path=target,
                        patch_id=manifest.patch_id,
                        session_dir=pre_flight_dir,
                    )
                    pre_flight_backups.append((target, record))
                except BackupError as exc:
                    raise ApplyPatchError(
                        f"Pre-flight backup failed for {file_patch.file}: {exc}"
                    ) from exc
            if pre_flight_backups:
                log.info(
                    f"[PRE-FLIGHT] Created {len(pre_flight_backups)} backup(s) for rollback."
                )
        except ApplyPatchError as exc:
            report.success = False
            report.message = f"Pre-flight backup failed: {exc}"
            return report

    # =========================================================================
    # Phase 2: APPLY
    # Track created resources để rollback nếu fail.
    # =========================================================================
    created_files: list[Path] = []  # Path của file mới tạo (chưa tồn tại trước)
    created_dirs: list[Path] = []   # Path của directory mới tạo (chưa tồn tại trước)

    all_ok = True
    try:
        for patch_entry in manifest.patches:
            if isinstance(patch_entry, DirectoryPatch):
                dir_result = FilePatchResult(file=patch_entry.path)
                report.files.append(dir_result)
                try:
                    dir_target = safe_join(project.root, patch_entry.path)
                    if dir_target.exists() and not dir_target.is_dir():
                        raise OperationError(
                            f"Cannot create directory: a file already exists at {dir_target}"
                        )

                    existed_before_dir = dir_target.exists()

                    if not context.dry_run:
                        dir_target.mkdir(parents=True, exist_ok=True)
                        dir_result.created = not existed_before_dir
                        if not existed_before_dir:
                            created_dirs.append(dir_target)
                        dir_result.changed = True
                        dir_result.status = "ok"
                        dir_result.message = "Directory created."
                    else:
                        dir_result.changed = True
                        dir_result.status = "ok"
                        dir_result.message = "DRY-RUN: directory would be created."
                except ApplyPatchError as exc:
                    all_ok = False
                    dir_result.status = "failed"
                    dir_result.message = f"{type(exc).__name__}: {exc}"
                    raise
                except Exception as exc:
                    all_ok = False
                    dir_result.status = "failed"
                    dir_result.message = f"Unexpected error: {type(exc).__name__}: {exc}"
                    raise
                continue

            file_patch = patch_entry
            result = FilePatchResult(file=file_patch.file)
            report.files.append(result)

            try:
                target = safe_join(project.root, file_patch.file)

                if target.exists() and not target.is_file():
                    raise OperationError(f"Path is not a file: {target}")

                existed_before = target.exists()

                if not existed_before:
                    first_op = file_patch.operations[0] if file_patch.operations else None
                    is_write_first = (
                        first_op is not None
                        and str(first_op.get("type", "")).strip() == "write_content"
                    )

                    if file_patch.create_if_missing or is_write_first:
                        content = ""
                        result.created = True
                        if not context.dry_run:
                            target.parent.mkdir(parents=True, exist_ok=True)
                    elif file_patch.optional:
                        result.status = "skipped"
                        result.message = "File does not exist and is marked optional."
                        continue
                    else:
                        raise OperationError(f"File does not exist: {target}")
                else:
                    if file_patch.verify_markers:
                        missing = verify_file_markers(
                            target, file_patch.verify_markers, encoding=file_patch.encoding
                        )
                        if missing:
                            raise VerificationError(
                                "File missing verification markers: " + ", ".join(missing)
                            )

                    try:
                        with open(target, "rb") as f_bin:
                            if b"\x00" in f_bin.read(8192):
                                raise OperationError(
                                    f"File appears to be binary (contains null bytes): {target}. "
                                    f"Apply Patch Code only supports text-based source files."
                                )
                    except OSError as exc:
                        raise OperationError(f"Cannot read file for binary check: {exc}") from exc

                    try:
                        content = read_text(target, encoding=file_patch.encoding)
                    except UnicodeDecodeError as exc:
                        raise OperationError(
                            f"File appears to be binary or not decodable with "
                            f"encoding '{file_patch.encoding}': {target}. "
                            f"Set the 'encoding' field correctly or exclude this file."
                        ) from exc

                    _check_syntax_pre(target, file_patch, project)

                original = content

                content, operation_results = apply_operations(
                    content, file_patch.operations, file_patch.file
                )

                result.operations = operation_results

                changed = content != original or (result.created and not existed_before)
                result.changed = changed

                if changed:
                    _check_syntax_post(target, content, file_patch, project)

                    if file_patch.verify_after:
                        verify_errors = verify_content(content, file_patch.verify_after)
                        result.verify_errors = verify_errors
                        if verify_errors:
                            raise VerificationError(
                                "verify_after failed before writing file: "
                                + "; ".join(verify_errors)
                            )

                    if not context.dry_run:
                        if existed_before:
                            backup_record = create_backup(
                                project=project,
                                file_path=target,
                                patch_id=manifest.patch_id,
                                session_dir=session_dir,
                            )
                            result.backup_path = backup_record.backup_file

                        write_text_atomic(target, content, encoding=file_patch.encoding)

                        # [C3 FIX] Track file mới tạo để rollback nếu cần
                        if not existed_before:
                            created_files.append(target)

                    result.status = "ok"
                    result.message = (
                        "DRY-RUN: valid changes, file not written."
                        if context.dry_run
                        else "File written successfully."
                    )
                else:
                    if file_patch.verify_after:
                        verify_errors = verify_content(content, file_patch.verify_after)
                        result.verify_errors = verify_errors
                        if verify_errors:
                            raise VerificationError(
                                "verify_after failed despite no changes: "
                                + "; ".join(verify_errors)
                            )

                    result.status = "ok"
                    result.message = "No actual changes."

            except ApplyPatchError as exc:
                all_ok = False
                result.status = "failed"
                result.message = f"{type(exc).__name__}: {exc}"
                raise
            except Exception as exc:
                all_ok = False
                result.status = "failed"
                result.message = f"Unexpected error: {type(exc).__name__}: {exc}"
                raise

    except ApplyPatchError as exc:
        # =========================================================================
        # Phase 3: ROLLBACK
        # =========================================================================
        has_rollback_work = bool(pre_flight_backups or created_files or created_dirs)
        if manifest.rollback_on_verify_failure and has_rollback_work:
            log.warning(
                f"[ROLLBACK] Patch failed. Restoring {len(pre_flight_backups)} file(s), "
                f"removing {len(created_files)} created file(s), "
                f"{len(created_dirs)} created dir(s)..."
            )
            # 1. Restore file đã backup
            for target, record in reversed(pre_flight_backups):
                try:
                    rollback_backup_path(project, record.backup_file)
                    log.info(f"[ROLLBACK] Restored {target}")
                except Exception as rollback_exc:
                    # Best-effort: tiếp tục restore các file khác dù 1 file fail
                    log.error(f"[ROLLBACK FAILED] {target}: {rollback_exc}")

            # 2. Cleanup file/dir mới tạo
            _rollback_created_resources(created_files, created_dirs)

            report.message = f"Patch failed and rolled back: {exc}"
        else:
            report.message = f"Patch failed: {exc}"
        report.success = False

        # [GAP-4 FIX] Write session metadata even on failure (success=False)
        if session_dir is not None:
            try:
                write_session_metadata(
                    session_dir=session_dir,
                    project=project,
                    patch_id=manifest.patch_id,
                    files=[
                        {
                            "file": f.file,
                            "status": f.status,
                            "backup_path": str(f.backup_path) if f.backup_path else None,
                        }
                        for f in report.files
                    ],
                    success=False,
                )
            except Exception as meta_exc:
                log.warning(f"[SESSION] Failed to write session metadata: {meta_exc}")

        return report

    report.success = all_ok
    report.message = "Success." if all_ok else "Errors occurred during patching."

    # [GAP-4 FIX] Write session metadata on success
    if session_dir is not None:
        try:
            write_session_metadata(
                session_dir=session_dir,
                project=project,
                patch_id=manifest.patch_id,
                files=[
                    {
                        "file": f.file,
                        "status": f.status,
                        "backup_path": str(f.backup_path) if f.backup_path else None,
                    }
                    for f in report.files
                ],
                success=all_ok,
            )
        except Exception as meta_exc:
            log.warning(f"[SESSION] Failed to write session metadata: {meta_exc}")

    # [UNDO] Write manifest + cleanup pre_flight on success
    if report.success and not context.dry_run and session_dir is not None:
        try:
            from .backup import (
                delete_pre_flight_session,
                update_index,
                write_manifest,
            )
            files_meta: list[dict[str, Any]] = []
            for f in report.files:
                # Skip no-op files: nothing changed, nothing to undo
                if not f.created and not f.changed:
                    continue
                action = "created" if f.created else "modified"
                backup_rel = None
                backup_sha = None
                if f.backup_path is not None:
                    try:
                        backup_rel = f.backup_path.relative_to(session_dir).as_posix()
                    except ValueError:
                        backup_rel = f.file
                    try:
                        from .utils import sha256_file
                        backup_sha = sha256_file(f.backup_path)
                    except Exception:
                        backup_sha = None
                # Post-patch SHA of target file (used by undo to detect user edits after apply)
                post_sha = None
                try:
                    from .utils import sha256_file
                    _target_path = project.root / f.file
                    post_sha = sha256_file(_target_path) if _target_path.is_file() else None
                except Exception:
                    post_sha = None
                files_meta.append({
                    "rel_path": f.file,
                    "action": action,
                    "backup_rel": backup_rel,
                    "sha256": post_sha,
                    "backup_sha256": backup_sha,
                    "size": 0,
                })
            write_manifest(session_dir, manifest.patch_id, project, files_meta)
            update_index(project)
            if pre_flight_dir is not None:
                delete_pre_flight_session(project, pre_flight_dir.name)
            log.info(f"[UNDO] Manifest written, {len(files_meta)} files tracked")
        except Exception as undo_exc:
            log.warning(f"[UNDO] Manifest write failed: {undo_exc}")

    # [SOURCE-MAP] Update source map từ patch apply (best-effort)
    if report.success and not context.dry_run:
        try:
            from .source_map import update_from_apply
            smap = update_from_apply(project, report)
            log.info(
                f"[SOURCE-MAP] Updated: {len(smap.source_files)} files, "
                f"{len(smap.source_folders)} folders tracked"
            )
        except Exception as sm_exc:
            log.warning(f"[SOURCE-MAP] Update failed (patch still OK): {sm_exc}")

    # [PROFILES] Auto-update 10 profiles/*.md from patch_history.
    # Best-effort: sync failure does NOT rollback a successful patch.
    import os as _os
    if (
        report.success
        and not context.dry_run
        and not _os.environ.get("APPLY_PATCH_NO_PROGRESS_UPDATE")
    ):
        try:
            from .profiles_sync import update_all_profiles
            sync_result = update_all_profiles(project.root)
            if sync_result.errors:
                log.warning(f"[PROFILES] Sync errors: {sync_result.errors}")
            else:
                log.info(
                    f"[PROFILES] Updated {len(sync_result.files_updated)} profile file(s)"
                )
        except Exception as prof_exc:
            log.warning(
                f"[PROFILES] Auto-update failed (patch still OK): "
                f"{type(prof_exc).__name__}: {prof_exc}"
            )

    return report