import os
import sqlite3
from loguru import logger
from typing import Any, Dict

logger.remove()
logger = logger.bind(type_log="BDD")

def verif_repertoire_db(db_path: str) -> None:
    """
    Vérifie que le répertoire de la base de données SQLite existe.
    Si ce n'est pas le cas, le crée et logue chaque étape.

    Args:
        db_path (str): Chemin vers la base de données SQLite.
    """
    dir_path = os.path.dirname(db_path)
    if not os.path.exists(dir_path):
        logger.warning(f"Le répertoire '{dir_path}' n'existe pas.")
        logger.info(f"Création du répertoire '{dir_path}' pour la base de données...")
        try:
            os.makedirs(dir_path)
            logger.success(f"Répertoire '{dir_path}' créé avec succès.")
        except Exception as e:
            logger.error(f"Erreur lors de la création du répertoire '{dir_path}' : {e}")
            raise
    else:
        logger.info(f"Le répertoire '{dir_path}' existe déjà.")

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
                CREATE TABLE IF NOT EXISTS charge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT,
                    proprietaire TEXT,
                    debit REAL,
                    credit REAL,
                    date DATE,
                    last_check DATE
                )
                """
            )
            logger.info("Table 'charge' vérifiée/créée.")

            # Création de la table 'alertes_debit_eleve'
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS alertes_debit_eleve (
                    alerte_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_origin INTEGER NOT NULL,
                    code_proprietaire TEXT,
                    nom_proprietaire TEXT,
                    debit REAL NOT NULL,
                    date_detection DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(id_origin) REFERENCES charge(id) ON DELETE CASCADE
                );
                """
            )
            logger.info("Table 'alertes_debit_eleve' vérifiée/créée.")

            # Création du trigger pour les insertions
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.debit > 2000.0
                BEGIN
                    INSERT INTO alertes_debit_eleve (id_origin, code_proprietaire, nom_proprietaire, debit)
                    VALUES (NEW.id, NEW.code, NEW.proprietaire, NEW.debit);
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


def integrite_db(db_path: str) -> Dict[str, Any]:
    """
    Vérifie l'existence des composants de la base et crée ceux qui manquent :
    - table `charge`
    - table `alertes_debit_eleve`
    - trigger `alerte_debit_eleve`

    Retourne un dict récapitulatif contenant l'état après vérification et la liste
    des éléments créés.
    """
    verif_repertoire_db(db_path)
    created = []
    # Ensure the DB file exists by opening a connection
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # charge
        logger.info("Vérification de la présence de la table 'charge'.")        
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='charge';")
        if cur.fetchone():
            has_charge = True
            logger.info("Table 'charge' existe.")
        else:
            logger.warning("Table 'charge' manquante, création en cours.")
            has_charge = False
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS charge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT,
                    proprietaire TEXT,
                    debit REAL,
                    credit REAL,
                    date DATE,
                    last_check DATE
                )
                """
            )
            created.append('charge')
            logger.info("Table 'charge' créée.")
        # alertes_debit_eleve
        logger.info("Vérification de la présence de la table 'alertes_debit_eleve'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alertes_debit_eleve';")
        if cur.fetchone():
            has_alertes = True
            logger.info("Table 'alertes_debit_eleve' existe.")
        else:
            logger.warning("Table 'alertes_debit_eleve' manquante, création en cours.")
            has_alertes = False
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS alertes_debit_eleve (
                    alerte_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_origin INTEGER NOT NULL,
                    code_proprietaire TEXT,
                    nom_proprietaire TEXT,
                    debit REAL NOT NULL,
                    date_detection DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(id_origin) REFERENCES charge(id) ON DELETE CASCADE
                );
                """
            )
            created.append('alertes_debit_eleve')
            logger.info("Table 'alertes_debit_eleve' créée.")

        # trigger alerte_debit_eleve
        logger.info("Vérification de la présence du trigger 'alerte_debit_eleve'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='alerte_debit_eleve';")
        if cur.fetchone():
            has_trigger = True
            logger.info("Trigger 'alerte_debit_eleve' existe.")
        else:
            logger.warning("Trigger 'alerte_debit_eleve' manquant, création en cours.")
            has_trigger = False
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.debit > 2000.0
                BEGIN
                    INSERT INTO alertes_debit_eleve (id_origin, code_proprietaire, nom_proprietaire, debit)
                    VALUES (NEW.id, NEW.code, NEW.proprietaire, NEW.debit);
                END;
                """
            )
            created.append('alerte_debit_eleve')
            logger.info("Trigger 'alerte_debit_eleve' créé.")

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Erreur lors de la vérification/création des composants DB : {e}")
        raise
    finally:
        conn.close()

    return {
        'charge': has_charge,
        'alertes_debit_eleve': has_alertes,
        'alerte_debit_eleve': has_trigger,
        'created': created,
    }

def enregistrer_donnees_sqlite(data: list[Any], db_path: str) -> None:
    """
    Enregistre les données extraites dans une base de données SQLite.

    La fonction se connecte à la base de données SQLite spécifiée par `db_path`,
    crée une table "charge" si elle n'existe pas, et insère les données
    fournies dans la table.

    Parameters:
    - data (list[Any]): Une liste de tuples contenant les données à enregistrer.
      Chaque tuple doit avoir le format suivant : (code, proprietaire, debit, credit, date).
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
        # Ignorer les deux premiers éléments de data (en-têtes)
        cur.executemany(
            "INSERT INTO charge (code, proprietaire, debit, credit, date, last_check) VALUES (?, ?, ?, ?, ?,?)",
            data[3:],
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Erreur lors de l'insertion des données : {e}")
        raise
    finally:
        conn.close()
    logger.info(f"{len(data)-2} enregistrements insérés dans la base de données.")
