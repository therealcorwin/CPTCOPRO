"""Tests pour les utilitaires de gestion et normalisation de dates UI."""

from __future__ import annotations

import datetime as dt

from cptcopro.utils.ui_components import normalize_date_range


def test_normalize_date_range_two_dates():
    """Vérifie le cas standard où l'utilisateur fournit les deux bornes."""
    min_d = dt.date(2020, 1, 1)
    max_d = dt.date(2025, 12, 31)
    d_start = dt.date(2022, 5, 1)
    d_end = dt.date(2024, 6, 30)

    start, end = normalize_date_range((d_start, d_end), min_d, max_d)
    assert start == d_start
    assert end == d_end

    start_list, end_list = normalize_date_range([d_start, d_end], min_d, max_d)
    assert start_list == d_start
    assert end_list == d_end


def test_normalize_date_range_single_date_preserves_max():
    """Vérifie que la sélection d'une seule date de début ne replie pas la date de fin sur la date de début."""
    min_d = dt.date(2020, 1, 1)
    max_d = dt.date(2025, 12, 31)
    d_start = dt.date(2023, 3, 15)

    start, end = normalize_date_range((d_start,), min_d, max_d)
    assert start == d_start
    assert end == max_d

    start_list, end_list = normalize_date_range([d_start], min_d, max_d)
    assert start_list == d_start
    assert end_list == max_d


def test_normalize_date_range_bare_date():
    """Vérifie le comportement si un objet dt.date direct est passé."""
    min_d = dt.date(2020, 1, 1)
    max_d = dt.date(2025, 12, 31)
    d_start = dt.date(2023, 1, 1)

    start, end = normalize_date_range(d_start, min_d, max_d)
    assert start == d_start
    assert end == max_d


def test_normalize_date_range_fallback_empty_or_invalid():
    """Vérifie le repli sur (min_d, max_d) pour les valeurs vides ou inattendues."""
    min_d = dt.date(2020, 1, 1)
    max_d = dt.date(2025, 12, 31)

    assert normalize_date_range((), min_d, max_d) == (min_d, max_d)
    assert normalize_date_range([], min_d, max_d) == (min_d, max_d)
    assert normalize_date_range(None, min_d, max_d) == (min_d, max_d)
    assert normalize_date_range("invalid", min_d, max_d) == (min_d, max_d)
