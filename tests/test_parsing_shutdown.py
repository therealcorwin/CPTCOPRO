import pytest

from cptcopro.Parsing.Commun import (
    _is_expected_target_closed,
    _is_expected_target_closed_context,
)


def test_is_expected_target_closed_matches_playwright_message() -> None:
    exc = RuntimeError("Target page, context or browser has been closed")
    assert _is_expected_target_closed(exc) is True


def test_is_expected_target_closed_ignores_other_errors() -> None:
    exc = RuntimeError("Some other error")
    assert _is_expected_target_closed(exc) is False


def test_is_expected_target_closed_context_matches_exception_field() -> None:
    context = {
        "exception": RuntimeError("Target page, context or browser has been closed")
    }
    assert _is_expected_target_closed_context(context) is True


def test_is_expected_target_closed_context_matches_message_field() -> None:
    context = {
        "message": "Future exception was never retrieved: Target page, context or browser has been closed"
    }
    assert _is_expected_target_closed_context(context) is True


def test_is_expected_target_closed_context_ignores_unrelated_context() -> None:
    context = {
        "message": "Some unrelated asyncio warning",
        "exception": RuntimeError("Some other error"),
    }
    assert _is_expected_target_closed_context(context) is False
