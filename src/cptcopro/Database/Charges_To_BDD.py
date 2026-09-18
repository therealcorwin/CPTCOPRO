"""Module d'insertion des charges dans la base de données MariaDB.

Ce module gère l'insertion des données de charges des copropriétaires.
"""

from typing import Any

from loguru import logger

from .connection import get_db_connection

logger = logger.bind(type_log="BDD")


class CollecteChargesVideError(RuntimeError):
    """Erreur levée lorsque aucune charge valide n'est extraite ou fournie."""
    pass


def valider_charges_presentes(data: list[Any]) -> list[tuple[Any, Any, Any, Any, Any]]:
    """Vérifie que des charges valides sont présentes après normalisation.

    Raises:
        CollecteChargesVideError: Si aucune charge valide n'est trouvée.
    """
    if not data:
        raise CollecteChargesVideError(
            "Échec collecte des charges : la liste des charges est vide."
        )
    lignes = _normaliser_lignes_charge(data)
    if not lignes:
        raise CollecteChargesVideError(
            "Échec collecte des charges : aucune ligne de charge valide après filtrage."
        )
    return lignes


def _normaliser_lignes_charge(data: list[Any]) -> list[tuple[Any, Any, Any, Any, Any]]:
    """Normalise la collecte charges en filtrant les entrées d'en-tête et lignes invalides.

    Historique: le code d'origine supprimait aveuglément `data[0:3]`.
    Désormais on valide chaque ligne pour ne conserver que les vraies charges de copropriétaires :
    - code_proprietaire et nom_proprietaire non vides et non égaux aux mots d'en-tête ("Code", "Copropriétaire", etc.)
    - exclusion des lignes résiduelles de filtres HTML concaténés (longueur aberrante).
    """
    lignes: list[tuple[Any, Any, Any, Any, Any]] = []
    for row in data:
        if isinstance(row, (tuple, list)) and len(row) >= 5:
            code = str(row[0]).strip()
            nom = str(row[1]).strip()
            if not code or not nom:
                continue
            if code.lower() in (
                "code",
                "copropriétaire",
                "coproprietaire",
                "informations",
                "en-tete1",
            ):
                continue
            if nom.lower() in (
                "copropriétaire",
                "coproprietaire",
                "nom",
                "nom propriétaire",
                "en-tete2",
            ):
                continue
            if len(code) > 30 or len(nom) > 150:
                continue
            lignes.append((code, nom, row[2], row[3], row[4]))
    return lignes


def enregistrer_charges(data: list[Any], allow_empty: bool = False) -> None:
    """Enregistre les données extraites dans la base de données MariaDB.

    La fonction se connecte via le pool MariaDB et insère les données fournies
    dans la table `charge` après validation et normalisation par
    `_normaliser_lignes_charge`.

    Utilise INSERT ... ON DUPLICATE KEY UPDATE pour préserver la sémantique
    idempotente : si une entrée (code_proprietaire, date) existe déjà, seule
    la colonne last_check est mise à jour (les triggers sont ainsi préservés).

    Parameters:
        data: Liste de tuples (code_proprietaire, nom_proprietaire, debit, credit, date).
              Les éventuelles lignes d'en-tête ou de format invalide sont filtrées.
        allow_empty: Si False (défaut), lève CollecteChargesVideError si aucune
                     ligne valide n'est présente.

    Raises:
        CollecteChargesVideError: Si aucune charge valide n'est extraite et allow_empty=False.
    """
    lignes = _normaliser_lignes_charge(data)
    if not lignes:
        if allow_empty:
            logger.info("Aucune donnée de charge à insérer après normalisation.")
            return
        raise CollecteChargesVideError(
            "Échec collecte des charges : aucune ligne de charge valide extraite."
        )

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # INSERT ... ON DUPLICATE KEY UPDATE :
            # - Contrairement à INSERT OR REPLACE SQLite (DELETE + INSERT), cette forme
            #   ne réinitialise pas l'id et ne perd pas de données non fournies.
            # - Les triggers AFTER INSERT sont préservés (pas de DELETE intermédiaire).
            cur.executemany(
                """INSERT INTO charge
                   (code_proprietaire, nom_proprietaire, debit, credit, date, last_check)
                   VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
                   ON DUPLICATE KEY UPDATE
                       last_check = VALUES(last_check)""",
                lignes,
            )

    processed_count = len(lignes)
    logger.info(f"{processed_count} enregistrements traités (insérés ou mis à jour).")
