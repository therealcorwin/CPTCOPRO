"""Module d'insertion des charges dans la base de données SQLite.

Ce module gère l'insertion des données de charges des copropriétaires.
"""

import os
import sqlite3
from typing import Any, List
from loguru import logger

logger = logger.bind(type_log="BDD")


def _normaliser_lignes_charge(data: List[Any]) -> list[tuple[Any, Any, Any, Any, Any]]:
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
            if code.lower() in ("code", "copropriétaire", "coproprietaire", "informations", "en-tete1"):
                continue
            if nom.lower() in ("copropriétaire", "coproprietaire", "nom", "nom propriétaire", "en-tete2"):
                continue
            if len(code) > 30 or len(nom) > 150:
                continue
            lignes.append((code, nom, row[2], row[3], row[4]))
    return lignes


def enregistrer_donnees_sqlite(data: List[Any], db_path: str) -> None:
    """
    Enregistre les données extraites dans une base de données SQLite.

    La fonction se connecte à la base de données SQLite spécifiée par `db_path`
    et insère les données fournies dans la table `charge` après validation
    et normalisation par `_normaliser_lignes_charge`.

    Parameters:
    - data (list[Any]): Une liste de tuples contenant les données de charges à enregistrer.
      Chaque tuple doit contenir : (code_proprietaire, nom_proprietaire, debit, credit, date).
      Les éventuelles lignes d'en-tête ou de format invalide sont automatiquement filtrées.
    - db_path (str): Le chemin vers la base de données SQLite.

    Returns:
    - None
    """
    if not os.path.exists(db_path):
        logger.error(
            f"Base de données '{db_path}' introuvable. Veuillez créer la base avant d'exécuter ce script."
        )
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    lignes = _normaliser_lignes_charge(data)
    try:
        # Insertion des données avec INSERT OR REPLACE
        # Si une entrée avec le même (code_proprietaire, date) existe, elle est mise à jour
        cur.executemany(
            """INSERT OR REPLACE INTO charge 
               (code_proprietaire, nom_proprietaire, debit, credit, date, last_check) 
               VALUES (?, ?, ?, ?, ?, CURRENT_DATE)""",
            lignes,
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Erreur lors de l'insertion des données : {e}")
        raise
    finally:
        conn.close()
    processed_count = len(lignes)
    logger.info(f"{processed_count} enregistrements traités (insérés ou mis à jour).")
