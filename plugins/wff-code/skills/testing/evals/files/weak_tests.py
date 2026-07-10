"""Weak tests demonstrating common quality problems.

This file is an INPUT for the review eval scenario. It intentionally contains
poor testing patterns for the skill to identify and critique.
"""

from unittest.mock import MagicMock

import pytest


# Source functions under test (inlined for simplicity)
def add(a: int, b: int) -> int:
    return a + b


def multiply(a: int, b: int) -> int:
    if b == 0:
        return 0
    return a * b


def get_user(db: object, user_id: int) -> dict:  # type: ignore[type-arg]
    return db.query(user_id)  # type: ignore[attr-defined]


# --- Weak tests below ---


def test_add_positive() -> None:
    assert add(2, 3) == 5


def test_add_positive_again() -> None:
    assert add(10, 20) == 30


def test_add_positive_third() -> None:
    assert add(100, 200) == 300


def test_multiply() -> None:
    result = multiply(3, 4)
    assert result is not None


def test_multiply_zero() -> None:
    assert True  # Zero case "tested"


def test_get_user() -> None:
    mock_db = MagicMock()
    mock_db.query.return_value = {"id": 1, "name": "Alice"}
    result = get_user(mock_db, 1)
    assert result


def test_add_does_not_raise() -> None:
    try:
        add(1, 1)
    except Exception:
        pytest.fail("add raised an exception")
