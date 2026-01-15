"""Module de création et vérification de l'intégrité de la base de données SQLite.

Ce module gère :
- La création des tables (charge, alertes_debit_eleve, coproprietaires, suivi_alertes, config_alerte)
- Les triggers pour la détection automatique des alertes de débit élevé
- La vérification de l'intégrité de la base de données
- La création de la vue vw_charge_coproprietaires
"""

import os
import sqlite3
from typing import Any, Dict
from loguru import logger

from .constants import DEFAULT_ALERT_THRESHOLDS, DEFAULT_THRESHOLD_FALLBACK
from .Verif_Prerequis_BDD import verif_repertoire_db

logger = logger.bind(type_log="BDD")


def verif_presence_db(db_path: str) -> None:
    """
    Vérifie la présence de la base de données SQLite.
    Si elle n'existe pas, la crée avec toutes les tables et triggers.

    Args:
        db_path (str): Chemin vers la base de données SQLite.
    """
    if not os.path.exists(db_path):
        logger.warning(f"La base de données '{db_path}' n'existe pas.")
        logger.info("Création de la base de données SQLite...")
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            # Table charge
            cur.execute("""
                CREATE TABLE IF NOT EXISTS charge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT,
                    debit REAL,
                    credit REAL,
                    date DATE,
                    last_check DATE DEFAULT CURRENT_DATE,
                    UNIQUE(code_proprietaire, date)
                )
            """)
            logger.info("Table 'charge' vérifiée/créée.")

            # Table alertes_debit_eleve
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alertes_debit_eleve (
                    alerte_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_origin INTEGER NOT NULL,
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT,
                    debit REAL NOT NULL,
                    type_alerte text NOT NULL,
                    last_detection DATE DEFAULT CURRENT_DATE,
                    first_detection DATE DEFAULT CURRENT_DATE,
                    occurence INTEGER NOT NULL,
                    FOREIGN KEY(id_origin) REFERENCES charge(id) ON DELETE CASCADE
                );
            """)
            logger.success("Table 'alertes_debit_eleve' vérifiée/créée.")

            # Table config_alerte
            cur.execute("""
                CREATE TABLE IF NOT EXISTS config_alerte (
                    type_apt TEXT PRIMARY KEY,
                    charge_moyenne REAL NOT NULL,
                    taux REAL NOT NULL DEFAULT 1.33,
                    threshold REAL NOT NULL,
                    last_update DATE DEFAULT CURRENT_DATE
                );
            """)
            logger.success("Table 'config_alerte' vérifiée/créée.")

            # Initialiser les seuils par défaut
            for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
                cur.execute(
                    """
                    INSERT OR IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                    VALUES (?, ?, ?, ?, CURRENT_DATE)
                """,
                    (
                        type_apt,
                        config["charge_moyenne"],
                        config["taux"],
                        config["threshold"],
                    ),
                )

            cur.execute(
                """
                INSERT OR IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                VALUES ('default', ?, 1.0, ?, CURRENT_DATE)
            """,
                (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK),
            )
            logger.info("Seuils d'alerte par défaut initialisés.")

            # Index et triggers
            cur.executescript("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alertes_code_proprietaire ON alertes_debit_eleve(code_proprietaire);

                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                  AND NEW.debit > COALESCE(
                      (SELECT ca.threshold FROM config_alerte ca 
                       JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                       WHERE cp.code_proprietaire = NEW.code_proprietaire),
                      (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                      2000.0)
                BEGIN
                    INSERT INTO alertes_debit_eleve (id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, first_detection, last_detection, occurence)
                    VALUES (NEW.id, NEW.nom_proprietaire, NEW.code_proprietaire, NEW.debit,
                        COALESCE((SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = NEW.code_proprietaire), 'na'),
                        CURRENT_DATE, CURRENT_DATE, 1)
                    ON CONFLICT(code_proprietaire) DO UPDATE SET
                        id_origin = excluded.id_origin, nom_proprietaire = excluded.nom_proprietaire,
                        debit = excluded.debit, type_alerte = excluded.type_alerte,
                        last_detection = CURRENT_DATE, occurence = COALESCE(occurence, 0) + 1;
                END;

                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert_clear
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                  AND NEW.debit <= COALESCE(
                      (SELECT ca.threshold FROM config_alerte ca 
                       JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                       WHERE cp.code_proprietaire = NEW.code_proprietaire),
                      (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                      2000.0)
                BEGIN
                    DELETE FROM alertes_debit_eleve WHERE code_proprietaire = NEW.code_proprietaire;
                END;

                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_delete
                AFTER DELETE ON charge
                FOR EACH ROW
                WHEN OLD.id >= COALESCE((SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire), 0)
                BEGIN
                    DELETE FROM alertes_debit_eleve WHERE code_proprietaire = OLD.code_proprietaire;
                    INSERT INTO alertes_debit_eleve (id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, first_detection, last_detection, occurence)
                    SELECT c.id, c.nom_proprietaire, c.code_proprietaire, c.debit,
                        COALESCE((SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = c.code_proprietaire), 'na'),
                        CURRENT_DATE, CURRENT_DATE, 1
                    FROM charge c
                    WHERE c.code_proprietaire = OLD.code_proprietaire
                      AND c.id = (SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire)
                      AND c.debit > COALESCE(
                          (SELECT ca.threshold FROM config_alerte ca 
                           JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                           WHERE cp.code_proprietaire = OLD.code_proprietaire),
                          (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                          2000.0);
                END;
            """)
            logger.info("Triggers 'alerte_debit_eleve' créés.")

            # Table coproprietaires
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coproprietaires (
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT PRIMARY KEY,
                    num_apt TEXT DEFAULT 'NA',
                    type_apt TEXT DEFAULT 'NA',
                    last_check DATE DEFAULT CURRENT_DATE
                )
            """)
            logger.success("Table 'coproprietaires' vérifiée/créée.")

            # Vue
            cur.executescript("""
                CREATE VIEW IF NOT EXISTS vw_charge_coproprietaires AS
                SELECT
                    (SELECT COUNT(*) FROM charge c2 WHERE c2.id <= c.id) AS id,
                    c.nom_proprietaire AS nom_proprietaire,
                    c.code_proprietaire AS code_proprietaire,
                    c.debit AS debit,
                    c.credit AS credit,
                    COALESCE(cp.num_apt, 'NA') AS num_apt,
                    COALESCE(cp.type_apt, 'NA') AS type_apt,
                    c.date AS date
                FROM charge c
                LEFT JOIN coproprietaires cp ON c.code_proprietaire = cp.code_proprietaire;
            """)
            logger.success("View 'vw_charge_coproprietaires' créée.")

            # Table suivi_alertes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS suivi_alertes (
                    date_releve DATE PRIMARY KEY,
                    nombre_alertes INTEGER NOT NULL,
                    total_debit REAL NOT NULL,
                    nb_2p INTEGER DEFAULT 0,
                    nb_3p INTEGER DEFAULT 0,
                    nb_4p INTEGER DEFAULT 0,
                    nb_5p INTEGER DEFAULT 0,
                    nb_na INTEGER DEFAULT 0,
                    debit_2p REAL DEFAULT 0,
                    debit_3p REAL DEFAULT 0,
                    debit_4p REAL DEFAULT 0,
                    debit_5p REAL DEFAULT 0,
                    debit_na REAL DEFAULT 0
                )
            """)
            logger.success("Table 'suivi_alertes' vérifiée/créée.")

            conn.commit()
            conn.close()
            logger.success(f"Base de données '{db_path}' créée avec succès.")
        except Exception as e:
            logger.error(f"Erreur lors de la création de la base de données : {e}")
            raise
    else:
        logger.info(f"La base de données '{db_path}' existe déjà.")


