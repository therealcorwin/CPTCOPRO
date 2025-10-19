import os
import sqlite3
from loguru import logger
from typing import Any

logger.remove()
logger = logger.bind(type_log="BDD")


def verif_presence_db(db_path: str) -> None:
    """
    Vérifie la présence de la base de données SQLite.
    Si elle n'existe pas, la crée et logue chaque étape.

    Args:
        db_path (str): Chemin vers la base de données SQLite.
    """
    if os.path.exists(db_path):
        logger.info(f"La base de données '{db_path}' existe déjà.")
        return

    try:
        # Création de la base et de la table principale
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS coproprietaires (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                coproprietaire TEXT,
                debit REAL,
                credit REAL,
                date DATE,
                last_check DATE
            )
            """
        )
        conn.commit()
        conn.close()
        logger.info(f"Base de données '{db_path}' créée avec succès.")
    except Exception as e:
        logger.error(f"Erreur lors de la création de la base de données : {e}")
        raise


def enregistrer_donnees_sqlite(data: list[Any], db_path: str) -> None:
    """
    Enregistre les données extraites dans une base de données SQLite.

    La fonction se connecte à la base de données SQLite spécifiée par `db_path`,
    crée une table "coproprietaires" si elle n'existe pas, et insère les données
    fournies dans la table.

    Parameters:
    - data (list[Any]): Une liste de tuples contenant les données à enregistrer.
      Chaque tuple doit avoir le format suivant : (code, coproprietaire, debit, credit, date).
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
        cur.executemany(
            "INSERT INTO coproprietaires (code, coproprietaire, debit, credit, date, last_check) VALUES (?, ?, ?, ?, ?,?)",
            data[3:],
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Erreur lors de l'insertion des données : {e}")
        raise
    finally:
        conn.close()
    logger.info(f"{len(data)-2} enregistrements insérés dans la base de données.")
