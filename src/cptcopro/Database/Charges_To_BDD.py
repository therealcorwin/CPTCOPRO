"""Module d'insertion des charges dans la base de données SQLite.

Ce module gère l'insertion des données de charges des copropriétaires.
"""

import os
import sqlite3
from typing import Any, List
from loguru import logger

logger = logger.bind(type_log="BDD")


def _normaliser_lignes_charge(data: List[Any]) -> list[tuple[Any, Any, Any, Any, Any]]:
    """Normalise la collecte charges en ignorant les anciennes entrées d'en-tête.

    Historique: le code supprimait systématiquement `data[0:3]`.
    Désormais on accepte:
    - une liste directement composée de tuples charges,
    - une liste mixte contenant des lignes d'en-tête (str) puis des tuples.
    """
    lignes: list[tuple[Any, Any, Any, Any, Any]] = []
    for row in data:
        if isinstance(row, (tuple, list)) and len(row) >= 5:
            lignes.append((row[0], row[1], row[2], row[3], row[4]))
    return lignes


def enregistrer_donnees_sqlite(data: List[Any], db_path: str) -> None:
    """
    Enregistre les données extraites dans une base de données SQLite.

    La fonction se connecte à la base de données SQLite spécifiée par `db_path`
    et insère les données fournies dans la table `charge`.

    Parameters:
    - data (list[Any]): Une liste de tuples contenant les données à enregistrer.
      Chaque tuple doit avoir le format suivant : (code_proprietaire, nom_proprietaire, debit, credit, date).
      Les 3 premiers éléments sont ignorés (en-têtes).
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
