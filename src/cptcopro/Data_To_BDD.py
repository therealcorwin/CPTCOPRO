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
    if not os.path.exists(db_path):
        logger.warning(f"La base de données '{db_path}' n'existe pas.")
        logger.info("Création de la base de données SQLite...")
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
            logger.info("Table 'coproprietaires' vérifiée/créée.")

            # Création de la table 'alertes_debit_eleve'
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS alertes_debit_eleve (
                    alerte_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    copro_id INTEGER NOT NULL,
                    copro_code TEXT,
                    copro_nom TEXT,
                    debit_detecte REAL NOT NULL,
                    date_detection DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(copro_id) REFERENCES coproprietaires(id) ON DELETE CASCADE
                );
                """
            )
            logger.info("Table 'alertes_debit_eleve' vérifiée/créée.")

            # Création du trigger pour les insertions
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve
                AFTER INSERT ON coproprietaires
                FOR EACH ROW
                WHEN NEW.debit > 2000.0
                BEGIN
                    INSERT INTO alertes_debit_eleve (copro_id, copro_code, copro_nom, debit_detecte)
                    VALUES (NEW.id, NEW.code, NEW.coproprietaire, NEW.debit);
                END;
                """
            )
            logger.info("Trigger 'alerte_debit_eleve' vérifié/créé.")

            conn.commit()
            conn.close()
            logger.success(f"Base de données '{db_path}' et trigger 'alerte_debit_eleve' créés avec succès.")
        except Exception as e:
            logger.error(f"Erreur lors de la création de la base de données : {e}")
            raise
    else:
        logger.info(f"La base de données '{db_path}' existe déjà.")

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
