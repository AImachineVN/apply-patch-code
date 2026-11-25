from pathlib import Path

import pytest

from apply_patch.context import SafetyError
from apply_patch.safety import safe_join


def test_safe_join_inside_project(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")

    result = safe_join(tmp_path, "a.py")

    assert result.name == "a.py"
    assert result.is_relative_to(tmp_path.resolve())


def test_safe_join_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(SafetyError):
        safe_join(tmp_path, "../outside.py")


def test_safe_join_rejects_absolute_path(tmp_path: Path) -> None:
    absolute = tmp_path / "a.py"
    absolute.write_text("print(1)\n", encoding="utf-8")

    with pytest.raises(SafetyError):
        safe_join(tmp_path, str(absolute))