"""Tests pour les utilitaires de base de données pandas (utils/db_helpers.py)."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pandas as pd

from cptcopro.utils.db_helpers import (
    fetch_dataframe,
    normalize_date_columns,
    normalize_numeric_columns,
)


def test_normalize_date_columns():
    """Vérifie la conversion des colonnes en datetime.date et gestion d'erreurs."""
    df = pd.DataFrame(
        {
            "date_col": ["2026-01-15", "2026-02-20", "invalid_date"],
            "other_col": [1, 2, 3],
        }
    )

    res = normalize_date_columns(df, ["date_col", "absent_col"])
    assert res["date_col"].iloc[0] == datetime.date(2026, 1, 15)
    assert res["date_col"].iloc[1] == datetime.date(2026, 2, 20)
    assert pd.isna(res["date_col"].iloc[2])
    assert res["other_col"].iloc[0] == 1


def test_normalize_numeric_columns():
    """Vérifie la conversion des colonnes numériques en float avec fallback 0.0."""
    df = pd.DataFrame(
        {
            "num_str": ["12.5", "100", None],
            "num_mixed": [10, "invalid", 20.5],
            "text": ["a", "b", "c"],
        }
    )

    res = normalize_numeric_columns(df, ["num_str", "num_mixed", "absent_col"])
    assert res["num_str"].tolist() == [12.5, 100.0, 0.0]
    assert res["num_mixed"].tolist() == [10.0, 0.0, 20.5]
    assert res["text"].tolist() == ["a", "b", "c"]


def test_fetch_dataframe_with_data():
    """Vérifie la construction d'un DataFrame à partir d'un curseur avec des données."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    mock_cur.description = [("id",), ("name",)]

    df = fetch_dataframe(mock_cur)
    assert len(df) == 2
    assert list(df.columns) == ["id", "name"]
    assert df["name"].tolist() == ["Alice", "Bob"]


def test_fetch_dataframe_empty_preserves_columns():
    """Vérifie qu'un curseur vide préserve tout de même les colonnes."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_cur.description = [("id",), ("name",), ("debit",)]

    df = fetch_dataframe(mock_cur)
    assert len(df) == 0
    assert list(df.columns) == ["id", "name", "debit"]


def test_fetch_dataframe_no_description():
    """Vérifie le comportement si cur.description est None."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_cur.description = None

    df = fetch_dataframe(mock_cur)
    assert len(df) == 0
