# AI Patch Creation Guide — 100% Standard Template

**For**: AI assistants writing Apply Patch Code JSON patches  
**Version**: 1.0.0  
**Last updated**: 2026-11-09  
**Purpose**: Step-by-step instructions for AI to create valid, production-ready patch JSON

---

## 🎯 READ THIS FIRST

You are an AI assistant about to write a patch JSON file for **Apply Patch Code**.

**Before you write a single line**, understand these 3 critical facts:

1. **Python regex syntax** — backreference is `\1 \2 \3`, NOT `$1 $2 $3` (JS syntax)
2. **No PCRE escapes** — `\U`, `\L`, `\E` don't work in Python regex
3. **`progress_report` is MANDATORY** — patch will be rejected without 3 core fields

**If you skip these, your patch will fail.**

---

## 📋 STEP-BY-STEP PROCESS

### Step 1: Understand the Task

Answer these questions before writing:

| Question | Example Answer |
|---|---|
| What file(s) need to change? | `src/main.py`, `config.json` |
| What is the exact content BEFORE? | `DEBUG = True` |
| What is the exact content AFTER? | `DEBUG = False` |
| Do files exist or need creating? | Exists / New file |
| Are there edge cases? | File may not exist → use `optional` or `create_if_missing` |
| How to verify success? | `contains: ["DEBUG = False"]` |

### Step 2: Copy the Master Template

Copy the template from **Section 8** below. Do NOT write from scratch.

### Step 3: Fill in Fields (Follow Order)

Fill in this exact order to avoid missing required fields:

1. **Top-level**: `schema_version`, `patch_id`, `description`, `author`, `date`
2. **Progress report**: 3 core fields (task_name, objective_and_scope, mandatory_info_for_next_ai)
3. **Patch list**: `patches` array (files + operations)
4. **Verify**: `verify_after` for each file

### Step 4: Apply the 5 Golden Rules (Section 2)

Run through the 5 rules before saving.

### Step 5: Validate

Run:
```powershell
python -m apply_patch validate Patches/Patch_YY_YourName.json
```

**If validation fails, fix the error before proceeding.**

### Step 6: Dry-Run

```powershell
python -m apply_patch apply Patches/Patch_YY_YourName.json --project . --dry-run
```

**If dry-run fails, review the operations. Common causes:**
- `old_text` not found → check exact content (whitespace, line endings)
- Regex didn't match → check pattern/backreference syntax
- File not found → add `create_if_missing: true`

### Step 7: Apply for Real

Only if dry-run passed:
```powershell
python -m apply_patch apply Patches/Patch_YY_YourName.json --project .
```

---

## 1. Top-Level Structure (Required Fields)

Every patch JSON MUST have these 5 top-level fields:

```json
{
  "schema_version": "2.0",
  "patch_id": "PATCH-YYYY-NNN-UNIQUE",
  "description": "Short description",
  "progress_report": { /* mandatory 3 fields */ },
  "patches": [ /* non-empty array */ ]
}
```

### Field Rules

| Field | Value | Rules |
|---|---|---|
| `schema_version` | `"2.0"` | MUST be exactly `"2.0"` (or `"1.0"` for legacy — avoid) |
| `patch_id` | Unique ID | Format: `PATCH-YYYY-NNN-UNIQUE` (e.g., `PATCH-2026-045-FIX-BUG`) |
| `description` | String | Short human-readable |
| `progress_report` | Object | See Section 3 |
| `patches` | Array | At least 1 file/directory patch |

### Optional Top-Level Fields

| Field | Default | When to Use |
|---|---|---|
| `author` | `""` | Always set (your AI name) |
| `date` | `""` | Always set (YYYY-MM-DD) |
| `target_projects` | `[]` | Use `["*"]` for all projects |
| `project_types` | `[]` | Use `["*"]` for all types |
| `rollback_on_verify_failure` | `false` | **Set to `true` for production patches** |

### Patch File Naming Convention

Files must follow this pattern:

```
Patch_<x>_<TASK_NAME>.json
```

