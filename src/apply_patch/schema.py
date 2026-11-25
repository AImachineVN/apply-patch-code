from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .context import SchemaError

log = logging.getLogger(__name__)

# Import mềm dẻo jsonschema (nếu chưa cài, tầng Defense in Depth mới sẽ tự động tắt)
try:
    import jsonschema
    from jsonschema import ValidationError
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False

# Flag để tránh spam log cảnh báo "schema file missing" mỗi lần validate
_schema_missing_warned = False

ALLOWED_OPERATION_TYPES = {
    "replace",
    "insert_after",
    "insert_before",
    "delete",
    "replace_regex",
    "write_content",
}

STRIP_LEGACY_KEYS = {
    "file", "type", "flags", "verify_markers", "contains", "not_contains",
    "patch_id", "id", "related_issue", "description", "author", "date",
    "version", "target_projects", "project_types", "project_id",
    "project_type", "markers", "source_roots", "exclude", "anchor",
}


def normalize_keys(value: Any) -> Any:
    """Chuẩn hóa key JSON bằng cách strip khoảng trắng thừa."""
    if isinstance(value, dict):
        return {str(k).strip(): normalize_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_keys(item) for item in value]
    return value


def _legacy_strip_values(value: Any, key: str | None = None) -> Any:
    """Chuẩn hóa giá trị legacy ở mức bảo thủ."""
    if isinstance(value, dict):
        return {k: _legacy_strip_values(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_legacy_strip_values(item, key) for item in value]
    if isinstance(value, str) and key in STRIP_LEGACY_KEYS:
        return value.strip()
    return value


def _as_str_list(value: Any, field_name: str) -> list[str]:
    """Ép giá trị thành list[str]."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise SchemaError(
                    f"Field '{field_name}[{index}]' must be a string, "
                    f"got: {type(item).__name__}"
                )
            result.append(item)
        return result
    raise SchemaError(f"Field '{field_name}' must be a list of strings or a single string.")


def _as_bool(value: Any, field_name: str) -> bool:
    """Ép giá trị thành bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    raise SchemaError(f"Field '{field_name}' must be a boolean.")


def _require_str(
    op: dict[str, Any],
    key: str,
    op_index: int,
    allow_empty: bool = False,
) -> str:
    """Lấy trường chuỗi bắt buộc từ operation."""
    value = op.get(key)
    if not isinstance(value, str):
        raise SchemaError(
            f"Operation #{op_index}: field '{key}' must be a string, "
            f"got: {type(value).__name__}"
        )
    if not allow_empty and not value:
        raise SchemaError(f"Operation #{op_index}: field '{key}' must not be empty.")
    return value


# =============================================================================
# DATA CLASSES CHO PROGRESS REPORT (14 mục theo tài liệu PHỐI HỢP AI)
# =============================================================================

@dataclass
class ProgressTask:
    """Một task trong progress_report (completed/uncompleted/proposed)."""
    id: str
    name: str
    completed_at: str = ""
    note: str = ""
    reason: str = ""
    priority: str = ""


@dataclass
class FileAction:
    """Một file được chỉnh sửa hoặc xóa."""
    path: str
    action: str  # "modified" | "deleted"


@dataclass
class ApiChange:
    """Một thay đổi API/hàm/giao diện/dữ liệu."""
    file: str
    kind: str  # "api" | "function" | "interface" | "data"
    change: str


@dataclass
class TestResult:
    """Kết quả một lệnh kiểm thử."""
    command: str
    result: str


@dataclass
class RemainingIssue:
    """Một lỗi còn tồn tại hoặc rủi ro."""
    id: str
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    description: str


@dataclass
class TechnicalDecision:
    """Một quyết định kỹ thuật đã đưa ra."""
    id: str
    decision: str
    rationale: str


@dataclass
class ProgressReport:
    """
    Báo cáo tiến độ dự án, BẮT BUỘC trong mỗi patch theo tài liệu PHỐI HỢP AI.
    Chứa 14 mục được định nghĩa trong phần V của tài liệu.
    """
    task_name: str
    objective_and_scope: str
    mandatory_info_for_next_ai: str

    completed_functions: list[ProgressTask] = field(default_factory=list)
    uncompleted_functions: list[ProgressTask] = field(default_factory=list)

    files_created: list[str] = field(default_factory=list)
    files_modified_or_deleted: list[FileAction] = field(default_factory=list)

    significant_changes: list[str] = field(default_factory=list)
    api_and_interface_changes: list[ApiChange] = field(default_factory=list)
    affected_modules: list[str] = field(default_factory=list)
    source_tree: str = ""

    test_results: list[TestResult] = field(default_factory=list)

    remaining_issues_and_risks: list[RemainingIssue] = field(default_factory=list)
    technical_decisions: list[TechnicalDecision] = field(default_factory=list)
    proposed_next_work: list[ProgressTask] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ProgressReport:
        """Parse và validate progress_report từ dict."""
        if data is None:
            raise SchemaError(
                "'progress_report' is required in every patch. "
                "See section V of PHỐI HỢP LÀM VIỆC CỦA CÁC AI.md for the 14 mandatory items."
            )
        if not isinstance(data, dict):
            raise SchemaError("'progress_report' must be a JSON object.")

        # Validate 3 string fields bắt buộc
        task_name = str(data.get("task_name", "")).strip()
        objective_and_scope = str(data.get("objective_and_scope", "")).strip()
        mandatory_info = str(data.get("mandatory_info_for_next_ai", "")).strip()

        if not task_name:
            raise SchemaError("'progress_report.task_name' is required and must not be empty.")
        if not objective_and_scope:
            raise SchemaError("'progress_report.objective_and_scope' is required and must not be empty.")
        if not mandatory_info:
            raise SchemaError("'progress_report.mandatory_info_for_next_ai' is required and must not be empty.")

        return cls(
            task_name=task_name,
            objective_and_scope=objective_and_scope,
            mandatory_info_for_next_ai=mandatory_info,
            completed_functions=_parse_progress_tasks(data.get("completed_functions", []), "completed_functions"),
            uncompleted_functions=_parse_progress_tasks(data.get("uncompleted_functions", []), "uncompleted_functions"),
            files_created=_as_str_list(data.get("files_created", []), "progress_report.files_created"),
            files_modified_or_deleted=_parse_file_actions(data.get("files_modified_or_deleted", [])),
            significant_changes=_as_str_list(data.get("significant_changes", []), "progress_report.significant_changes"),
            api_and_interface_changes=_parse_api_changes(data.get("api_and_interface_changes", [])),
            affected_modules=_as_str_list(data.get("affected_modules", []), "progress_report.affected_modules"),
            source_tree=str(data.get("source_tree", "")).strip(),
            test_results=_parse_test_results(data.get("test_results", [])),
            remaining_issues_and_risks=_parse_remaining_issues(data.get("remaining_issues_and_risks", [])),
            technical_decisions=_parse_technical_decisions(data.get("technical_decisions", [])),
            proposed_next_work=_parse_progress_tasks(data.get("proposed_next_work", []), "proposed_next_work"),
        )


def _parse_progress_tasks(data: Any, field_name: str) -> list[ProgressTask]:
    if not isinstance(data, list):
        raise SchemaError(f"'progress_report.{field_name}' must be a list.")
    result: list[ProgressTask] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise SchemaError(f"'progress_report.{field_name}[{i}]' must be an object.")
        tid = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if not tid or not name:
            raise SchemaError(
                f"'progress_report.{field_name}[{i}]' requires 'id' and 'name'."
            )
        result.append(ProgressTask(
            id=tid,
            name=name,
            completed_at=str(item.get("completed_at", "")).strip(),
            note=str(item.get("note", "")).strip(),
            reason=str(item.get("reason", "")).strip(),
            priority=str(item.get("priority", "")).strip(),
        ))
    return result


def _parse_file_actions(data: Any) -> list[FileAction]:
    if not isinstance(data, list):
        raise SchemaError("'progress_report.files_modified_or_deleted' must be a list.")
    valid_actions = {"modified", "deleted"}
    result: list[FileAction] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise SchemaError(f"'progress_report.files_modified_or_deleted[{i}]' must be an object.")
        path = str(item.get("path", "")).strip()
        action = str(item.get("action", "")).strip()
        if not path or action not in valid_actions:
            raise SchemaError(
                f"'progress_report.files_modified_or_deleted[{i}]' requires "
                f"'path' and 'action' in {valid_actions}."
            )
        result.append(FileAction(path=path, action=action))
    return result


def _parse_api_changes(data: Any) -> list[ApiChange]:
    if not isinstance(data, list):
        raise SchemaError("'progress_report.api_and_interface_changes' must be a list.")
    valid_kinds = {"api", "function", "interface", "data"}
    result: list[ApiChange] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise SchemaError(f"'progress_report.api_and_interface_changes[{i}]' must be an object.")
        f = str(item.get("file", "")).strip()
        kind = str(item.get("kind", "")).strip()
        change = str(item.get("change", "")).strip()
        if not f or kind not in valid_kinds or not change:
            raise SchemaError(
                f"'progress_report.api_and_interface_changes[{i}]' requires "
                f"'file', 'kind' in {valid_kinds}, and 'change'."
            )
        result.append(ApiChange(file=f, kind=kind, change=change))
    return result


def _parse_test_results(data: Any) -> list[TestResult]:
    if not isinstance(data, list):
        raise SchemaError("'progress_report.test_results' must be a list.")
    result: list[TestResult] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise SchemaError(f"'progress_report.test_results[{i}]' must be an object.")
        cmd = str(item.get("command", "")).strip()
        res = str(item.get("result", "")).strip()
        if not cmd or not res:
            raise SchemaError(
                f"'progress_report.test_results[{i}]' requires 'command' and 'result'."
            )
        result.append(TestResult(command=cmd, result=res))
    return result


def _parse_remaining_issues(data: Any) -> list[RemainingIssue]:
    if not isinstance(data, list):
        raise SchemaError("'progress_report.remaining_issues_and_risks' must be a list.")
    valid_severity = {"HIGH", "MEDIUM", "LOW"}
    result: list[RemainingIssue] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise SchemaError(f"'progress_report.remaining_issues_and_risks[{i}]' must be an object.")
        tid = str(item.get("id", "")).strip()
        sev = str(item.get("severity", "")).strip()
        desc = str(item.get("description", "")).strip()
        if not tid or sev not in valid_severity or not desc:
            raise SchemaError(
                f"'progress_report.remaining_issues_and_risks[{i}]' requires "
                f"'id', 'severity' in {valid_severity}, and 'description'."
            )
        result.append(RemainingIssue(id=tid, severity=sev, description=desc))
    return result


def _parse_technical_decisions(data: Any) -> list[TechnicalDecision]:
    if not isinstance(data, list):
        raise SchemaError("'progress_report.technical_decisions' must be a list.")
    result: list[TechnicalDecision] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise SchemaError(f"'progress_report.technical_decisions[{i}]' must be an object.")
        tid = str(item.get("id", "")).strip()
        decision = str(item.get("decision", "")).strip()
        rationale = str(item.get("rationale", "")).strip()
        if not tid or not decision or not rationale:
            raise SchemaError(
                f"'progress_report.technical_decisions[{i}]' requires "
                f"'id', 'decision', and 'rationale'."
            )
        result.append(TechnicalDecision(id=tid, decision=decision, rationale=rationale))
    return result


# =============================================================================
# DATA CLASSES CHO PATCH MANIFEST
# =============================================================================

@dataclass
class VerifyRules:
    """Quy tắc xác minh sau khi patch."""
    contains: list[str] = field(default_factory=list)
    not_contains: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> VerifyRules:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise SchemaError("'verify_after' must be a JSON object.")
        contains = _as_str_list(data.get("contains", []), "verify_after.contains")
        not_contains = _as_str_list(
            data.get("not_contains", []),
            "verify_after.not_contains",
        )
        return cls(contains=contains, not_contains=not_contains)


@dataclass
class FilePatch:
    """Mô tả patch trên một file."""
    file: str
    operations: list[dict[str, Any]] = field(default_factory=list)
    verify_markers: list[str] = field(default_factory=list)
    optional: bool = False
    create_if_missing: bool = False
    verify_after: VerifyRules | None = None
    encoding: str = "utf-8"
    language: str | None = None
    skip_syntax_check: bool = False

    @classmethod
    def from_dict(cls, data: Any, index: int) -> FilePatch:
        if not isinstance(data, dict):
            raise SchemaError(f"patches[{index}] must be a JSON object.")
        file_value = data.get("file")
        if not isinstance(file_value, str) or not file_value.strip():
            raise SchemaError(f"patches[{index}].file is a required field.")
        operations_raw = data.get("operations", [])
        if not isinstance(operations_raw, list):
            raise SchemaError(f"patches[{index}].operations must be a list.")
        operations: list[dict[str, Any]] = []
        for op_index, op in enumerate(operations_raw, start=1):
            _validate_operation(op, op_index)
            operations.append(op)
        verify_markers = _as_str_list(
            data.get("verify_markers", []),
            f"patches[{index}].verify_markers",
        )
        optional = _as_bool(data.get("optional", False), f"patches[{index}].optional")
        create_if_missing = _as_bool(
            data.get("create_if_missing", False),
            f"patches[{index}].create_if_missing",
        )
        verify_after_raw = data.get("verify_after")
        verify_after = VerifyRules.from_dict(verify_after_raw)
        encoding = data.get("encoding", "utf-8")
        if not isinstance(encoding, str) or not encoding.strip():
            raise SchemaError(f"patches[{index}].encoding must be a non-empty string.")
        language_raw = data.get("language")
        language = None
        if language_raw is not None:
            if not isinstance(language_raw, str):
                raise SchemaError(f"patches[{index}].language must be a string.")
            language = language_raw.strip() or None
        skip_syntax_check = _as_bool(
            data.get("skip_syntax_check", False),
            f"patches[{index}].skip_syntax_check",
        )
        return cls(
            file=file_value,
            operations=operations,
            verify_markers=verify_markers,
            optional=optional,
            create_if_missing=create_if_missing,
            verify_after=verify_after,
            encoding=encoding.strip(),
            language=language,
            skip_syntax_check=skip_syntax_check,
        )


@dataclass
class DirectoryPatch:
    """Mô tả yêu cầu tạo một thư mục rỗng."""
    type: str
    path: str

    @classmethod
    def from_dict(cls, data: Any, index: int) -> DirectoryPatch:
        if not isinstance(data, dict):
            raise SchemaError(f"patches[{index}] must be a JSON object.")
        op_type = data.get("type")
        if op_type != "create_directory":
            raise SchemaError(
                f"patches[{index}].type must be 'create_directory', got: '{op_type}'"
            )
        path_value = data.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise SchemaError(
                f"patches[{index}].path is required for create_directory entries."
            )
        path_stripped = path_value.strip()
        if ".." in path_stripped:
            raise SchemaError(
                f"patches[{index}].path must not contain '..' "
                f"to prevent Path Traversal attacks."
            )
        return cls(type="create_directory", path=path_stripped)


@dataclass
class PatchManifest:
    """Manifest của một file patch."""
    schema_version: str
    patch_id: str
    description: str = ""
    author: str = ""
    date: str = ""
    target_projects: list[str] = field(default_factory=list)
    project_types: list[str] = field(default_factory=list)
    patches: list[FilePatch | DirectoryPatch] = field(default_factory=list)
    rollback_on_verify_failure: bool = False
    progress_report: ProgressReport | None = None  # [MỚI] Bắt buộc

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchManifest:
        if not isinstance(data, dict):
            raise SchemaError("Root patch JSON must be an object.")
        schema_version = str(data.get("schema_version", "")).strip()
        if schema_version not in {"1.0", "2.0"}:
            raise SchemaError(
                "Patch must have a valid schema_version: '1.0' or '2.0'. "
                f"Current value: '{schema_version}'"
            )
        patch_id = str(
            data.get("patch_id")
            or data.get("id")
            or data.get("related_issue")
            or "legacy_patch"
        ).strip()
        if not patch_id:
            raise SchemaError("Patch must have 'patch_id', 'id', or 'related_issue'.")
        description = str(data.get("description", "")).strip()
        author = str(data.get("author", "")).strip()
        date = str(data.get("date", "")).strip()
        target_projects = _as_str_list(
            data.get("target_projects", []),
            "target_projects",
        )
        project_types = _as_str_list(
            data.get("project_types", []),
            "project_types",
        )
        rollback_on_verify_failure = _as_bool(
            data.get("rollback_on_verify_failure", False),
            "rollback_on_verify_failure",
        )
        patches_raw = data.get("patches", [])
        if not isinstance(patches_raw, list) or not patches_raw:
            raise SchemaError("Field 'patches' must be a non-empty list.")
        patches: list[FilePatch | DirectoryPatch] = []
        for index, item in enumerate(patches_raw):
            if not isinstance(item, dict):
                raise SchemaError(f"patches[{index}] must be a JSON object.")
            if item.get("type") == "create_directory":
                patches.append(DirectoryPatch.from_dict(item, index))
            elif "file" in item:
                patches.append(FilePatch.from_dict(item, index))
            else:
                raise SchemaError(
                    f"patches[{index}] must have either 'file' (for file patch) "
                    f"or 'type: create_directory' with 'path' (for directory creation)."
                )

        # [MỚI] Parse progress_report (bắt buộc)
        progress_report = ProgressReport.from_dict(data.get("progress_report"))

        return cls(
            schema_version=schema_version,
            patch_id=patch_id,
            description=description,
            author=author,
            date=date,
            target_projects=target_projects,
            project_types=project_types,
            patches=patches,
            rollback_on_verify_failure=rollback_on_verify_failure,
            progress_report=progress_report,
        )


def _validate_operation(op: Any, index: int) -> None:
    """Validate một operation trong patch."""
    if not isinstance(op, dict):
        raise SchemaError(f"Operation #{index} must be a JSON object.")
    op_type = op.get("type")
    if not isinstance(op_type, str):
        raise SchemaError(f"Operation #{index}: field 'type' is required.")
    op_type = op_type.strip()
    if op_type not in ALLOWED_OPERATION_TYPES:
        raise SchemaError(
            f"Operation #{index}: operation type '{op_type}' is not supported. "
            f"Valid types: {sorted(ALLOWED_OPERATION_TYPES)}"
        )
    if op_type == "replace":
        _require_str(op, "old_text", index, allow_empty=False)
        _require_str(op, "new_text", index, allow_empty=True)
        occurrence = op.get("occurrence", 1)
        if isinstance(occurrence, bool) or not isinstance(occurrence, int):
            raise SchemaError(f"Operation #{index}: 'occurrence' must be an integer.")
        if occurrence != -1 and occurrence < 1:
            raise SchemaError(
                f"Operation #{index}: 'occurrence' must be -1 or a positive integer."
            )
    elif op_type in {"insert_after", "insert_before"}:
        _require_str(op, "anchor", index, allow_empty=False)
        _require_str(op, "new_text", index, allow_empty=True)
    elif op_type == "delete":
        _require_str(op, "old_text", index, allow_empty=False)
    elif op_type == "replace_regex":
        pattern = _require_str(op, "pattern", index, allow_empty=False)
        _require_str(op, "replacement", index, allow_empty=True)
        flags_str = op.get("flags", "")
        if not isinstance(flags_str, str):
            raise SchemaError(f"Operation #{index}: 'flags' must be a string.")
        flags_str = flags_str.strip()
        flags = 0
        for flag_char in flags_str:
            if flag_char == "i":
                flags |= re.IGNORECASE
            elif flag_char == "m":
                flags |= re.MULTILINE
            elif flag_char == "s":
                flags |= re.DOTALL
            elif flag_char == "x":
                flags |= re.VERBOSE
            else:
                raise SchemaError(
                    f"Operation #{index}: invalid regex flag: '{flag_char}'. "
                    "Only i, m, s, x are supported."
                )
        try:
            re.compile(pattern, flags=flags)
        except re.error as exc:
            raise SchemaError(
                f"Operation #{index}: invalid regex: {exc}"
            ) from exc
    elif op_type == "write_content":
        _require_str(op, "content", index, allow_empty=True)
    else:
        raise SchemaError(f"Operation #{index}: unsupported operation type.")


def _validate_with_jsonschema(data: dict[str, Any]) -> None:
    """Defense in Depth: Validate dict bằng JSON Schema Draft 2020-12.

    Layer 2 validation. Failure modes được phân biệt rõ:
    - jsonschema library không cài → skip (không phải lỗi, tầng 1 vẫn chạy)
    - Schema file không tồn tại → warn 1 lần (build issue, không raise)
    - Schema file tồn tại nhưng corrupt → log error + raise SchemaError (real bug)
    - jsonschema.validate raise ValidationError → raise SchemaError (đã có)
    - jsonschema.validate raise Exception khác → warn, continue (library issue)
    """
    global _schema_missing_warned

    if not _JSONSCHEMA_AVAILABLE:
        return

    # Bước 1: Resolve đường dẫn schema
    try:
        from .utils.path_resolver import get_resource_path
        schema_path = get_resource_path("src/apply_patch/core/schemas/patch_v2.json")
    except Exception as exc:
        log.warning(
            "Cannot resolve JSON Schema path: %s: %s. Layer 2 disabled.",
            type(exc).__name__, exc,
        )
        return

    # Bước 2: File không tồn tại → build issue, warn 1 lần
    if not schema_path.exists():
        if not _schema_missing_warned:
            log.warning(
                "JSON Schema file not found at %s. "
                "Defense-in-Depth layer 2 disabled. "
                "This usually means the build did not bundle "
                "'core/schemas/patch_v2.json'. See build.py --include-data-dir.",
                schema_path,
            )
            _schema_missing_warned = True
        return

    # Bước 3: File tồn tại nhưng không đọc/parse được → REAL BUG, phải raise
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("JSON Schema file at %s is corrupt or unreadable: %s", schema_path, exc)
        raise SchemaError(
            f"JSON Schema file exists but cannot be loaded at {schema_path}: {exc}. "
            f"This is a build/packaging error — please verify the bundled schema file."
        ) from exc

    # Bước 4: Chạy validate thật
    try:
        jsonschema.validate(instance=data, schema=schema)
    except ValidationError as exc:
        path_str = (
            " -> ".join(str(p) for p in exc.absolute_path)
            if exc.absolute_path else "root"
        )
        if "'..'" in exc.message or "does not match" in exc.message:
            raise SchemaError(
                f"Security error at '{path_str}': Path must not contain '..' "
                f"to prevent Path Traversal attacks. Please fix the 'file' field."
            ) from exc
        raise SchemaError(
            f"JSON Schema validation error at '{path_str}': {exc.message}"
        ) from exc
    except Exception as exc:
        # Lỗi không mong đợi từ jsonschema library (version mismatch, etc.)
        # Không raise — tầng 1 đã validate đủ. Nhưng log để debug.
        log.warning(
            "Unexpected error in JSON Schema validation: %s: %s. "
            "Continuing with layer-1 validation only.",
            type(exc).__name__, exc,
        )


def load_patch(path: Path) -> PatchManifest:
    """Đọc và validate file patch JSON."""
    path = Path(path)
    if not path.exists():
        raise SchemaError(f"Patch file not found: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SchemaError(
            f"Cannot read patch file {path}: File is not UTF-8 encoded. "
            f"Please re-save with UTF-8 encoding (no BOM)."
        ) from exc
    except Exception as exc:
        raise SchemaError(f"Cannot read patch file {path}: {exc}") from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SchemaError(
            f"Invalid JSON in patch file {path} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    normalized = normalize_keys(raw)
    if not isinstance(normalized, dict):
        raise SchemaError("Root patch JSON must be an object.")
    schema_version = str(normalized.get("schema_version", "")).strip()
    is_legacy = schema_version in {"", "1", "1.0"}
    if is_legacy:
        normalized = _legacy_strip_values(normalized)
        normalized["schema_version"] = "1.0"
    _validate_with_jsonschema(normalized)
    return PatchManifest.from_dict(normalized)