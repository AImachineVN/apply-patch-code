"""Tests for patch list sort order (numeric, not string)."""
from __future__ import annotations

from pathlib import Path

from apply_patch.gui.views.main_view import _patch_sort_key


def test_numeric_sort_order() -> None:
    """Patch_10 > Patch_9 > Patch_2 > Patch_1 (descending, newest first)."""
    names = [
        "Patch_1_FIRST.json",
        "Patch_2_SECOND.json",
        "Patch_9_NINTH.json",
        "Patch_10_TENTH.json",
        "Patch_11_ELEVENTH.json",
    ]
    paths = [Path(n) for n in names]
    sorted_paths = sorted(paths, key=_patch_sort_key, reverse=True)
    result = [p.name for p in sorted_paths]
    assert result == [
        "Patch_11_ELEVENTH.json",
        "Patch_10_TENTH.json",
        "Patch_9_NINTH.json",
        "Patch_2_SECOND.json",
        "Patch_1_FIRST.json",
    ]


def test_legacy_files_sort_to_bottom() -> None:
    """Patch_2026_110_* (4-digit) and other non-matching files go to bottom."""
    names = [
        "Patch_5_FIFTH.json",
        "Patch_2026_110_SOURCE_SNAPSHOT_MD.json",
        "Patch_1_FIRST.json",
        "random_patch.json",
        "Patch_10_TENTH.json",
    ]
    paths = [Path(n) for n in names]
    sorted_paths = sorted(paths, key=_patch_sort_key, reverse=True)
    result = [p.name for p in sorted_paths]
    # First 3 should be numeric Patch_10, Patch_5, Patch_1 (descending)
    assert result[0] == "Patch_10_TENTH.json"
    assert result[1] == "Patch_5_FIFTH.json"
    assert result[2] == "Patch_1_FIRST.json"
    # Legacy and non-matching at bottom
    assert "Patch_2026_110_SOURCE_SNAPSHOT_MD.json" in result[3:]
    assert "random_patch.json" in result[3:]


def test_subversion_sort() -> None:
    """Patch_10.1 sorts between Patch_10.10 and Patch_10 (descending)."""
    names = [
        "Patch_9_NINTH.json",
        "Patch_10_TENTH.json",
        "Patch_10.1_TENTH_ONE.json",
        "Patch_10.10_TENTH_TEN.json",
        "Patch_11_ELEVENTH.json",
    ]
    paths = [Path(n) for n in names]
    sorted_paths = sorted(paths, key=_patch_sort_key, reverse=True)
    result = [p.name for p in sorted_paths]
    assert result == [
        "Patch_11_ELEVENTH.json",
        "Patch_10.10_TENTH_TEN.json",
        "Patch_10.1_TENTH_ONE.json",
        "Patch_10_TENTH.json",
        "Patch_9_NINTH.json",
    ]


def test_subversion_mixed_with_legacy() -> None:
    """Subversions sort correctly; legacy Patch_2026_* still at bottom."""
    names = [
        "Patch_10.1_NEW.json",
        "Patch_2026_110_LEGACY.json",
        "Patch_10_OLD.json",
        "Patch_11_LATEST.json",
    ]
    paths = [Path(n) for n in names]
    sorted_paths = sorted(paths, key=_patch_sort_key, reverse=True)
    result = [p.name for p in sorted_paths]
    assert result[0] == "Patch_11_LATEST.json"
    assert result[1] == "Patch_10.1_NEW.json"
    assert result[2] == "Patch_10_OLD.json"
    assert result[3] == "Patch_2026_110_LEGACY.json"


def test_case_insensitive_sort() -> None:
    """PATCH_/Patch_/patch_ đều match cùng số, sort ổn định theo name.lower()."""
    names = [
        "Patch_10_upper.json",
        "patch_10_lower.json",
        "PATCH_10_allcaps.json",
        "Patch_9_old.json",
    ]
    paths = [Path(n) for n in names]
    sorted_paths = sorted(paths, key=_patch_sort_key, reverse=True)
    result = [p.name for p in sorted_paths]
    # Cả 3 Patch_10 variants đều match số 10, sort cùng nhóm (case-insensitive)
    assert result[0].lower().startswith("patch_10")
    assert result[1].lower().startswith("patch_10")
    assert result[2].lower().startswith("patch_10")
    # Patch_9 last
    assert result[3] == "Patch_9_old.json"


def test_case_insensitive_tiebreak() -> None:
    """Khi cùng số, tie-breaker bằng p.name.lower() -> ổn định trên Windows."""
    names = [
        "patch_10_b.json",
        "PATCH_10_A.json",
        "Patch_10_C.json",
    ]
    paths = [Path(n) for n in names]
    sorted_paths = sorted(paths, key=_patch_sort_key, reverse=True)
    result = [p.name.lower() for p in sorted_paths]
    # Reverse=True -> Z > C > B > A -> c=..., a=..., b=...
    assert result == [
        "patch_10_c.json",
        "patch_10_b.json",
        "patch_10_a.json",
    ]
