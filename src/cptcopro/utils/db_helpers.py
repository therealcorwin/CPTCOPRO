"""Utilitaires partagés pour la couche base de données (pages Streamlit).

Ce module centralise les helpers nécessaires à la transition SQLite → MariaDB,
en particulier la normalisation des types de colonnes retournés par pymysql.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import pandas as pd


class CursorLike(Protocol):
    description: Sequence[Sequence[object]] | None

    def fetchall(self) -> Sequence[object]:
        ...



def normalize_date_columns(df: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    """Convertit les colonnes DATE retournées par pymysql en datetime.date."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df


def normalize_numeric_columns(df: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    """Convertit les colonnes numériques en float (en remplacant NaN par 0.0)."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
    return df


def fetch_dataframe(cur: CursorLike) -> pd.DataFrame:
    """Convertit les resultats d'un curseur en DataFrame pandas en preservant toujours les colonnes."""
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if (hasattr(cur, "description") and cur.description) else None
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)