| Part | Rules |
|---|---|
| `<x>` | Sequence number starting from `1` (1, 2, 3, ...) |
| `<TASK_NAME>` | UPPER_SNAKE_CASE describing what the patch does |

**Examples**:
- `Patch_1_SOURCE_SNAPSHOT_MD.json`
- `Patch_2_SOURCE_SNAPSHOT_FIX_EXCLUDES.json`
- `Patch_10_DOCUMENTATION_UPDATE.json`

**Why**:
- `<x>` makes apply order obvious (file explorer sorts naturally)
- `<TASK_NAME>` makes intent clear without opening the file
- Matches the `patch_id` convention: `PATCH-YYYY-NNN-<TASK_NAME>`

---

## 2. 🚨 5 GOLDEN RULES (MANDATORY)

### RULE 1: Python Regex Backreference is `\1 \2 \3`

**ALWAYS USE PYTHON SYNTAX:**

| ✅ CORRECT | ❌ WRONG |
|---|---|
| `"replacement": "\\1-\\2-\\3"` | `"replacement": "$1-$2-$3"` |
| Output: `012-345-6789` | Output: `$1-$2-$3` (literal, NOT what you want) |

**Why**: Apply Patch Code uses Python `regex` library. JS/Perl syntax `$1` will print literally.

**Memory trick**: "Python uses backslash `\`, JS uses dollar `$`. We use Python."

### RULE 2: No PCRE Escapes

| ❌ NOT SUPPORTED | ✅ USE INSTEAD |
|---|---|
| `\U` (uppercase) | Literal value: `"#A3F5C8"` |
| `\L` (lowercase) | Literal value: `"user@example.com"` |
| `\E` (end case) | N/A |

**Example**:
```json
// ❌ WRONG — fails with "incomplete escape \U"
{"pattern": "#[a-f0-9]{6}", "replacement": "#\\U$1"}

// ✅ RIGHT — literal replacement
{"pattern": "#[a-f0-9]{6}", "replacement": "#A3F5C8"}
```

### RULE 3: No Duplicate Operations

**Each operation runs on the TRANSFORMED content of previous operations.**

```json
// ❌ WRONG — Op 2 will fail
[
  {"type": "replace_regex", "pattern": "(\\d{3})(\\d{3})(\\d{4})", "replacement": "\\1-\\2-\\3"},
  {"type": "replace_regex", "pattern": "(\\d{3})(\\d{3})(\\d{4})", "replacement": "\\1-\\2-\\3"}
]
```

After Op 1: `012-345-6789` (has dashes).  
Op 2: pattern `\d{3}\d{3}\d{4}` won't match `012-345-6789` because of the dashes.

**Golden rule**: Each operation should transform DIFFERENT content, or if same content, ensure pattern still matches after previous transformation.

### RULE 4: `skip_syntax_check` for Non-Code Files

