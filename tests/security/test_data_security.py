"""Tests de sécurité et de validation stricte des données (Lots et Charges)."""

import pytest

from cptcopro.Database.Charges_To_BDD import (
    CollecteChargesVideError,
    enregistrer_charges,
    valider_charges_presentes,
)
from cptcopro.Database.constants import NOMBRE_LOTS_ATTENDU
from cptcopro.Database.Coproprietaires_To_BDD import (
    IncoherenceLotsError,
    enregistrer_coproprietaires,
    valider_nombre_lots,
)
from cptcopro.main import _valider_donnees_avant_sauvegarde


def _generer_lots_factices(nb: int) -> list[dict[str, str]]:
    """Génère un nombre donné de lots factices valides."""
    lots = []
    for i in range(nb):
        if i == 0:
            lots.append(
                {
                    "nom_proprietaire": "SCIC AB HABITAT",
                    "code_proprietaire": "558A",
                    "num_apt": "NA",
                    "type_apt": "NA",
                }
            )
        else:
            lots.append(
                {
                    "nom_proprietaire": f"Propriétaire {i}",
                    "code_proprietaire": f"CODE{i}",
                    "num_apt": str(i),
                    "type_apt": "3p",
                }
            )
    return lots


def _generer_charges_factices() -> list[tuple[str, str, str, str, str]]:
    """Génère une liste de charges factices valides."""
    return [
        ("CODE1", "Propriétaire 1", "150.00", "0.00", "2026-09-01"),
        ("CODE2", "Propriétaire 2", "0.00", "200.00", "2026-09-01"),
    ]


# === Tests Lots ===


def test_valider_nombre_lots_accepte_exactement_64():
    """64 lots valides doivent être acceptés sans lever d'exception."""
    lots_64 = _generer_lots_factices(NOMBRE_LOTS_ATTENDU)
    valider_nombre_lots(lots_64, nombre_attendu=NOMBRE_LOTS_ATTENDU)


@pytest.mark.parametrize("nb_lots", [0, 1, 50, 63, 65, 100])
def test_valider_nombre_lots_rejette_tout_nombre_different_de_64(nb_lots: int):
    """Tout nombre de lots différent de 64 doit lever IncoherenceLotsError."""
    lots = _generer_lots_factices(nb_lots)
    with pytest.raises(IncoherenceLotsError) as exc_info:
        valider_nombre_lots(lots, nombre_attendu=NOMBRE_LOTS_ATTENDU)
    assert f"au lieu de {NOMBRE_LOTS_ATTENDU} attendus" in str(exc_info.value)


def test_enregistrer_coproprietaires_rejette_nombre_incorrect_quand_specifie():
    """enregistrer_coproprietaires avec nombre_attendu doit lever IncoherenceLotsError."""
    lots_incomplets = _generer_lots_factices(63)
    with pytest.raises(IncoherenceLotsError):
        enregistrer_coproprietaires(lots_incomplets, nombre_attendu=NOMBRE_LOTS_ATTENDU)


# === Tests Charges ===


def test_valider_charges_presentes_accepte_charges_valides():
    """Une liste de charges valides doit être acceptée et normalisée."""
    charges = _generer_charges_factices()
    lignes = valider_charges_presentes(charges)
    assert len(lignes) == 2


def test_valider_charges_presentes_rejette_liste_vide():
    """Une liste vide doit lever CollecteChargesVideError."""
    with pytest.raises(CollecteChargesVideError):
        valider_charges_presentes([])


def test_valider_charges_presentes_rejette_en_tetes_seules():
    """Une liste contenant uniquement des lignes d'en-tête doit lever CollecteChargesVideError."""
    headers_only = [
        ("Code", "Copropriétaire", "Débit", "Crédit", "Date"),
        ("Informations", "Nom propriétaire", "", "", ""),
    ]
    with pytest.raises(CollecteChargesVideError):
        valider_charges_presentes(headers_only)


def test_enregistrer_charges_rejette_vide_par_defaut():
    """enregistrer_charges([]) sans allow_empty doit lever CollecteChargesVideError."""
    with pytest.raises(CollecteChargesVideError):
        enregistrer_charges([])


def test_enregistrer_charges_accepte_vide_si_allow_empty():
    """enregistrer_charges([], allow_empty=True) ne doit pas lever d'exception."""
    enregistrer_charges([], allow_empty=True)


# === Tests Validation Globale Pré-BDD (main.py) ===


def test_valider_donnees_avant_sauvegarde_succes():
    """Lots 64 + Charges présentes -> succès."""
    lots = _generer_lots_factices(64)
    charges = _generer_charges_factices()
    _valider_donnees_avant_sauvegarde(charges, lots)


def test_valider_donnees_avant_sauvegarde_echec_lots():
    """Lots != 64 -> lève IncoherenceLotsError."""
    lots = _generer_lots_factices(63)
    charges = _generer_charges_factices()
    with pytest.raises(IncoherenceLotsError):
        _valider_donnees_avant_sauvegarde(charges, lots)


def test_valider_donnees_avant_sauvegarde_echec_charges():
    """Lots == 64 mais Charges vides -> lève CollecteChargesVideError."""
    lots = _generer_lots_factices(64)
    with pytest.raises(CollecteChargesVideError):
        _valider_donnees_avant_sauvegarde([], lots)
