"""Module d'insertion des charges dans la base de données SQLite.

Ce module gère l'insertion des données de charges des copropriétaires.
"""
import os
import sqlite3
from typing import Any, List
from loguru import logger

logger = logger.bind(type_log="BDD")


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
    try:
        # Insertion des données
        # Ignorer les trois premiers éléments de data (en-têtes) avec data[3:]
        # data[3:] contient des tuples (code_proprietaire, nom_proprietaire, debit, credit, date)
        cur.executemany(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            data[3:],
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Erreur lors de l'insertion des données : {e}")
        raise
    finally:
        conn.close()
    # Log le nombre de lignes insérées (on ignore les 3 premiers éléments d'en-tête)
    try:
        inserted_count = len(data[3:])
    except Exception:
        inserted_count = 0
    logger.info(f"{inserted_count} enregistrements insérés dans la base de données.")
