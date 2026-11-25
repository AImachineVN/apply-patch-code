# Patch Author Guide

**For**: AI assistants, developers, DevOps writing patches  
**Version**: 1.0.0  
**Last updated**: 2026-11-09

---

## Table of Contents

1. [5 Golden Rules](#1-5-golden-rules)
2. [Patch JSON Structure](#2-patch-json-structure)
3. [6 Operation Types](#3-6-operation-types)
4. [Regex Deep Dive](#4-regex-deep-dive)
5. [Progress Report](#5-progress-report)
6. [Verify After](#6-verify-after)
7. [Common Mistakes](#7-common-mistakes)
8. [Complete Example](#8-complete-example)
9. [Pre-flight Checklist](#9-pre-flight-checklist)

---

## 1. 5 Golden Rules

### 🔴 RULE 1: Python Regex Backreference is `\1 \2 \3`

| ✅ Correct (Python) | ❌ Wrong (JS/Perl) |
|---|---|
| `"replacement": "\\1-\\2-\\3"` | `"replacement": "$1-$2-$3"` |
| Output: `012-345-6789` | Output: `$1-$2-$3` (literal) |

**Why**: Apply Patch Code uses Python `regex` library, not JavaScript.

### 🔴 RULE 2: No PCRE Escapes

| Escape | Supported? | Alternative |
|---|---|---|
| `\U` (uppercase) | ❌ No | Use literal or Python callback |
| `\L` (lowercase) | ❌ No | Use literal |
| `\E` (end case) | ❌ No | N/A |

**Wrong**:
```json
{"pattern": "#[a-f0-9]{6}", "replacement": "#\\U$1"}
```

**Right**:
```json
{"pattern": "#[a-f0-9]{6}", "replacement": "#A3F5C8"}
```

### 🟡 RULE 3: No Duplicate Operations

Each operation runs on **transformed content** from previous operations.

**Wrong** (duplicate → 2nd fails):
```json
[
  {"type": "replace_regex", "pattern": "(\\d{3})(\\d{3})(\\d{4})", "replacement": "\\1-\\2-\\3"},
  {"type": "replace_regex", "pattern": "(\\d{3})(\\d{3})(\\d{4})", "replacement": "\\1-\\2-\\3"}
]
```
After Op 1: `012-345-6789`. Op 2 pattern `\d{3}\d{3}\d{4}` won't match (has dashes).

### 🟡 RULE 4: `skip_syntax_check` for Non-Code Files

| Extension | `skip_syntax_check`? |
|---|---|
| `.py`, `.pyw` | ❌ No |
| `.json` | ❌ No |
| `.xml`, `.svg` | ❌ No |
| `.js`, `.ts` (external advisory) | ❌ No |
| **`.txt`, `.md`, `.log`, `.csv`** | ✅ **YES** |
| **File without extension** | ✅ **YES** |

**Why**: `.txt` files fall back to `project_default_language` (often `"python"`) → Python syntax check fails.

### 🟢 RULE 5: Always Use `verify_after`

```json
"verify_after": {
  "contains": ["expected string 1", "expected string 2"],
  "not_contains": ["forbidden string 1"]
}
```

- If verify fails → file not written (safe)
- If `rollback_on_verify_failure: true` → rollback triggered

---

## 2. Patch JSON Structure

### Minimal Valid Patch

```json
{
  "schema_version": "2.0",
  "patch_id": "PATCH-YYYY-NNN",
  "progress_report": {
    "task_name": "Task name",
    "objective_and_scope": "Goal",
    "mandatory_info_for_next_ai": "Context"
  },
  "patches": [
    {
      "file": "path/to/file.py",
      "operations": [
        {"type": "replace", "old_text": "old", "new_text": "new"}
      ]
    }
  ]
}
```

### Top-Level Fields

| Field | Required | Description |
|---|---|---|
| `schema_version` | ✅ | `"1.0"` or `"2.0"` |
| `patch_id` | ✅ | Unique identifier (or use `id` / `related_issue`) |
| `progress_report` | ✅ | 3 core fields required (v2.0 only) |
| `patches` | ✅ | Non-empty array of file/directory patches |
| `description` | ❌ | Human-readable description |
| `author` | ❌ | Author name |
| `date` | ❌ | ISO date |
| `target_projects` | ❌ | List of project IDs (or `["*"]`) |
| `project_types` | ❌ | List of project types |
| `rollback_on_verify_failure` | ❌ | Default `false` |

### File Patch Fields

| Field | Required | Description |
|---|---|---|
| `file` | ✅ | Relative path from project root |
| `operations` | ✅ | Non-empty array |
| `create_if_missing` | ❌ | Create file if not exists (default `false`) |
| `optional` | ❌ | Skip if not exists (default `false`) |
| `skip_syntax_check` | ❌ | Default `false` |
| `encoding` | ❌ | Default `"utf-8"` |
| `language` | ❌ | Explicit language override |
| `verify_markers` | ❌ | Strings that must exist before patch |
| `verify_after` | ❌ | Content rules after patch |

### Directory Patch

```json
{
  "type": "create_directory",
  "path": "new_folder/subfolder"
}
```

---

## 3. 6 Operation Types

### Op 1: `replace` — Replace literal text

```json
{
  "type": "replace",
  "old_text": "DEBUG = True",
  "new_text": "DEBUG = False",
  "occurrence": 1
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `old_text` | ✅ | — | Literal text to find |
| `new_text` | ✅ | — | Replacement |
| `occurrence` | ❌ | `1` | `1` = first, `-1` = all |

**Errors**:
- `old_text` not found → `OperationError`
- `occurrence` invalid → `OperationError`

### Op 2: `insert_after` — Insert after line containing anchor

```json
{
  "type": "insert_after",
  "anchor": "DEBUG = False",
  "new_text": "# This line added\n"
}
```

- Anchor must be **substring of a single line**
- Inserts after the **entire line** containing anchor
- `new_text` automatically gets `\n` if not ending with one

### Op 3: `insert_before` — Insert before line containing anchor

```json
{
  "type": "insert_before",
  "anchor": "def main():",
  "new_text": "def setup():\n    pass\n"
}
```

### Op 4: `delete` — Delete literal text

```json
{
  "type": "delete",
  "old_text": "# TODO: remove this later\n"
}
```

Deletes **all occurrences** of `old_text`.

### Op 5: `replace_regex` — Regex replacement

```json
{
  "type": "replace_regex",
  "pattern": "(\\d{3})(\\d{3})(\\d{4})",
  "replacement": "\\1-\\2-\\3",
  "flags": ""
}
```

| Field | Required | Description |
|---|---|---|
| `pattern` | ✅ | Python regex pattern |
| `replacement` | ✅ | Uses `\1 \2 \3` (Python syntax) |
| `flags` | ❌ | `i` (ignorecase), `m` (multiline), `s` (dotall), `x` (verbose) |

**Timeout**: 10 seconds (kills computation on ReDoS).

**Errors**:
- Invalid pattern → `OperationError`
- No match → `OperationError`
- Timeout → `OperationError`

### Op 6: `write_content` — Write entire file

```json
{
  "type": "write_content",
  "content": "Entire file content here\n"
}
```

- Overwrites entire file
- If file doesn't exist + `create_if_missing: true` (or `write_content` is first op) → creates it
- Creates parent directories automatically

---

## 4. Regex Deep Dive

### Backreference Syntax

| Purpose | Syntax | Example |
|---|---|---|
| **Python** (use this) | `\1`, `\2`, `\3` | `"\\1-\\2"` |
| Named groups | `\g<name>` | `"\\g<year>-\\g<month>"` |
| ❌ JS/Perl | `$1`, `$2` | **DO NOT USE** |

### Flags

| Flag | Effect | Example |
|---|---|---|
| `i` | Ignorecase | `"flags": "i"` |
| `m` | `^` and `$` match line boundaries | `"flags": "m"` |
| `s` | `.` matches newlines | `"flags": "s"` |
| `x` | Verbose (ignore whitespace in pattern) | `"flags": "x"` |
| Combined | `"im"`, `"is"`, `"imsx"` | `"flags": "im"` |

### Common Patterns

| Task | Pattern | Replacement |
|---|---|---|
| Format phone | `(\d{3})(\d{3})(\d{4})` | `\1-\2-\3` |
| Extract email | `([a-z0-9]+@[a-z0-9.]+)` | `\1` |
| Trim spaces | `\s+` | `` (empty) |
| Strip line | `^.*TARGET.*$\n` (with `m`) | `` |

### ReDoS Protection

`regex` library (unlike `re`) supports **timeout**:
- Max 10 seconds per `replace_regex` operation
- If timeout → operation fails, no partial write
- Classic ReDoS patterns like `^(a+)+$` are optimized and won't hang

---

## 5. Progress Report

### Required 3

```json
"progress_report": {
  "task_name": "Short task name — what was done",
  "objective_and_scope": "Detailed goal, scope, files affected, expected outcome",
  "mandatory_info_for_next_ai": "CRITICAL context: decisions, pitfalls, how to continue, TEST or PRODUCTION"
}
```

### Optional 11

**completed_functions** (list):
```json
[{"id": "F-001", "name": "Feature A", "completed_at": "2026-11-09"}]
```

**uncompleted_functions** (list):
```json
[{"id": "F-002", "name": "Feature B", "reason": "Blocked by X"}]
```

**files_created** (list):
```json
["src/new_module.py", "docs/guide.md"]
```

**files_modified_or_deleted** (list):
```json
[
  {"path": "src/engine.py", "action": "modified"},
  {"path": "src/old.py", "action": "deleted"}
]
```

**significant_changes** (list):
```json
["Changed rollback logic to track created files", "Added source_tree field"]
```

**api_and_interface_changes** (list):
```json
[{"file": "src/api.py", "kind": "api", "change": "Signature: foo() → foo(x, y)"}]
```

**affected_modules** (list):
```json
["engine", "backup", "schema"]
```

**source_tree** (string):
```json
"source_tree": "src/\n├── apply_patch/\n│   ├── engine.py\n│   └── schema.py\n└── tests/"
```

**test_results** (list):
```json
[
  {"command": "pytest -q", "result": "124 passed"},
  {"command": "ruff check", "result": "All checks passed"}
]
```

**remaining_issues_and_risks** (list):
```json
[{"id": "RISK-001", "severity": "LOW", "description": "Known minor issue"}]
```

**technical_decisions** (list):
```json
[{"id": "TD-001", "decision": "Use regex library", "rationale": "Native re has no timeout"}]
```

**proposed_next_work** (list):
```json
[{"id": "N-001", "name": "Add feature X", "priority": "HIGH"}]
```

---

## 6. Verify After

### Format

```json
"verify_after": {
  "contains": ["string 1", "string 2"],
  "not_contains": ["forbidden 1"]
}
```

### Semantics

| Check | When | Result if fail |
|---|---|---|
| `contains` | After operations, before write | `OperationError` → no write |
| `not_contains` | After operations, before write | `OperationError` → no write |

### Best Practices

✅ **DO**:
- Check key expected strings
- Check absence of known-bad strings
- Use exact substrings (case-sensitive)

❌ **DON'T**:
- Use regex in `verify_after` (it's literal match)
- Check huge amounts of content (slow)
- Skip `verify_after` for production patches

---

## 7. Common Mistakes

### ❌ Mistake 1: `$1` instead of `\1`

```json
// WRONG
{"replacement": "$1-$2-$3"}
// Output: Phone: $1-$2-$3 (literal)

// RIGHT
{"replacement": "\\1-\\2-\\3"}
// Output: Phone: 012-345-6789
```

### ❌ Mistake 2: `\U` for uppercase

```json
// WRONG
{"replacement": "#\\U$1"}
// Error: incomplete escape \U at position 4

// RIGHT (literal)
{"replacement": "#A3F5C8"}
```

### ❌ Mistake 3: Duplicate regex operations

```json
// WRONG
[
  {"pattern": "(\\d{3})(\\d{3})(\\d{4})", "replacement": "\\1-\\2-\\3"},
  {"pattern": "(\\d{3})(\\d{3})(\\d{4})", "replacement": "\\1-\\2-\\3"}
]
// Op 2 fails: 012-345-6789 has dashes, doesn't match \d{3}\d{3}\d{4}
```

### ❌ Mistake 4: Missing `skip_syntax_check` for `.txt`

```json
// WRONG (fails Python syntax check)
{"file": "notes.txt", "operations": [{"type": "write_content", "content": "text"}]}

// RIGHT
{
  "file": "notes.txt",
  "skip_syntax_check": true,
  "operations": [{"type": "write_content", "content": "text"}]
}
```

### ❌ Mistake 5: Backslashes in JSON

```json
// WRONG (JSON escape error)
{"pattern": "\d{3}"}

// RIGHT (double backslash)
{"pattern": "\\d{3}"}
```

### ❌ Mistake 6: Line endings

If file uses CRLF, multi-line `old_text` needs `\r\n` (not `\n`). Use single-line `old_text` or `insert_after`/`insert_before` to avoid.

### ❌ Mistake 7: Not using `create_if_missing`

```json
// WRONG (file doesn't exist → error)
{
  "file": "new_file.py",
  "operations": [{"type": "replace", "old_text": "x", "new_text": "y"}]
}

// RIGHT
{
  "file": "new_file.py",
  "create_if_missing": true,
  "operations": [{"type": "write_content", "content": "x = 1\n"}]
}
```

---

## 8. Complete Example

**Task**: Convert phone format + lowercase email + uppercase hex color.

```json
{
  "schema_version": "2.0",
  "patch_id": "PATCH-2026-032-TEST-REGEX",
  "description": "Test regex: backreference, ignorecase, literal replacement",
  "author": "Test Suite",
  "date": "2026-11-09",
  "rollback_on_verify_failure": true,
  "progress_report": {
    "task_name": "Regex Test",
    "objective_and_scope": "Test 3 regex patterns on sample data",
    "mandatory_info_for_next_ai": "Python regex uses \\1 not $1"
  },
  "patches": [
    {
      "file": "docs/TEST_REGEX_OUTPUT.txt",
      "create_if_missing": true,
      "skip_syntax_check": true,
      "operations": [
        {
          "type": "write_content",
          "content": "Phone: 0123456789\nEmail: USER@EXAMPLE.COM\nColor: #a3f5c8\n"
        },
        {
          "type": "replace_regex",
          "pattern": "(\\d{3})(\\d{3})(\\d{4})",
          "replacement": "\\1-\\2-\\3"
        },
        {
          "type": "replace_regex",
          "pattern": "[A-Z]+@[A-Z.]+",
          "replacement": "user@example.com",
          "flags": "i"
        },
        {
          "type": "replace_regex",
          "pattern": "#[a-f0-9]{6}",
          "replacement": "#A3F5C8",
          "flags": "i"
        }
      ],
      "verify_after": {
        "contains": ["012-345-6789", "user@example.com", "#A3F5C8"],
        "not_contains": ["USER@EXAMPLE.COM", "#a3f5c8"]
      }
    }
  ]
}
```

**Result**:
```
Phone: 012-345-6789
Email: user@example.com
Color: #A3F5C8
```

---

## 9. Pre-flight Checklist

Before apply:

- [ ] `schema_version: "2.0"`
- [ ] Unique `patch_id`
- [ ] `progress_report` with 3 core fields
- [ ] `patches` array non-empty
- [ ] No `$1` in regex replacements (use `\1`)
- [ ] No `\U` / `\L` escapes
- [ ] No duplicate operations
- [ ] `skip_syntax_check: true` for non-code files
- [ ] `verify_after` for production patches
- [ ] `create_if_missing: true` for new files
- [ ] Validated with `python -m apply_patch validate <file>`

### Pre-flight Commands

```powershell
# 1. Validate schema
python -m apply_patch validate Patches/Patch_XX.json

# 2. Dry-run
python -m apply_patch apply Patches/Patch_XX.json --project . --dry-run

# 3. Apply for real
python -m apply_patch apply Patches/Patch_XX.json --project .
```

---

**End of Patch Author Guide.**

**Remember**: Python regex uses `\1 \2 \3`, not `$1 $2 $3`.