| File Extension | `skip_syntax_check`? |
|---|---|
| `.py`, `.pyw` | ❌ No (Python built-in validator) |
| `.json` | ❌ No (JSON built-in validator) |
| `.xml`, `.svg` | ❌ No (XML built-in validator) |
| `.js`, `.ts` | ❌ No (external advisory, won't block) |
| **`.txt`, `.md`, `.log`, `.csv`, `.yml`** | ✅ **YES** |
| **No extension** | ✅ **YES** |

**Why**: Non-code files fall back to `project_default_language` (often `python`) → Python syntax check fails on text content.

### RULE 5: Always Use `verify_after`

```json
"verify_after": {
  "contains": ["expected string 1", "expected string 2"],
  "not_contains": ["forbidden string 1"]
}
```

**Why**:
- Catches bugs BEFORE file is written
- Triggers rollback if `rollback_on_verify_failure: true`
- Prevents corrupted output

**For production patches**: ALWAYS include `verify_after`.

---

## 3. Progress Report (MANDATORY 3 + Optional 11)

### Required 3 Fields (MUST have all)

```json
"progress_report": {
  "task_name": "Short task name — what was done",
  "objective_and_scope": "Detailed goal, scope, files affected, expected outcome",
  "mandatory_info_for_next_ai": "CRITICAL context: decisions, pitfalls, how to continue"
}
```

| Field | Length | Content |
|---|---|---|
| `task_name` | 10-100 chars | Short title |
| `objective_and_scope` | 50-500 chars | Goal + scope + files + expected outcome |
| `mandatory_info_for_next_ai` | 50-1000 chars | Decisions + pitfalls + how to continue + TEST/PRODUCTION tag |

### Optional 11 Fields (Use for production)

| Field | Type | Example |
|---|---|---|
| `completed_functions` | `[{id, name, completed_at}]` | `[{"id": "F-001", "name": "Fix bug", "completed_at": "2026-11-09"}]` |
| `uncompleted_functions` | `[{id, name, reason}]` | `[{"id": "F-002", "name": "Test", "reason": "Pending"}]` |
| `files_created` | `[string]` | `["src/new.py"]` |
| `files_modified_or_deleted` | `[{path, action}]` | `[{"path": "src/main.py", "action": "modified"}]` |
| `significant_changes` | `[string]` | `["Changed API signature"]` |
| `api_and_interface_changes` | `[{file, kind, change}]` | `[{"file": "src/api.py", "kind": "api", "change": "foo() → foo(x)"}]` |
| `affected_modules` | `[string]` | `["engine", "schema"]` |
| `source_tree` | String (ASCII tree) | `"src/\n├── a.py\n└── b.py"` |
| `test_results` | `[{command, result}]` | `[{"command": "pytest -q", "result": "124 passed"}]` |
| `remaining_issues_and_risks` | `[{id, severity, description}]` | `[{"id": "R-1", "severity": "LOW", "description": "Minor"}]` |
| `technical_decisions` | `[{id, decision, rationale}]` | `[{"id": "TD-1", "decision": "Use X", "rationale": "Because Y"}]` |
| `proposed_next_work` | `[{id, name, priority}]` | `[{"id": "N-1", "name": "Add tests", "priority": "HIGH"}]` |

---

## 4. File Patch Structure

Each item in `patches` array is either:

### A) File Patch

```json
{
  "file": "relative/path/from/project/root.py",
  "create_if_missing": false,
  "optional": false,
  "skip_syntax_check": false,
  "encoding": "utf-8",
  "operations": [ /* see Section 5 */ ],
  "verify_after": { /* see Rule 5 */ }
}
```

### B) Directory Patch

```json
{
  "type": "create_directory",
  "path": "relative/path/to/new/folder"
}
```

### Field Rules

| Field | Required | Default | When to Use |
|---|---|---|---|
| `file` | ✅ | — | Relative path (no `..`, no absolute) |
| `type` | For dir | — | `"create_directory"` |
| `path` | For dir | — | Relative folder path |
| `operations` | ✅ (file) | — | At least 1 operation |
| `create_if_missing` | ❌ | `false` | Set `true` for new files |
| `optional` | ❌ | `false` | Set `true` to skip if file missing |
| `skip_syntax_check` | ❌ | `false` | See Rule 4 |
| `encoding` | ❌ | `"utf-8"` | Only change if file uses different encoding |
| `language` | ❌ | auto | Force specific language for syntax check |
| `verify_markers` | ❌ | `[]` | Pre-check strings (fail if missing) |
| `verify_after` | ❌ | none | Post-check rules (Rule 5) |

---

## 5. 6 Operation Types

### Op 1: `replace`

```json
{
  "type": "replace",
  "old_text": "DEBUG = True",
  "new_text": "DEBUG = False",
  "occurrence": 1
}
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `old_text` | ✅ | — | Literal string (exact match) |
| `new_text` | ✅ | — | Replacement string (can be empty) |
| `occurrence` | ❌ | `1` | `1` = first match, `-1` = all matches |

**Fails if**:
- `old_text` not found → `OperationError`
- `occurrence` invalid (0, negative not -1) → `OperationError`

### Op 2: `insert_after`

```json
{
  "type": "insert_after",
  "anchor": "DEBUG = False",
  "new_text": "# This line added after DEBUG\n"
}
```

| Field | Required | Notes |
|---|---|---|
| `anchor` | ✅ | Substring of ONE line (will insert after that whole line) |
| `new_text` | ✅ | Auto-gets `\n` if not ending with one |

### Op 3: `insert_before`

```json
{
  "type": "insert_before",
  "anchor": "def main():",
  "new_text": "def setup():\n    pass\n"
}
```

Same fields as `insert_after`. Inserts BEFORE the line containing anchor.

### Op 4: `delete`

```json
{
  "type": "delete",
  "old_text": "# TODO: remove this later\n"
}
```

Deletes ALL occurrences of `old_text`. **Include trailing `\n`** to remove the whole line.

### Op 5: `replace_regex`

```json
{
  "type": "replace_regex",
  "pattern": "(\\d{3})(\\d{3})(\\d{4})",
  "replacement": "\\1-\\2-\\3",
  "flags": ""
}
```

| Field | Required | Notes |
|---|---|---|
| `pattern` | ✅ | Python regex pattern |
| `replacement` | ✅ | Use `\1 \2 \3` (Python — Rule 1) |
| `flags` | ❌ | `i`, `m`, `s`, `x` or combined `"im"` |

**Fails if**:
- Invalid pattern → `OperationError`
- No match found → `OperationError`
- Timeout (>10s, ReDoS) → `OperationError`

**Escaping in JSON**:
- `\d` in regex → `"\\d"` in JSON
- `\1` in replacement → `"\\1"` in JSON
- `#` literal → `"#"` in JSON (no escape needed)

### Op 6: `write_content`

```json
{
  "type": "write_content",
  "content": "Entire file content\nLine 2\nLine 3\n"
}
```

- Overwrites whole file
- Creates parent dirs
- Auto-creates file if `create_if_missing: true` (or if this is first operation)

---

## 6. Complete Master Template

**Copy this. Fill in placeholders. Do NOT change structure.**

```json
{
  "schema_version": "2.0",
  "patch_id": "PATCH-YYYY-NNN-UNIQUE-ID",
  "description": "Short human-readable description of this patch",
  "author": "AI Assistant Name",
  "date": "2026-11-09",
  "target_projects": ["*"],
  "project_types": ["*"],
  "rollback_on_verify_failure": true,
  "progress_report": {
    "task_name": "Short task name — what was done",
    "objective_and_scope": "Detailed goal, scope, files affected, expected outcome",
    "mandatory_info_for_next_ai": "CRITICAL context: decisions, pitfalls, how to continue, TEST or PRODUCTION",
    "completed_functions": [],
    "uncompleted_functions": [],
    "files_created": [],
    "files_modified_or_deleted": [],
    "significant_changes": [],
    "api_and_interface_changes": [],
    "affected_modules": [],
    "source_tree": "",
    "test_results": [],
    "remaining_issues_and_risks": [],
    "technical_decisions": [],
    "proposed_next_work": []
  },
  "patches": [
    {
      "file": "path/to/target.py",
      "create_if_missing": false,
      "skip_syntax_check": false,
      "encoding": "utf-8",
      "operations": [
        {
          "type": "replace",
          "old_text": "exact text to find",
          "new_text": "replacement text"
        }
      ],
      "verify_after": {
        "contains": ["expected string"],
        "not_contains": ["forbidden string"]
      }
    }
  ]
}
```

---

## 7. Filled Example (Reference)

Real working patch with all mandatory fields:

```json
{
  "schema_version": "2.0",
  "patch_id": "PATCH-2026-045-DISABLE-DEBUG",
  "description": "Disable DEBUG flag in settings.py for production release",
  "author": "AI Assistant",
  "date": "2026-11-09",
  "target_projects": ["*"],
  "project_types": ["*"],
  "rollback_on_verify_failure": true,
  "progress_report": {
    "task_name": "Disable DEBUG flag for production",
    "objective_and_scope": "Change DEBUG = True to DEBUG = False in src/settings.py to prevent debug output in production. Scope: single file, single line change. Expected: production build no longer logs debug info.",
    "mandatory_info_for_next_ai": "PRODUCTION patch. If applied successfully, DEBUG will be False. Verify before deploying to production by running app and checking no debug logs appear. If rolling back, restore DEBUG = True but this should NOT be done in production.",
    "completed_functions": [
      {"id": "F-001", "name": "Replace DEBUG flag", "completed_at": "2026-11-09"}
    ],
    "uncompleted_functions": [],
    "files_created": [],
    "files_modified_or_deleted": [
      {"path": "src/settings.py", "action": "modified"}
    ],
    "significant_changes": [
      "DEBUG set to False — no debug logs in production"
    ],
    "api_and_interface_changes": [],
    "affected_modules": ["settings"],
    "source_tree": "src/\n├── settings.py\n└── main.py",
    "test_results": [
      {"command": "pytest -q", "result": "124 passed"}
    ],
    "remaining_issues_and_risks": [],
    "technical_decisions": [
      {"id": "TD-045", "decision": "Hardcode DEBUG = False", "rationale": "Env var approach would require production setup; simpler to hardcode"}
    ],
    "proposed_next_work": []
  },
  "patches": [
    {
      "file": "src/settings.py",
      "create_if_missing": false,
      "skip_syntax_check": false,
      "encoding": "utf-8",
      "operations": [
        {
          "type": "replace",
          "old_text": "DEBUG = True",
          "new_text": "DEBUG = False"
        }
      ],
      "verify_after": {
        "contains": ["DEBUG = False"],
        "not_contains": ["DEBUG = True"]
      }
    }
  ]
}
```

---

## 8. Common AI Mistakes (AVOID THESE)

### ❌ Mistake 1: Forgetting `progress_report`

```json
// WRONG — will fail validation
{
  "schema_version": "2.0",
  "patch_id": "P1",
  "patches": [...]
}
```

**Always include progress_report with 3 core fields.**

### ❌ Mistake 2: Using `$1` instead of `\1`

```json
// WRONG
{"replacement": "$1-$2-$3"}
// Output: $1-$2-$3 (literal, NOT actual values)

// RIGHT
{"replacement": "\\1-\\2-\\3"}
// Output: 012-345-6789 (actual values)
```

### ❌ Mistake 3: Using `\U` for uppercase

```json
// WRONG — Python regex error
{"replacement": "#\\U$1"}

// RIGHT — literal
{"replacement": "#A3F5C8"}
```

### ❌ Mistake 4: Not escaping backslashes in JSON

```json
// WRONG — JSON parse error
{"pattern": "\d{3}"}

// RIGHT
{"pattern": "\\d{3}"}
```

### ❌ Mistake 5: Not setting `skip_syntax_check` for text files

```json
// WRONG — will fail Python syntax check
{"file": "notes.txt", "operations": [{"type": "write_content", "content": "text"}]}

// RIGHT
{"file": "notes.txt", "skip_syntax_check": true, "operations": [{"type": "write_content", "content": "text"}]}
```

### ❌ Mistake 6: Duplicate regex operations

```json
// WRONG — 2nd op fails (already has dashes)
[
  {"pattern": "(\\d{3})(\\d{3})(\\d{4})", "replacement": "\\1-\\2-\\3"},
  {"pattern": "(\\d{3})(\\d{3})(\\d{4})", "replacement": "\\1-\\2-\\3"}
]
```

### ❌ Mistake 7: Not setting `create_if_missing` for new files

```json
// WRONG — fails if file doesn't exist
{"file": "new.py", "operations": [{"type": "replace", ...}]}

// RIGHT
{"file": "new.py", "create_if_missing": true, "operations": [{"type": "write_content", ...}]}
```

### ❌ Mistake 8: Hardcoded `occurrence` for replace

```json
// RISKY — fails if only 1 occurrence
{"type": "replace", "old_text": "x", "new_text": "y", "occurrence": 2}

// SAFE — replace first match
{"type": "replace", "old_text": "x", "new_text": "y", "occurrence": 1}
```

### ❌ Mistake 9: Forgetting to validate

**ALWAYS run**:
```powershell
python -m apply_patch validate Patches/Patch_XX.json
```

before saving.

### ❌ Mistake 10: Line ending mismatch

If file uses CRLF (Windows), `old_text` with `\n` won't match. Use single-line `old_text` or `insert_after`/`insert_before`.

---

## 9. Validation Checklist (Before Saving)

Run through this checklist:

- [ ] `schema_version` is `"2.0"`
- [ ] `patch_id` is unique (format `PATCH-YYYY-NNN-XXX`)
- [ ] `progress_report` has all 3 core fields with non-empty strings
- [ ] `patches` array is non-empty
- [ ] Each patch has `file` (or `type: "create_directory"` + `path`)
- [ ] No `$1`, `$2`, `$3` in any replacement (use `\1`, `\2`, `\3`)
- [ ] No `\U`, `\L`, `\E` in replacement
- [ ] No duplicate operations (each op transforms different content)
- [ ] `skip_syntax_check: true` for `.txt`, `.md`, `.log`, `.csv` files
- [ ] `create_if_missing: true` for new files
- [ ] `verify_after` for production patches
- [ ] `rollback_on_verify_failure: true` for production patches
- [ ] All backslashes escaped: `\d` → `"\\d"`, `\1` → `"\\1"`

### Validate Command

```powershell
python -m apply_patch validate Patches/Patch_YY_YourName.json
```

**Expected output**: `Valid patch: ...`

**If fails**: Read error message carefully, fix, retry.

---

## 10. Full Workflow Example

### Scenario

**Task**: Add a comment above `DEBUG = True` line and change it to `DEBUG = False`.

**File**: `src/settings.py`
**Content before**:
```python
# Settings
DEBUG = True
PORT = 8080
```

### Step 1: Identify operations needed

- `replace`: `DEBUG = True` → `DEBUG = False`
- `insert_after`: Add comment after new `DEBUG = False`
- OR `insert_before`: Add comment before `DEBUG = True`

**Decision**: Use `replace` for line change, `insert_after` for comment.

### Step 2: Write patch JSON

```json
{
  "schema_version": "2.0",
  "patch_id": "PATCH-2026-046-ADD-DEBUG-COMMENT",
  "description": "Disable DEBUG + add explanation comment",
  "author": "AI Assistant",
  "date": "2026-11-09",
  "target_projects": ["*"],
  "project_types": ["*"],
  "rollback_on_verify_failure": true,
  "progress_report": {
    "task_name": "Disable DEBUG + comment",
    "objective_and_scope": "Change DEBUG = True to False + add explanation comment. File: src/settings.py. Expected: DEBUG disabled for production with context.",
    "mandatory_info_for_next_ai": "PRODUCTION patch. Changes 1 line + adds 1 comment. Rollback restores DEBUG=True but should not be done in production.",
    "completed_functions": [{"id": "F-001", "name": "Disable DEBUG", "completed_at": "2026-11-09"}],
    "uncompleted_functions": [],
    "files_created": [],
    "files_modified_or_deleted": [{"path": "src/settings.py", "action": "modified"}],
    "significant_changes": ["DEBUG disabled for production"],
    "api_and_interface_changes": [],
    "affected_modules": ["settings"],
    "source_tree": "src/\n├── settings.py\n└── main.py",
    "test_results": [{"command": "pytest -q", "result": "124 passed"}],
    "remaining_issues_and_risks": [],
    "technical_decisions": [],
    "proposed_next_work": []
  },
  "patches": [
    {
      "file": "src/settings.py",
      "create_if_missing": false,
      "skip_syntax_check": false,
      "encoding": "utf-8",
      "operations": [
        {
          "type": "replace",
          "old_text": "DEBUG = True",
          "new_text": "DEBUG = False"
        },
        {
          "type": "insert_after",
          "anchor": "DEBUG = False",
          "new_text": "# DEBUG disabled for production release\n"
        }
      ],
      "verify_after": {
        "contains": ["DEBUG = False", "# DEBUG disabled for production release"],
        "not_contains": ["DEBUG = True"]
      }
    }
  ]
}
```

### Step 3: Validate

```powershell
python -m apply_patch validate Patches/Patch_2026_046_ADD_DEBUG_COMMENT.json
# → Valid patch: ...
```

### Step 4: Dry-run

```powershell
python -m apply_patch apply Patches/Patch_2026_046_ADD_DEBUG_COMMENT.json --project . --dry-run
# → Success: True (no file written)
```

### Step 5: Apply

```powershell
python -m apply_patch apply Patches/Patch_2026_046_ADD_DEBUG_COMMENT.json --project .
# → Success: True
```

### Step 6: Verify

```powershell
Get-Content src/settings.py -Raw
# → Should show DEBUG = False + comment
```

---

## 11. Regex Cheat Sheet

### Backreference Syntax

| Purpose | Syntax | JSON Example |
|---|---|---|
| First group | `\1` | `"replacement": "\\1"` |
| Second group | `\2` | `"replacement": "\\2"` |
| Named group | `\g<name>` | `"replacement": "\\g<year>"` |
| ❌ JS/Perl (WRONG) | `$1` | `"replacement": "$1"` |

### Common Patterns

| Task | Pattern | Replacement |
|---|---|---|
| Format phone | `(\d{3})(\d{3})(\d{4})` | `\1-\2-\3` |
| Format date | `(\d{4})(\d{2})(\d{2})` | `\1-\2-\3` |
| Remove spaces | `\s+` | `` (empty) |
| Match word | `\bword\b` | `replacement` |
| Match email | `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}` | `` |
| Match URL | `https?://[^\s]+` | `` |

### Flags

| Flag | Effect |
|---|---|
| `i` | Case-insensitive |
| `m` | `^` / `$` match line boundaries |
| `s` | `.` matches newlines |
| `x` | Verbose (ignore whitespace in pattern) |

**Combine**: `"flags": "im"` (ignorecase + multiline)

---

## 12. When to Use Each Operation

| Task | Operation |
|---|---|
| Change exact text | `replace` |
| Change exact text (multiple places) | `replace` with `occurrence: -1` |
| Change text using pattern | `replace_regex` |
| Insert after a specific line | `insert_after` |
| Insert before a specific line | `insert_before` |
| Remove lines | `delete` |
| Rewrite whole file | `write_content` |
| Create new file | `write_content` + `create_if_missing: true` |
| Create new folder | `create_directory` |

---

## 13. Safety Rules for Production

For **production patches** (real code, not tests):

- [ ] Set `rollback_on_verify_failure: true`
- [ ] Include comprehensive `verify_after`
- [ ] Test on non-production first
- [ ] Have a rollback plan
- [ ] Consider `verify_markers` (pre-checks) for extra safety
- [ ] Use specific `patch_id` (not generic like `PATCH-001`)
- [ ] Fill in `remaining_issues_and_risks`
- [ ] Set `proposed_next_work` if future work needed

---

## 14. Final Checklist Before Delivery

When you finish writing a patch JSON:

**Structure**:
- [ ] `schema_version: "2.0"`
- [ ] `patch_id` unique
- [ ] `description` present
- [ ] `progress_report` has 3 core fields (non-empty strings)
- [ ] `patches` non-empty array

**Rules**:
- [ ] No `$1` / `$2` / `$3` in replacements
- [ ] No `\U` / `\L` / `\E`
- [ ] No duplicate operations
- [ ] `skip_syntax_check: true` for non-code files
- [ ] `create_if_missing: true` for new files

**Quality**:
- [ ] `verify_after` for production patches
- [ ] `rollback_on_verify_failure: true` for production
- [ ] No hardcoded values (use literals or template vars where appropriate)

**Validation**:
- [ ] `python -m apply_patch validate <file>` passes
- [ ] `python -m apply_patch apply <file> --dry-run` succeeds
- [ ] Ready for actual apply

---

## 15. Support

If a patch fails validation or apply:

1. Read error message carefully
2. Check Section 8 (Common AI Mistakes)
3. Check Section 14 (Final Checklist)
4. Validate with `python -m apply_patch validate <file>`
5. Check `docs/PATCH_AUTHOR_GUIDE.md` for detailed rules

**Remember**: Python regex uses `\1 \2 \3`, not `$1 $2 $3`.

---

**End of AI Patch Creation Guide.**

**Quick reference**: See `Patches/Patch_33_TEMPLATE_GOLD.json` for canonical template.