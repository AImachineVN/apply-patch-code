# Apply Patch Code

**Enterprise patch automation tool for source code with AI handoff support.**

Apply Patch Code is a desktop tool that applies declarative JSON patches to source code projects. Instead of manually editing files, developers (and AI assistants) write self-describing JSON patches that are validated, dry-run tested, backed up, and applied atomically.

## ✨ Features
- **6 operation types**: `replace`, `insert_after`, `insert_before`, `delete`, `replace_regex`, `write_content`
- **Undo Execute**: Restore files from backup with one click.
- **Source Snapshot**: Generate Markdown snapshots of your source code optimized for AI context limits (300 KB chunks).
- **Profiles Auto-sync**: Automatically updates 10 project status files after every patch.
- **Atomic writes & Backups**: No partial writes. Auto-rollback on verify failure.
- **Multi-language validation**: Python, JSON, XML, JS, PHP, Go, etc.

## 📦 Installation
Download the latest `ApplyPatchCode_Setup_v1.0.0.exe` from the [Releases](https://github.com/AImachineVN/apply-patch-code/releases) page.

## 🛠️ Build from source
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install pytest ruff mypy nuitka ordered-set zstandard

python build.py
iscc installer_config.iss
💝 Support Development
If this tool helps you, consider supporting development:

PayPal.Me: https://paypal.me/AImachine

PayPal Email: support.aimachine@gmail.com

Bank (Vietcombank): 1073988400 (NGUYEN XUAN CAO)

📄 License
This project is licensed under the MIT License.

text

#### File 3: `LICENSE` (Bản quyền)
Tạo file `LICENSE` ở thư mục gốc (Bản quyền MIT):
```text
MIT License

Copyright (c) 2026 Nguyễn Cao (AImachineVN)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.