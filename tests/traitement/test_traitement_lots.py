"""Tests pour le traitement et la consolidation des lots des copropriétaires (Traitement/Lots_Copro.py)."""

from __future__ import annotations

import pytest

from cptcopro.Traitement.Lots_Copro import (
    consolider_proprietaires_lots,
    detecter_proprietaire,
    est_ligne_lot,
    est_scic,
    extraire_info_lot,
    normaliser_prefixes_proprietaire,
)

# ---------------------------------------------------------------------------
# Tests normaliser_prefixes_proprietaire
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_name, expected",
    [
        ("M. DUPONT Jean", "DUPONT Jean"),
        ("Mme MARTIN Sophie", "MARTIN Sophie"),
        ("Monsieur et Madame BERNARD", "BERNARD"),
        ("M. ou Mme PETIT", "PETIT"),
        ("Mlle DUBOIS Claire", "DUBOIS Claire"),
        ("Me. LEROY Pierre", "LEROY Pierre"),
        ("Mr & Mrs SMITH", "SMITH"),
        ("DUPONT Pierre", "DUPONT Pierre"),
        ("", ""),
    ],
)
def test_normaliser_prefixes_proprietaire(input_name, expected):
    """Vérifie le nettoyage exhaustif des préfixes de civilité."""
    assert normaliser_prefixes_proprietaire(input_name) == expected


# ---------------------------------------------------------------------------
# Tests est_scic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("SCIC HABITAT ILE DE FRANCE", True),
        ("AB HABITAT", True),
        ("AB-HABITAT", True),
        ("Scic d'HLM", True),
        ("DUPONT Jean", False),
        ("", False),
    ],
)
def test_est_scic(name, expected):
    """Vérifie la détection des bailleurs sociaux (SCIC / AB HABITAT)."""
    assert est_scic(name) is expected


# ---------------------------------------------------------------------------
# Tests detecter_proprietaire & est_ligne_lot & extraire_info_lot
# ---------------------------------------------------------------------------


def test_detecter_proprietaire_valid_and_invalid():
    assert detecter_proprietaire("DUPONT Jean (12A)") == ("DUPONT Jean", "12A")
    assert detecter_proprietaire("MARTIN Paul (558)") == ("MARTIN Paul", "558")
    assert detecter_proprietaire("Lot 0021 Appartement 3P") is None
    assert detecter_proprietaire("Texte sans code") is None


def test_est_ligne_lot():
    assert est_ligne_lot("Lot 0021 Appartement 3P") is True
    assert est_ligne_lot("Lot 9") is True
    assert est_ligne_lot("Appartement 2 pièces") is True
    assert est_ligne_lot("DUPONT Jean (12A)") is False


def test_extraire_info_lot():
    assert extraire_info_lot("Lot 0009: Appartement 3 p") == ("9", "3P")
    assert extraire_info_lot("Lot 012 Appartement 4 p") == ("12", "4P")
    assert extraire_info_lot("Lot 100") == ("100", "")
    assert extraire_info_lot("") == (None, None)


# ---------------------------------------------------------------------------
# Tests consolider_proprietaires_lots
# ---------------------------------------------------------------------------


def test_proprietaire_with_single_lot():
    elements = [
        ("A17_1_1", "Plop PLOP (3825A)"),
        ("A17_1_2", "Lot 0009: Appartement 3 p"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 1
    e = out[0]
    assert e["nom_proprietaire"] == "Plop PLOP"
    assert e["code_proprietaire"] == "3825A"
    assert e["num_apt"] == "9"
    assert e["type_apt"] == "3p"


def test_proprietaire_with_multiple_lots():
    elements = [
        ("A17_1_1", "JEAN (100)"),
        ("A17_1_2", "Lot 001: Appartement 2 p"),
        ("A17_1_3", "Lot 002: Appartement 3 p"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 2
    nums = [o.get("num_apt") for o in out]
    assert "1" in nums and "2" in nums


def test_lot_without_proprietaire():
    elements = [
        ("A17_1_1", "Lot 010: Appartement 1 p"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 1
    e = out[0]
    assert e.get("nom_proprietaire") in (None, "")
    assert e.get("num_apt") == "10"


def test_proprietaire_without_lot():
    elements = [
        ("A17_1_1", "ALICE (555)"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 1
    e = out[0]
    assert e.get("nom_proprietaire") == "ALICE"
    assert e.get("num_apt") in (None, "")
    assert e.get("type_apt") in (None, "")


def test_proprietaire_scic_has_na_lots():
    """Vérifie que les bailleurs SCIC / AB HABITAT reçoivent automatiquement num_apt='NA' et type_apt='NA'."""
    elements = [
        ("A17_1_1", "SCIC HABITAT (558A)"),
        ("A17_1_2", "Lot 001: Appartement 2 p"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 1
    assert out[0]["num_apt"] == "NA"
    assert out[0]["type_apt"] == "NA"
