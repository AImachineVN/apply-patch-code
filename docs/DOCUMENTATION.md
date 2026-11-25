# Apply Patch Code — Documentation

**Version**: 1.0.0  
**Last updated**: 2026-11-09  
**Platform**: Windows 10/11 (64-bit)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Quick Start](#3-quick-start)
4. [CLI Reference](#4-cli-reference)
5. [GUI Guide](#5-gui-guide)
6. [Patch Format](#6-patch-format)
7. [Progress Report](#7-progress-report)
8. [Backup and Rollback](#8-backup-and-rollback)
9. [Source Snapshot](#9-source-snapshot)
10. [AI Handoff Protocol](#10-ai-handoff-protocol)
11. [Troubleshooting](#11-troubleshooting)
12. [Development](#12-development)

---

## 1. Overview

### What is Apply Patch Code?

**Apply Patch Code** is a desktop tool that applies declarative JSON patches to source code projects. Instead of manually editing files, developers (and AI assistants) write self-describing JSON patches that are validated, dry-run tested, backed up, and applied atomically.

### Core Capabilities

| Feature | Description |
|---|---|
| **6 operation types** | `replace`, `insert_after`, `insert_before`, `delete`, `replace_regex`, `write_content` |
| **Multi-language validation** | Python, JSON, XML (built-in); JS, PHP, Go, Ruby, Shell (external advisory) |
| **Atomic writes** | `mkstemp` + `os.replace` — no partial writes |
| **Line ending preservation** | CRLF / LF / CR preserved verbatim |
| **Backup and rollback** | Per-patch session backup + auto-rollback on verify failure |
| **Progress report** | Mandatory 14-item report for AI coordination |
| **Source snapshot** | Full code snapshot for AI handoff |
| **Auto-updater** | Ed25519-signed updates with cold-patch helper |

### AI Coordination Design

This tool is built as an **AI Coordination Tool** with 3 layers:

| Layer | Mechanism | Role |
|---|---|---|
| **Layer 1** | `progress_report` in each patch | Ephemeral AI handoff context |
| **Layer 2** | `profiles/*.md` files | Persistent state between sessions |
| **Layer 3** | `.apply_patch/project.json` | Per-project config |

---

## 2. Installation

### End Users

1. Run `ApplyPatchCode_Setup_v1.0.0.exe`
2. Follow wizard (requires admin for Program Files)
3. Installs to `C:\Program Files\ApplyPatchCode\`

### Developers

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install pytest ruff mypy nuitka ordered-set zstandard
```

### Build

```powershell
python build.py
# Output: dist/ApplyPatchCode.exe (~15-25 MB)
```

---

## 3. Quick Start

### GUI (recommended)

```powershell
apply_patch_gui
```

Workflow:
1. **Project**: select project folder
2. **Patches**: select folder containing `.json` patches
3. **Available Patches**: shows list with status
4. **Execute Selected Patch**: apply highlighted patch
5. **Snapshot Source**: generate `profiles/source_snapshot.json`

### CLI

```powershell
# Validate a patch
python -m apply_patch validate Patches/Patch_XX.json

# Dry-run (no writes)
python -m apply_patch apply Patches/Patch_XX.json --project . --dry-run

# Apply for real
python -m apply_patch apply Patches/Patch_XX.json --project .

# Auto: dry-run first, then apply if OK
python -m apply_patch auto Patches/Patch_XX.json --project .

# Snapshot source code
python -m apply_patch snapshot-source --project .
```

---

## 4. CLI Reference

| Command | Description |
|---|---|
| `validate <patch.json>` | Validate structure only |
| `apply <patch.json> --project PATH --dry-run` | Apply patch |
| `auto <patch.json> --project PATH` | Dry-run then apply |
| `detect --project PATH` | Show detected project |
| `languages` | List registered language validators |
| `list-backups --project PATH` | List backups |
| `rollback <backup.meta.json>` | Restore file from backup |
| `init-project --path PATH` | Create `.apply_patch/project.json` |
| `snapshot-source --project PATH` | Generate source snapshot |
| `forget` | Remove legacy project memory |

**Global flags**: `-v/--verbose`, `-q/--quiet`, `--json`, `--log-file`

---

## 5. GUI Guide

### Layout

```
+--------------------------------------------------+
| Project:  [________________________] [Browse]     |
| Patches:  [________________________] [Browse]     |
|                                                   |
| Available Patches:                               |
| +----------------------+----------------------+  |
| |      Patch File      |        Status        |  |
| +----------------------+----------------------+  |
| | Patch_30_TEST.json   | Patched              |  |
| | Patch_31_TEST.json   | Patch failed         |  |
| | Patch_32_TEST.json   | Not Patched          |  |
| +----------------------+----------------------+  |
|                                                   |
| [Execute Selected Patch]  [Snapshot Source]      |
|                                                   |
| Terminal:                                        |
| +----------------------------------------------+ |
| | [INFO] Session restored...                   | |
| | [INFO] Patch applied successfully            | |
| +----------------------------------------------+ |
+--------------------------------------------------+
```

### 5 Status Values

| Status | Meaning |
|---|---|
| `Not Patched` | Never applied |
| `Patching...` | Currently running (transient) |
| `Patched` | Applied successfully, file unchanged since |
| `Patched (file modified)` | Applied, but patch file was modified since |
| `Patch failed` | Last attempt failed |

### Features

- **Hover effects**: buttons change color when mouse enters
- **Auto-refresh**: polling every 1.5s, debounced 0.5s
- **Session memory**: restores last project/patches path
- **Thread-safe**: worker thread + main-thread polling

---

## 6. Patch Format

See `docs/PATCH_AUTHOR_GUIDE.md` for complete specification.

Quick reference:

```json
{
  "schema_version": "2.0",
  "patch_id": "PATCH-YYYY-NNN",
  "progress_report": { ... },
  "patches": [
    {
      "file": "path/to/file.py",
      "operations": [
        {"type": "replace", "old_text": "old", "new_text": "new"}
      ],
      "verify_after": {
        "contains": ["expected"],
        "not_contains": ["forbidden"]
      }
    }
  ]
}
```

---

## 7. Progress Report

### Mandatory 3 Fields

```json
"progress_report": {
  "task_name": "Short task name",
  "objective_and_scope": "Detailed goal and scope",
  "mandatory_info_for_next_ai": "Critical context for next AI"
}
```

### Optional 11 Fields

| Field | Purpose |
|---|---|
| `completed_functions` | List of `{id, name, completed_at}` |
| `uncompleted_functions` | List of `{id, name, reason}` |
| `files_created` | List of new file paths |
| `files_modified_or_deleted` | List of `{path, action}` |
| `significant_changes` | List of important changes |
| `api_and_interface_changes` | List of `{file, kind, change}` |
| `affected_modules` | List of module names |
| `source_tree` | ASCII tree of directory structure |
| `test_results` | List of `{command, result}` |
| `remaining_issues_and_risks` | List of `{id, severity, description}` |
| `technical_decisions` | List of `{id, decision, rationale}` |
| `proposed_next_work` | List of `{id, name, priority}` |

### Where It's Stored

- **In patch JSON**: source of truth, validated by schema
- **In `patch_history.json`**: snapshot preserved after apply

---

## 8. Backup and Rollback

### Backup Location

```
<project>/apply_patch_backup/
  <patch_id>_<timestamp>/
    _session.json
    src/main.py
    src/main.py.meta.json
```

**One session per patch apply**. All files share the same session directory.

### Session Metadata (`_session.json`)

```json
{
  "schema_version": "1.0",
  "session_id": "PATCH-2026-032-TEST-REGEX_20261109T063844Z",
  "patch_id": "PATCH-2026-032-TEST-REGEX",
  "project_id": "apply_patch_tool",
  "finished_at": "2026-11-09T06:38:44+00:00",
  "file_count": 1,
  "success": true,
  "files": [
    {"file": "docs/TEST_REGEX_OUTPUT.txt", "status": "ok", "backup_path": null}
  ]
}
```

### Rollback Behavior

When `rollback_on_verify_failure: true`:

1. **Phase 1**: Pre-flight backup all existing files
2. **Phase 2**: Apply operations, track created files/dirs
3. **Phase 3 (on failure)**:
   - Restore files from backups
   - **Delete new files created**
   - **Delete new dirs created** (only if empty)
   - Write session metadata with `success: false`

---

## 9. Source Snapshot

### Purpose

Generate full source code snapshot for AI handoff, so next AI can read entire codebase without scanning filesystem.

### Output (3 files)

All three files are written to `<project>/profiles/`:

| File | Size limit | Purpose |
|---|---|---|
| `source_tree.md` | ~10-30 KB | ASCII tree + per-file metadata (path, language, size, sha256 prefix). Read FIRST for orientation. |
| `source_content.<ext>` | 400 KB total, 100 KB per-file | Full content of all source files. Extension follows project's dominant language (`.py`, `.js`, `.ts`, ...). |
| `source_progress.md` | 200 KB | Concatenation of 10 `profiles/*.md` files in fixed order (00 to 09). Shows project status. |

The content file extension is chosen from `project_type` in `.apply_patch/project.json`:

| project_type | Extension | Comment style |
|---|---|---|
| `python` | `.py` | `#` |
| `javascript` | `.js` | `//` |
| `typescript` | `.ts` | `//` |
| `java` | `.java` | `//` |
| `go` | `.go` | `//` |
| `rust` | `.rs` | `//` |
| `c` / `cpp` / `csharp` | `.c` / `.cpp` / `.cs` | `//` |
| `php` / `swift` / `kotlin` | `.php` / `.swift` / `.kt` | `//` |
| `ruby` / `shell` | `.rb` / `.sh` | `#` |
| `json` | `.json` | `//` |
| `xml` | `.xml` | `<!-- -->` |
| `plain` (fallback) | `.txt` | `#` |

### Content file format

```
# =============================================================================
# SOURCE CONTENT SNAPSHOT
# Project: my_project
# Dominant language: python  |  Content file: source_content.py
# =============================================================================

# -----------------------------------------------------------------------------
# FILE: src/engine.py
# LANGUAGE: python  |  SIZE: 24567 bytes  |  SHA-256: abc123def456...
# -----------------------------------------------------------------------------
from __future__ import annotations
# ... full file content ...

# -----------------------------------------------------------------------------
# FILE: pyproject.toml
# LANGUAGE: toml  |  SIZE: 892 bytes  |  SHA-256: 789ghi012...
# NOTE: non-python content commented-out with '#'
# -----------------------------------------------------------------------------
# [build-system]
# requires = ["setuptools>=68"]
```

Non-dominant content is commented out using the dominant language's comment marker so the content file remains syntactically valid.

### Exclusions

| Category | Excluded |
|---|---|
| **Dirs** | `.git`, `.hg`, `.svn`, `.venv`, `venv`, `env`, `.tox`, `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `node_modules`, `build`, `dist`, `release`, `.apply_patch`, `apply_patch_backup`, `.idea`, `.vscode`, `target`, `bin`, `obj`, `.next`, `.nuxt`, `out`, `.cache` |
| **Garbage dirs** | `Doccuments`/`doccuments`, `Documents`/`documents`, `Logs`/`logs`, `CrashReports`/`crashreports`/`crash_reports` |
| **Tool dirs** | `profiles`, `Patches`/`patches` (avoid circular inclusion of tool output) |
| **Files** | `.DS_Store`, `Thumbs.db`, `desktop.ini`, `package-lock.json`, `yarn.lock`, `poetry.lock`, `Pipfile.lock` |
| **Glob patterns** | `*.log`, `*.tmp`, `*.bak`, `*.swp`, `*.swo`, `nuitka-crash-report.xml`, `source_content.*`, `source_tree.md`, `source_snapshot.json` |
| **Binary** | Files with null bytes in first 8 KB |
| **Non-UTF-8** | Files that fail UTF-8 / UTF-8-sig decoding |

### Limits

| Limit | Value | Behavior |
|---|---|---|
| **Total content** | 400 KB | Files added in priority order (code > config > scripts > UI > docs). Once exceeded, remaining files go to `Skipped Files`. |
| **Per-file** | 100 KB | Content truncated with `TRUNCATED` marker. Original size and SHA-256 preserved. |
| **Progress** | 200 KB | Files appended in fixed order. If a file overflows, truncated with warning. |
| **File count warning** | 200 | Warning logged if more than 200 files are scanned. |

### Priority order (when total > 400 KB)

1. **Code** — `.py`, `.js`, `.ts`, `.java`, `.kt`, `.go`, `.rs`, `.c`, `.cpp`, `.cs`, `.php`, `.rb`, `.swift`
2. **Config** — `.json`, `.yaml`, `.toml`, `.xml`, `.ini`, `.cfg`, `.conf`
3. **Scripts** — `.sql`, `.sh`, `.bash`, `.ps1`, `.bat`, `.cmd`
4. **UI** — `.html`, `.css`, `.scss`, `.vue`, `.svelte`
5. **Docs** — `.md`, `.rst`, `.txt`, `.adoc`

Within each priority group, files are ordered alphabetically by path.

### Handoff workflow

When handing off to a new AI, provide:

1. **Full source code** (`src/`, `tests/`)
2. **10 profile files** (`profiles/00_*.md` to `09_AI_HANDOFF.md`) — project status
3. **`profiles/source_tree.md`** — file map
4. **`profiles/source_content.<ext>`** — full code
5. **`profiles/source_progress.md`** — status summary

The receiving AI reads in this order: `source_progress.md`, `source_tree.md`, `source_content.<ext>` (targeted lookups).

### Profiles auto-sync

After every successful `apply` (non-dry-run), the tool automatically rebuilds the `AUTO-GENERATED` section in all 10 `profiles/*.md` files from `.apply_patch/patch_history.json`.

- **Gốc content above the marker is preserved 100%** — never overwritten.
- Auto section aggregates: patch history, affected modules, technical decisions, task tracker, changelog, AI handoff status.
- **Idempotent**: rerunning produces the same output (only timestamp differs).
- **Dedup**: items already present in gốc content are not duplicated.
- **Disable**: set `APPLY_PATCH_NO_PROGRESS_UPDATE=1` environment variable.
- **Best-effort**: sync failure never rolls back a successful patch.

### CLI

```powershell
python -m apply_patch snapshot-source --project .
python -m apply_patch snapshot-source --project . --output-dir custom_profiles/
python -m apply_patch snapshot-source --project . --json
```

### Disable progress auto-update

```powershell
$env:APPLY_PATCH_NO_PROGRESS_UPDATE = "1"
python -m apply_patch apply Patches/Patch_XX.json --project .
```

---

## 10. AI Handoff Protocol

### For AI Receiving a Project

**Step 1: Read documentation**

```powershell
cat docs/DOCUMENTATION.md
cat docs/PATCH_AUTHOR_GUIDE.md
cat profiles/00_PROJECT_OVERVIEW.md
cat profiles/09_AI_HANDOFF.md
cat profiles/source_snapshot.json   # If exists
```

**Step 2: Verify baseline**

```powershell
pytest -q                    # Expect: 124 passed
ruff check src/ tests/       # Expect: All checks passed
```

**Step 3: Continue work**

- Follow `docs/PATCH_AUTHOR_GUIDE.md`
- Always include `progress_report` with 3 core fields
- Run `pytest -q` before/after
- Update `profiles/09_AI_HANDOFF.md` at end

### For AI Delivering a Project

1. Write final `profiles/09_AI_HANDOFF.md` (6 sections)
2. Generate `profiles/source_snapshot.json`
3. Update `profiles/07_TASK_TRACKER.md` and `08_CHANGELOG.md`
4. Run all tests: `pytest -q`
5. Update `profiles/04_DATABASE_DESIGN.md` if data model changed

---

## 11. Troubleshooting

### Application does not start

Run from PowerShell to reveal traceback:

```powershell
cd "C:\Program Files\ApplyPatchCode"
.\ApplyPatchCode.exe
```

Common causes: missing VC++ Redistributable, Tcl/Tk not bundled.

### "Path must not contain '..'"

Schema blocked path traversal. Use project-relative paths without `..`.

### "File is not UTF-8 encoded"

Re-save patch file as UTF-8 (no BOM).

### "File appears to be binary"

Target has null bytes. Only text files supported.

### "old_text not found"

Literal didn't match. Check exact indentation, line endings, whitespace.

### "Regex did not match"

Possible causes:
- **Backreference syntax**: use `\1 \2 \3` (Python) not `$1 $2 $3` (JS)
- **Content already transformed**: previous operation changed text
- **Escaping**: pattern with `\d` needs `"\\d"` in JSON

### "verify_after failed"

Check expected strings carefully — exact substring, case-sensitive.

### Patch applied but content wrong

Check if duplicate operations — each op runs on transformed content of previous.

### Build fails: "Microsoft Visual C++ 14.0 required"

Install VC++ Build Tools from visualstudio.microsoft.com.

---

## 12. Development

### Project Structure

```
apply_patch_tool/
  src/apply_patch/
    __init__.py           # Version, app name
    __main__.py           # python -m apply_patch
    cli.py                # CLI entry point
    engine.py             # Core patch executor
    schema.py             # JSON parsing + validation
    context.py            # Exceptions + dataclasses
    discovery.py          # Project detection
    backup.py             # Backup and rollback
    patch_history.py      # Track applied patches
    profiles.py           # Auto-init profiles/
    safety.py             # Path safety (safe_join)
    verification.py       # Content verification
    source_snapshot.py    # Source code snapshot
    core/schemas/patch_v2.json
    gui/                  # Tkinter GUI
    languages/            # Multi-language validators
    updater/              # Ed25519 updater
  tests/                  # pytest suite (124 tests)
  profiles/               # AI handoff docs
  Patches/                # Patch JSON files
  assets/                 # Icon, images
  build.py                # Nuitka build
  installer_config.iss    # Inno Setup
  pyproject.toml          # Package metadata
```

### Running Tests

```powershell
pytest -q                          # All tests
pytest tests/test_engine.py -v     # Specific file
pytest -k "regex"                  # Match "regex"
pytest --cov=src/apply_patch       # With coverage
```

### Code Quality

```powershell
ruff check src/ tests/             # Linter
ruff check --fix src/ tests/       # Auto-fix
mypy src/ --strict                 # Type checker
```

### Release Checklist

- [ ] All tests pass: `pytest -q`
- [ ] Ruff clean: `ruff check src/ tests/`
- [ ] Version bumped in `src/apply_patch/__init__.py`
- [ ] `profiles/09_AI_HANDOFF.md` updated
- [ ] `docs/DOCUMENTATION.md` updated
- [ ] `python build.py` succeeds
- [ ] Test exe on clean machine (no Python)
- [ ] `iscc installer_config.iss` succeeds

---

## Appendix A: Data Locations

| Data | Location |
|---|---|
| Project manifest | `<project>/.apply_patch/project.json` |
| Patch history | `<project>/.apply_patch/patch_history.json` |
| Backup sessions | `<project>/apply_patch_backup/<patch_id>_<timestamp>/` |
| Profiles | `<project>/profiles/*.md` |
| Source snapshot | `<project>/profiles/source_snapshot.json` |
| User settings | `%APPDATA%\ApplyPatchCode\settings.json` |
| Downloads | `%APPDATA%\ApplyPatchCode\downloads\` |
| Logs | `%APPDATA%\ApplyPatchCode\logs\` |

## Appendix B: Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Error (validation, apply, config) |
| `130` | User cancelled (Ctrl+C) |

---

**End of documentation.**