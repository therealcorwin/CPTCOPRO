"""Tests unitaires pour la logique de statut et calculs financiers de Liste_Charge."""

from __future__ import annotations

from cptcopro.utils.ui_components import determiner_statut_copro


def test_determiner_statut_alerte():
    """Un compte en alerte seuil doit retourner le badge d'alerte prioritaire."""
    alert_codes = {"C001", "C002"}
    assert (
        determiner_statut_copro(
            code="C001",
            debit=3500.0,
            credit=0.0,
            delta_debit=200.0,
            alert_codes=alert_codes,
        )
        == "🚨 Alerte seuil"
    )


def test_determiner_statut_debiteur_en_hausse():
    """Un compte débiteur dont la dette augmente depuis N-1."""
    alert_codes = set()
    assert (
        determiner_statut_copro(
            code="C005",
            debit=1200.0,
            credit=0.0,
            delta_debit=150.0,
            alert_codes=alert_codes,
        )
        == "🔴 Débiteur (+)"
    )


def test_determiner_statut_debiteur_en_baisse():
    """Un compte débiteur dont la dette diminue depuis N-1 (régularisation partielle)."""
    alert_codes = set()
    assert (
        determiner_statut_copro(
            code="C006",
            debit=800.0,
            credit=0.0,
            delta_debit=-250.0,
            alert_codes=alert_codes,
        )
        == "🟡 Débiteur (-)"
    )


def test_determiner_statut_debiteur_stable():
    """Un compte débiteur dont la dette est strictement inchangée."""
    alert_codes = set()
    assert (
        determiner_statut_copro(
            code="C007",
            debit=500.0,
            credit=0.0,
            delta_debit=0.0,
            alert_codes=alert_codes,
        )
        == "🟠 Débiteur"
    )


def test_determiner_statut_crediteur():
    """Un compte avec solde créditeur (avance de charges)."""
    alert_codes = set()
    assert (
        determiner_statut_copro(
            code="C008",
            debit=0.0,
            credit=350.0,
            delta_debit=0.0,
            alert_codes=alert_codes,
        )
        == "🔵 Créditeur"
    )


def test_determiner_statut_a_jour():
    """Un compte sans débit ni crédit."""
    alert_codes = set()
    assert (
        determiner_statut_copro(
            code="C009",
            debit=0.0,
            credit=0.0,
            delta_debit=0.0,
            alert_codes=alert_codes,
        )
        == "🟢 À jour"
    )

