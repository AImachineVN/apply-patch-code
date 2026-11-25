"""Tests for DonateView module."""
from __future__ import annotations

from apply_patch.gui.views import donate_view


def test_paypal_constants() -> None:
    assert donate_view.PAYPAL_EMAIL == "support.aimachine@gmail.com"
    assert donate_view.PAYPAL_ME_USER == "AImachine"


def test_paypal_me_url() -> None:
    assert donate_view.PAYPAL_ME_URL == "https://paypal.me/AImachine"


def test_bank_constants() -> None:
    assert donate_view.BANK_STK == "1073988400"
    assert donate_view.BANK_HOLDER == "NGUYEN XUAN CAO"
    assert donate_view.BANK_NAME == "Vietcombank"


def test_github_constants() -> None:
    assert donate_view.GITHUB_USER == "AImachineVN"
    assert donate_view.GITHUB_REPO == "apply-patch-code"
    assert donate_view.GITHUB_URL == "https://github.com/AImachineVN/apply-patch-code"


def test_author_name() -> None:
    assert donate_view.AUTHOR_NAME == "Nguyễn Cao"
