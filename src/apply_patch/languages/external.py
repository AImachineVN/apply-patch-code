from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import LanguageHandler


class ExternalToolHandler(LanguageHandler):
    """
    Handler ủy quyền kiểm tra cú pháp cho một công cụ CLI bên ngoài
    (node, php, gofmt...).

    Nguyên tắc an toàn tuyệt đối:
    - Nếu binary không tồn tại trên PATH: bỏ qua kiểm tra (return True).
    - Nếu công cụ crash hoặc timeout: bỏ qua kiểm tra (return True).
    - Không bao giờ chặn patch chỉ vì thiếu toolchain.

    Mức độ nghiêm trọng của lỗi (chặn cứng hay chỉ cảnh báo)
    sẽ do engine quyết định ở Bước 2 dựa trên validation_kind.
    """

    name: str = "external"
    extensions: frozenset[str] = frozenset()
    validates_syntax = True
    validation_kind = "external"

    # Tên binary tra cứu trên PATH, ví dụ: "node"
    tool_name: str = ""
    # Mẫu argv, hỗ trợ placeholder {file}, ví dụ: ("--check", "{file}")
    argv_template: tuple[str, ...] = ()
    # Timeout cho tiến trình kiểm tra (giây)
    timeout_seconds: int = 30

    def is_tool_available(self) -> bool:
        """Kiểm tra binary có tồn tại trên PATH không."""
        return shutil.which(self.tool_name) is not None

    def check_file(self, path: Path, encoding: str = "utf-8") -> tuple[bool, str | None]:
        if not self.tool_name or not self.is_tool_available():
            return True, None

        argv = [self.tool_name] + [
            arg.replace("{file}", str(path)) for arg in self.argv_template
        ]

        try:
            proc = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError):
            # Công cụ không chạy được -> bỏ qua, không chặn patch
            return True, None

        if proc.returncode == 0:
            return True, None

        stderr = (proc.stderr or proc.stdout or "").strip()
        return False, f"{self.tool_name} reported syntax error: {stderr[:500]}"

    def check_text(self, content: str) -> tuple[bool, str | None]:
        if not self.tool_name or not self.is_tool_available():
            return True, None

        suffix = next(iter(self.extensions), ".txt")
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                suffix=suffix,
                encoding="utf-8",
                delete=False,
            ) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            return self.check_file(tmp_path, encoding="utf-8")
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


class JavaScriptHandler(ExternalToolHandler):
    """Handler JavaScript: dùng 'node --check' nếu node có trong PATH."""

    name = "javascript"
    extensions = frozenset({".js", ".mjs", ".cjs", ".jsx"})
    tool_name = "node"
    argv_template = ("--check", "{file}")


class PhpHandler(ExternalToolHandler):
    """Handler PHP: dùng 'php -l' nếu php có trong PATH."""

    name = "php"
    extensions = frozenset({".php"})
    tool_name = "php"
    argv_template = ("-l", "{file}")


class GoHandler(ExternalToolHandler):
    """Handler Go: dùng 'gofmt -e' nếu gofmt có trong PATH."""

    name = "go"
    extensions = frozenset({".go"})
    tool_name = "gofmt"
    argv_template = ("-e", "{file}")
    
    
class RubyHandler(ExternalToolHandler):
    """Handler Ruby: dùng 'ruby -c' nếu ruby có trong PATH."""

    name = "ruby"
    extensions = frozenset({".rb"})
    tool_name = "ruby"
    argv_template = ("-c", "{file}")


class ShellHandler(ExternalToolHandler):
    """Handler shell script: dùng 'bash -n' nếu bash có trong PATH."""

    name = "shell"
    extensions = frozenset({".sh", ".bash"})
    tool_name = "bash"
    argv_template = ("-n", "{file}")