def integrite_db(db_path: str) -> Dict[str, Any]:
    """
    Vérifie l'existence des composants de la base et crée ceux qui manquent.

    Retourne un dict récapitulatif contenant l'état après vérification et la liste
    des éléments créés.
    """
    verif_repertoire_db(db_path)
    created = []
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    has_config_alerte = False

    try:
        # Table charge
        logger.info("Vérification de la présence de la table 'charge'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='charge';"
        )
        if cur.fetchone():
            has_charge = True
            logger.info("Table 'charge' existe.")
            # Vérifier/créer l'index UNIQUE pour éviter les doublons
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_charge_unique';"
            )
            if not cur.fetchone():
                logger.info(
                    "Création de l'index UNIQUE sur (code_proprietaire, date)..."
                )
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_charge_unique ON charge(code_proprietaire, date);"
                )
                created.append("idx_charge_unique")
                logger.success("Index 'idx_charge_unique' créé.")
        else:
            logger.warning("Table 'charge' manquante, création en cours.")
            has_charge = False
            cur.execute("""
                CREATE TABLE IF NOT EXISTS charge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT,
                    debit REAL,
                    credit REAL,
                    date DATE,
                    last_check DATE DEFAULT CURRENT_DATE,
                    UNIQUE(code_proprietaire, date)
                )
            """)
            created.append("charge")
            logger.info("Table 'charge' créée.")

        # Table alertes_debit_eleve
        logger.info("Vérification de la présence de la table 'alertes_debit_eleve'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alertes_debit_eleve';"
        )
        if cur.fetchone():
            has_alertes = True
            logger.info("Table 'alertes_debit_eleve' existe.")
        else:
            logger.warning("Table 'alertes_debit_eleve' manquante, création en cours.")
            has_alertes = False
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alertes_debit_eleve (
                    alerte_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_origin INTEGER NOT NULL,
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT,
                    debit REAL NOT NULL,
                    type_alerte text NOT NULL,
                    last_detection DATE DEFAULT CURRENT_DATE,
                    first_detection DATE DEFAULT CURRENT_DATE,
                    occurence INTEGER NOT NULL,
                    FOREIGN KEY(id_origin) REFERENCES charge(id) ON DELETE CASCADE
                );
            """)
            created.append("alertes_debit_eleve")
            logger.info("Table 'alertes_debit_eleve' créée.")

        # Table config_alerte
        logger.info("Vérification de la présence de la table 'config_alerte'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='config_alerte';"
        )
        if cur.fetchone():
            has_config_alerte = True
            logger.info("Table 'config_alerte' existe.")
        else:
            logger.warning("Table 'config_alerte' manquante, création en cours.")
            has_config_alerte = False
            cur.execute("""
                CREATE TABLE IF NOT EXISTS config_alerte (
                    type_apt TEXT PRIMARY KEY,
                    charge_moyenne REAL NOT NULL,
                    taux REAL NOT NULL DEFAULT 1.33,
                    threshold REAL NOT NULL,
                    last_update DATE DEFAULT CURRENT_DATE
                );
            """)
            for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
                cur.execute(
                    """
                    INSERT OR IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                    VALUES (?, ?, ?, ?, CURRENT_DATE)
                """,
                    (
                        type_apt,
                        config["charge_moyenne"],
                        config["taux"],
                        config["threshold"],
                    ),
                )
            cur.execute(
                """
                INSERT OR IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                VALUES ('default', ?, 1.0, ?, CURRENT_DATE)
            """,
                (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK),
            )
            created.append("config_alerte")
            logger.info("Table 'config_alerte' créée avec seuils par défaut.")

        # Trigger alerte_debit_eleve
        logger.info("Vérification de la présence du trigger 'alerte_debit_eleve'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='alerte_debit_eleve_insert';"
        )
        if cur.fetchone():
            has_trigger = True
            logger.info("Trigger 'alerte_debit_eleve' existe.")
        else:
            logger.warning("Trigger 'alerte_debit_eleve' manquant, création en cours.")
            has_trigger = False
            cur.executescript("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alertes_code_proprietaire ON alertes_debit_eleve(code_proprietaire);
                
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                  AND NEW.debit > COALESCE(
                      (SELECT ca.threshold FROM config_alerte ca 
                       JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                       WHERE cp.code_proprietaire = NEW.code_proprietaire),
                      (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                      2000.0)
                BEGIN
                    INSERT INTO alertes_debit_eleve (id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, first_detection, last_detection, occurence)
                    VALUES (NEW.id, NEW.nom_proprietaire, NEW.code_proprietaire, NEW.debit,
                        COALESCE((SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = NEW.code_proprietaire), 'na'),
                        CURRENT_DATE, CURRENT_DATE, 1)
                    ON CONFLICT(code_proprietaire) DO UPDATE SET
                        id_origin = excluded.id_origin, nom_proprietaire = excluded.nom_proprietaire,
                        debit = excluded.debit, type_alerte = excluded.type_alerte,
                        last_detection = CURRENT_DATE, occurence = COALESCE(occurence, 0) + 1;
                END;
                
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert_clear
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                  AND NEW.debit <= COALESCE(
                      (SELECT ca.threshold FROM config_alerte ca 
                       JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                       WHERE cp.code_proprietaire = NEW.code_proprietaire),
                      (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                      2000.0)
                BEGIN
                    DELETE FROM alertes_debit_eleve WHERE code_proprietaire = NEW.code_proprietaire;
                END;
                
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_delete
                AFTER DELETE ON charge
                FOR EACH ROW
                WHEN OLD.id >= COALESCE((SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire), 0)
                BEGIN
                    DELETE FROM alertes_debit_eleve WHERE code_proprietaire = OLD.code_proprietaire;
                    INSERT INTO alertes_debit_eleve (id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, first_detection, last_detection, occurence)
                    SELECT c.id, c.nom_proprietaire, c.code_proprietaire, c.debit,
                        COALESCE((SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = c.code_proprietaire), 'na'),
                        CURRENT_DATE, CURRENT_DATE, 1
                    FROM charge c
                    WHERE c.code_proprietaire = OLD.code_proprietaire
                      AND c.id = (SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire)
                      AND c.debit > COALESCE(
                          (SELECT ca.threshold FROM config_alerte ca 
                           JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                           WHERE cp.code_proprietaire = OLD.code_proprietaire),
                          (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                          2000.0);
                END;
            """)
            created.append("alerte_debit_eleve")

        # Table coproprietaires
        logger.info("Vérification de la présence de la table 'coproprietaires'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='coproprietaires';"
        )
        if cur.fetchone():
            has_coproprietaires = True
            logger.info("Table 'coproprietaires' existe.")
        else:
            logger.warning("Table 'coproprietaires' manquante, création en cours.")
            has_coproprietaires = False
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coproprietaires (
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT PRIMARY KEY,
                    num_apt TEXT DEFAULT 'NA',
                    type_apt TEXT DEFAULT 'NA',
                    last_check DATE DEFAULT CURRENT_DATE
                )
            """)
            created.append("coproprietaires")
            logger.info("Table 'coproprietaires' créée.")

        conn.commit()

        # Vue vw_charge_coproprietaires
        logger.info(
            "Vérification de la présence de la vue 'vw_charge_coproprietaires'."
        )
        try:
            cur.executescript("""
                CREATE VIEW IF NOT EXISTS vw_charge_coproprietaires AS
                SELECT
                    (SELECT COUNT(*) FROM charge c2 WHERE c2.id <= c.id) AS id,
                    c.nom_proprietaire AS nom_proprietaire,
                    c.code_proprietaire AS code_proprietaire,
                    c.debit AS debit,
                    c.credit AS credit,
                    COALESCE(cp.num_apt, 'NA') AS num_apt,
                    COALESCE(cp.type_apt, 'NA') AS type_apt,
                    c.date AS date
                FROM charge c
                LEFT JOIN coproprietaires cp ON c.code_proprietaire = cp.code_proprietaire;
            """)
            logger.success("View 'vw_charge_coproprietaires' créée/assurée.")
        except Exception as e:
            logger.error(f"Impossible de créer la vue vw_charge_coproprietaires : {e}")

        # Table suivi_alertes
        logger.info("Vérification de la présence de la table 'suivi_alertes'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='suivi_alertes';"
        )
        if cur.fetchone():
            has_nombre_alertes = True
            logger.info("Table 'suivi_alertes' existe.")
        else:
            logger.warning("Table 'suivi_alertes' manquante, création en cours.")
            has_nombre_alertes = False
            cur.execute("""
                CREATE TABLE IF NOT EXISTS suivi_alertes (
                    date_releve DATE PRIMARY KEY,
                    nombre_alertes INTEGER NOT NULL,
                    total_debit REAL NOT NULL,
                    nb_2p INTEGER DEFAULT 0,
                    nb_3p INTEGER DEFAULT 0,
                    nb_4p INTEGER DEFAULT 0,
                    nb_5p INTEGER DEFAULT 0,
                    nb_na INTEGER DEFAULT 0,
                    debit_2p REAL DEFAULT 0,
                    debit_3p REAL DEFAULT 0,
                    debit_4p REAL DEFAULT 0,
                    debit_5p REAL DEFAULT 0,
                    debit_na REAL DEFAULT 0
                )
            """)
            logger.success("Table 'suivi_alertes' vérifiée/créée.")
            created.append("suivi_alertes")

    except Exception as e:
        conn.rollback()
        logger.error(f"Erreur lors de la vérification/création des composants DB : {e}")
        raise
    finally:
        conn.close()

    return {
        "charge": has_charge,
        "alertes_debit_eleve": has_alertes,
        "alerte_debit_eleve": has_trigger,
        "coproprietaires": has_coproprietaires,
        "nombre_alertes": has_nombre_alertes,
        "config_alerte": has_config_alerte,
        "created": created,
    }
