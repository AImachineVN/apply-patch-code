from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, cast

from .backup import list_backups, rollback_backup_path
from .context import ApplyPatchError, ExecutionContext, PatchReport
from .discovery import (
    discover_project,
    forget_last_project,
    init_project,
    load_project_from_path,
)
from .engine import apply_patch_to_project
from .languages import list_languages
from .schema import load_patch
from .source_snapshot import generate_snapshot

log = logging.getLogger("apply_patch")


def configure_logging(verbose: bool, quiet: bool, log_file: str | None) -> None:
    """Cấu hình logging cho CLI."""
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def _resolve_patch_path(value: str) -> Path:
    """Tìm file patch từ đường dẫn người dùng nhập."""
    path = Path(value)
    if path.is_absolute():
        resolved = path.resolve()
        if resolved.exists():
            return resolved
        raise ApplyPatchError(f"Patch file not found: {resolved}")

    candidates = [
        Path.cwd() / path,
        Path.cwd() / "patches" / path,
        Path.cwd() / "patches" / path.name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise ApplyPatchError(
        f"Patch file '{value}' not found. Tried: "
        + ", ".join(str(c) for c in candidates)
    )


def _print_report(report: PatchReport, json_output: bool) -> None:
    """In báo cáo kết quả."""
    if json_output:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return

    log.info("=" * 70)
    log.info("Patch file : %s", report.patch_path)
    log.info("Project    : %s", report.project_id)
    log.info("Root       : %s", report.project_root)
    log.info("Mode       : %s", "DRY-RUN" if report.dry_run else "APPLY")
    log.info("Success    : %s", report.success)
    log.info("Message    : %s", report.message)

    for file_result in report.files:
        log.info("-" * 70)
        log.info("File       : %s", file_result.file)
        log.info("Status     : %s", file_result.status)
        if file_result.message:
            log.info("Message    : %s", file_result.message)
        if file_result.backup_path:
            log.info("Backup     : %s", file_result.backup_path)
        if file_result.verify_errors:
            for error in file_result.verify_errors:
                log.error("Verify     : %s", error)
        for op in file_result.operations:
            log.info("Op #%02d    : [%s] %s", op.index, op.type, op.detail)

    log.info("=" * 70)


def _record_patch_history(
    project: Any,
    patch_path: Path,
    manifest: Any,
) -> None:
    """Record a successful patch apply to patch_history.json.

    CLI equivalent of GUI's _record_and_refresh. Best-effort: log warning on
    failure, don't raise (patch already applied, history is metadata).
    """
    from dataclasses import asdict

    from .patch_history import (
        PatchHistory,
        compute_file_sha256,
        get_history_path,
    )

    try:
        history_path = get_history_path(project.root)
        history = PatchHistory.load(history_path)
        sha256 = compute_file_sha256(patch_path)
        progress_snapshot = None
        if manifest.progress_report is not None:
            try:
                progress_snapshot = asdict(manifest.progress_report)
            except Exception:
                progress_snapshot = None
        history.record_success(
            filename=patch_path.name,
            patch_id=manifest.patch_id,
            sha256=sha256,
            progress_report_snapshot=progress_snapshot,
        )
        if history.save(history_path):
            log.info(
                "[HISTORY] Recorded %s (patch_id=%s)",
                patch_path.name,
                manifest.patch_id,
            )
        else:
            log.warning("[HISTORY] Failed to save history for %s", patch_path.name)
    except Exception as exc:
        log.warning("[HISTORY] Failed to record %s: %s", patch_path.name, exc)


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate patch JSON."""
    patch_path = _resolve_patch_path(args.patch)
    manifest = load_patch(patch_path)

    if args.json:
        print(
            json.dumps(
                {
                    "patch_path": str(patch_path),
                    "schema_version": manifest.schema_version,
                    "patch_id": manifest.patch_id,
                    "description": manifest.description,
                    "file_count": len(manifest.patches),
                    "valid": True,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        log.info("Valid patch: %s", patch_path)
        log.info("Schema version : %s", manifest.schema_version)
        log.info("Patch ID       : %s", manifest.patch_id)
        log.info("Description    : %s", manifest.description)
        log.info("File count     : %d", len(manifest.patches))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Áp dụng patch."""
    patch_path = _resolve_patch_path(args.patch)
    manifest = load_patch(patch_path)
    project = discover_project(
        explicit=args.project,
        project_id=args.project_id,
    )

    context = ExecutionContext(
        project=project,
        dry_run=args.dry_run,
        json_output=args.json,
        patch_path=patch_path,
    )
    report = apply_patch_to_project(context, manifest)
    _print_report(report, args.json)
    if report.success and not args.dry_run:
        _record_patch_history(project, patch_path, manifest)
    return 0 if report.success else 1


def cmd_auto(args: argparse.Namespace) -> int:
    """Chạy pipeline auto: dry-run trước, sau đó apply thật."""
    patch_path = _resolve_patch_path(args.patch)
    manifest = load_patch(patch_path)
    project = discover_project(
        explicit=args.project,
        project_id=args.project_id,
    )

    dry_context = ExecutionContext(
        project=project,
        dry_run=True,
        json_output=args.json,
        patch_path=patch_path,
    )
    log.info("[AUTO] Step 1/2: Dry-run")
    dry_report = apply_patch_to_project(dry_context, manifest)
    _print_report(dry_report, args.json)

    if not dry_report.success:
        log.error("[AUTO] Dry-run failed. Not applying for real.")
        return 1

    real_context = ExecutionContext(
        project=project,
        dry_run=False,
        json_output=args.json,
        patch_path=patch_path,
    )
    log.info("[AUTO] Step 2/2: Applying for real")
    real_report = apply_patch_to_project(real_context, manifest)
    _print_report(real_report, args.json)
    if real_report.success:
        _record_patch_history(project, patch_path, manifest)
    return 0 if real_report.success else 1


def cmd_detect(args: argparse.Namespace) -> int:
    """Hiển thị project được nhận diện."""
    project = discover_project(
        explicit=args.project,
        project_id=args.project_id,
    )

    if args.json:
        print(json.dumps(project.to_dict(), indent=2, ensure_ascii=False))
    else:
        log.info("Project ID       : %s", project.project_id)
        log.info("Project root     : %s", project.root)
        log.info("Project type     : %s", project.project_type)
        log.info("Default language : %s", project.default_language)
        log.info("Manifest         : %s", project.manifest_path)
        log.info("Legacy           : %s", project.legacy)
        log.info("Markers          : %s", ", ".join(project.markers) or "(empty)")
    return 0


def cmd_languages(args: argparse.Namespace) -> int:
    """Liệt kê các ngôn ngữ đã đăng ký và trạng thái validator."""
    rows = list_languages()

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    log.info("=" * 82)
    log.info("%-14s | %-30s | %-9s | %s", "LANGUAGE", "EXTENSIONS", "VALIDATES", "KIND")
    log.info("-" * 82)
    for row in rows:
        # Bỏ dòng plain trùng lặp, chỉ giữ dòng fallback cuối danh sách
        if row["name"] == "plain":
            continue
        exts = ", ".join(cast(list[str], row["extensions"])) if row["extensions"] else "(none)"
        validates = "yes" if row["validates_syntax"] else "no"
        log.info(
            "%-14s | %-30s | %-9s | %s",
            row["name"],
            exts,
            validates,
            row["validation_kind"],
        )
    log.info("=" * 82)
    log.info("Note: external validators are advisory only. Missing tools never block a patch.")
    return 0


def cmd_list_backups(args: argparse.Namespace) -> int:
    """Liệt kê backup."""
    project = discover_project(
        explicit=args.project,
        project_id=args.project_id,
    )
    records = list_backups(project)

    if args.json:
        print(
            json.dumps(
                [record.to_dict() for record in records],
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if not records:
        log.info("No backups found in project: %s", project.root)
        return 0

    log.info("Found %d backup(s) in project: %s", len(records), project.root)
    for record in records:
        log.info("-" * 70)
        log.info("Timestamp      : %s", record.timestamp)
        log.info("Original file  : %s", record.original_rel)
        log.info("Patch ID       : %s", record.patch_id)
        log.info("Backup file    : %s", record.backup_file)
        log.info("Metadata       : %s", record.metadata_file)
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    """Rollback từ backup."""
    backup_path = Path(args.backup_path).resolve()
    project = None

    meta_path = backup_path
    if not backup_path.name.endswith(".meta.json"):
        meta_path = backup_path.parent / (backup_path.name + ".meta.json")

    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            project_root = metadata.get("project_root")
            if project_root and Path(project_root).exists():
                project = load_project_from_path(Path(project_root))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            project = None

    if project is None:
        project = discover_project(
            explicit=args.project,
            project_id=args.project_id,
        )

    original_path = rollback_backup_path(project, backup_path)

    if args.json:
        print(
            json.dumps(
                {
                    "success": True,
                    "original_path": str(original_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        log.info("Rollback succeeded: %s", original_path)
    return 0


def cmd_init_project(args: argparse.Namespace) -> int:
    """Tạo project manifest."""
    path = Path(args.path).resolve()
    manifest_path = init_project(
        path=path,
        project_id=args.project_id,
        project_type=args.project_type,
        default_language=args.default_language,
        markers=args.marker,
        overwrite=args.force,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "success": True,
                    "manifest_path": str(manifest_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        log.info("Created project manifest: %s", manifest_path)
    return 0


def cmd_forget(args: argparse.Namespace) -> int:
    """Xóa file ghi nhớ project (tương thích lệnh cũ)."""
    deleted = forget_last_project()
    if args.json:
        print(json.dumps({"success": True, "deleted": deleted}, indent=2))
    else:
        if deleted:
            log.info("Deleted last project memory file.")
        else:
            log.info("No last project memory file to delete.")
    return 0

def cmd_snapshot_source(args: argparse.Namespace) -> int:
    """Generate source snapshot (2 files) for AI handoff."""
    project = discover_project(
        explicit=args.project,
        project_id=args.project_id,
    )

    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    result = generate_snapshot(project=project, output_dir=output_dir)

    if args.json:
        print(
            json.dumps(
                {
                    "success": result.success,
                    "tree_path": str(result.tree_path),
                    "content_path": str(result.content_path),
                    "content_format": result.content_format,
                    "total_files": result.total_files,
                    "included_files": result.included_files,
                    "skipped_files": result.skipped_files,
                    "total_bytes": result.total_bytes,
                    "included_bytes": result.included_bytes,
                    "warnings": result.warnings,
                    "error": result.error,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if result.success:
            log.info("Tree file      : %s", result.tree_path)
            log.info("Content file   : %s", result.content_path)
            log.info("Content format : %s", result.content_format)
            log.info("Total files    : %d", result.total_files)
            log.info("Included files : %d", result.included_files)
            log.info("Skipped files  : %d", result.skipped_files)
            log.info("Total bytes    : %d", result.total_bytes)
            log.info("Included bytes : %d", result.included_bytes)
            for warning in result.warnings:
                log.warning("  %s", warning)
        else:
            log.error("Snapshot failed: %s", result.error)

    return 0 if result.success else 1



def build_parser() -> argparse.ArgumentParser:
    """Xây dựng CLI parser."""
    base = argparse.ArgumentParser(add_help=False)
    base.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    base.add_argument("-q", "--quiet", action="store_true", help="Only log warnings/errors.")
    base.add_argument("--log-file", help="Write logs to file.")

    parser = argparse.ArgumentParser(
        prog="apply_patch",
        description="Multi-project, multi-language patch tool for source code.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate
    p_validate = subparsers.add_parser(
        "validate",
        parents=[base],
        help="Validate a patch JSON file.",
    )
    p_validate.add_argument("patch", help="Path to patch JSON file.")
    p_validate.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_validate.set_defaults(func=cmd_validate)

    # apply
    p_apply = subparsers.add_parser(
        "apply",
        parents=[base],
        help="Apply a patch.",
    )
    p_apply.add_argument("patch", help="Path to patch JSON file.")
    p_apply.add_argument("--project", help="Path to project directory.")
    p_apply.add_argument("--project-id", help="Project ID in workspace.")
    p_apply.add_argument("--dry-run", action="store_true", help="Do not modify real files.")
    p_apply.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_apply.set_defaults(func=cmd_apply)

    # auto
    p_auto = subparsers.add_parser(
        "auto",
        parents=[base],
        help="Auto mode: dry-run first, then apply for real.",
    )
    p_auto.add_argument("patch", help="Path to patch JSON file.")
    p_auto.add_argument("--project", help="Path to project directory.")
    p_auto.add_argument("--project-id", help="Project ID in workspace.")
    p_auto.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_auto.set_defaults(func=cmd_auto)

    # detect
    p_detect = subparsers.add_parser(
        "detect",
        parents=[base],
        help="Detect project directory and default language.",
    )
    p_detect.add_argument("--project", help="Path to project directory.")
    p_detect.add_argument("--project-id", help="Project ID in workspace.")
    p_detect.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_detect.set_defaults(func=cmd_detect)

    # languages
    p_languages = subparsers.add_parser(
        "languages",
        parents=[base],
        help="List registered languages and syntax validators.",
    )
    p_languages.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_languages.set_defaults(func=cmd_languages)

    # list-backups
    p_list_backups = subparsers.add_parser(
        "list-backups",
        parents=[base],
        help="List backups of a project.",
    )
    p_list_backups.add_argument("--project", help="Path to project directory.")
    p_list_backups.add_argument("--project-id", help="Project ID in workspace.")
    p_list_backups.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_list_backups.set_defaults(func=cmd_list_backups)

    # rollback
    p_rollback = subparsers.add_parser(
        "rollback",
        parents=[base],
        help="Restore file from backup.",
    )
    p_rollback.add_argument("backup_path", help="Backup file or .meta.json file.")
    p_rollback.add_argument("--project", help="Path to project directory.")
    p_rollback.add_argument("--project-id", help="Project ID in workspace.")
    p_rollback.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_rollback.set_defaults(func=cmd_rollback)

    # init-project
    p_init = subparsers.add_parser(
        "init-project",
        parents=[base],
        help="Create .apply_patch/project.json for a project directory.",
    )
    p_init.add_argument("--path", default=".", help="Project directory.")
    p_init.add_argument("--project-id", help="Project ID.")
    p_init.add_argument("--project-type", default="python", help="Project type.")
    p_init.add_argument(
        "--default-language",
        default="python",
        help="Default language for files with unknown extensions.",
    )
    p_init.add_argument(
        "--marker",
        action="append",
        help="Marker file to identify project. Can be used multiple times.",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite existing manifest.")
    p_init.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_init.set_defaults(func=cmd_init_project)

    # forget
    p_forget = subparsers.add_parser(
        "forget",
        parents=[base],
        help="Delete last project memory file (legacy compatibility).",
    )
    p_forget.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_forget.set_defaults(func=cmd_forget)

    # snapshot-source
    p_snapshot = subparsers.add_parser(
        "snapshot-source",
        parents=[base],
        help="Generate source snapshot (source_tree.md + source_content.<ext>) for AI handoff.",
    )
    p_snapshot.add_argument("--project", help="Path to project directory.")
    p_snapshot.add_argument("--project-id", help="Project ID in workspace.")
    p_snapshot.add_argument(
        "--output-dir",
        help="Custom output directory (default: <project>/profiles/).",
    )
    p_snapshot.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_snapshot.set_defaults(func=cmd_snapshot_source)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
        log_file=getattr(args, "log_file", None),
    )

    try:
        return int(args.func(args))
    except ApplyPatchError as exc:
        log.error("[ERROR] %s", exc)
        return 1
    except KeyboardInterrupt:
        log.error("User cancelled operation.")
        return 130
    except Exception as exc:
        log.exception("[UNEXPECTED ERROR] %s", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())