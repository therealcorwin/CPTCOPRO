"""Module de création et vérification de l'intégrité de la base de données SQLite.

Ce module gère :
- La création des tables (charge, alertes_debit_eleve, coproprietaires, suivi_alertes, config_alerte)
- Les triggers pour la détection automatique des alertes de débit élevé
- La vérification de l'intégrité de la base de données
- La création de la vue vw_charge_coproprietaires
"""

import os
import sqlite3
from typing import Any

from loguru import logger

from .constants import DEFAULT_ALERT_THRESHOLDS, DEFAULT_THRESHOLD_FALLBACK
from .Verif_Prerequis_BDD import verif_repertoire_db

logger = logger.bind(type_log="BDD")


ALERT_TRIGGERS_SQL = """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_alertes_code_proprietaire ON alertes_debit_eleve(code_proprietaire);

    DROP TRIGGER IF EXISTS alerte_debit_eleve_insert;
    CREATE TRIGGER alerte_debit_eleve_insert
    AFTER INSERT ON charge
    FOR EACH ROW
    WHEN NEW.date = (SELECT MAX(c.date) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
      AND NEW.debit > COALESCE(
          (SELECT ca.threshold FROM config_alerte ca
           JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
           WHERE cp.code_proprietaire = NEW.code_proprietaire),
          (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
          2000.0)
    BEGIN
        INSERT INTO alertes_debit_eleve (id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, date_origin, first_detection, last_detection, occurence)
        VALUES (NEW.id, NEW.nom_proprietaire, NEW.code_proprietaire, NEW.debit,
            COALESCE((SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = NEW.code_proprietaire), 'na'),
            NEW.date,
            CURRENT_DATE, CURRENT_DATE, 1)
        ON CONFLICT(code_proprietaire) DO UPDATE SET
            id_origin = excluded.id_origin, nom_proprietaire = excluded.nom_proprietaire,
            debit = excluded.debit, type_alerte = excluded.type_alerte,
            date_origin = excluded.date_origin,
            last_detection = CASE
                WHEN DATE(COALESCE(excluded.date_origin, '0001-01-01'))
                     > DATE(COALESCE(alertes_debit_eleve.date_origin, excluded.date_origin, '0001-01-01'))
                THEN CURRENT_DATE
                ELSE alertes_debit_eleve.last_detection
            END,
            occurence = CASE
                WHEN DATE(COALESCE(excluded.date_origin, '0001-01-01'))
                     > DATE(COALESCE(alertes_debit_eleve.date_origin, excluded.date_origin, '0001-01-01'))
                THEN COALESCE(alertes_debit_eleve.occurence, 0) + 1
                ELSE COALESCE(alertes_debit_eleve.occurence, 1)
            END;
    END;

    DROP TRIGGER IF EXISTS alerte_debit_eleve_insert_clear;
    CREATE TRIGGER alerte_debit_eleve_insert_clear
    AFTER INSERT ON charge
    FOR EACH ROW
    WHEN NEW.date = (SELECT MAX(c.date) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
      AND NEW.debit <= COALESCE(
          (SELECT ca.threshold FROM config_alerte ca
           JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
           WHERE cp.code_proprietaire = NEW.code_proprietaire),
          (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
          2000.0)
    BEGIN
        DELETE FROM alertes_debit_eleve WHERE code_proprietaire = NEW.code_proprietaire;
    END;

    DROP TRIGGER IF EXISTS alerte_debit_eleve_delete;
    CREATE TRIGGER alerte_debit_eleve_delete
    AFTER DELETE ON charge
    FOR EACH ROW
    WHEN NOT EXISTS (
        SELECT 1
        FROM charge c
        WHERE c.code_proprietaire = OLD.code_proprietaire
          AND c.date > OLD.date
    )
    BEGIN
        DELETE FROM alertes_debit_eleve WHERE code_proprietaire = OLD.code_proprietaire;
        INSERT INTO alertes_debit_eleve (id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, date_origin, first_detection, last_detection, occurence)
        SELECT c.id, c.nom_proprietaire, c.code_proprietaire, c.debit,
            COALESCE((SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = c.code_proprietaire), 'na'),
            c.date,
            CURRENT_DATE, CURRENT_DATE, 1
        FROM charge c
        WHERE c.code_proprietaire = OLD.code_proprietaire
          AND c.date = (SELECT MAX(c2.date) FROM charge c2 WHERE c2.code_proprietaire = OLD.code_proprietaire)
          AND c.debit > COALESCE(
              (SELECT ca.threshold FROM config_alerte ca
               JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
               WHERE cp.code_proprietaire = OLD.code_proprietaire),
              (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
              2000.0);
    END;
"""


def verif_presence_db(db_path: str) -> bool:
    """
    Vérifie la présence du fichier de base de données SQLite.

    Args:
        db_path (str): Chemin vers la base de données SQLite.

    Returns:
        bool: True si la base existe, sinon False.
    """
    db_exists = os.path.exists(db_path)
    if db_exists:
        logger.info(f"La base de données '{db_path}' existe déjà.")
    else:
        logger.warning(f"La base de données '{db_path}' n'existe pas.")
    return db_exists


def creer_base_db(db_path: str) -> None:
    """
    Crée la base de données SQLite avec toutes les tables, vues et triggers.

    Args:
        db_path (str): Chemin vers la base de données SQLite.
    """
    logger.info("Création de la base de données SQLite...")
    conn = None
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
                date_origin DATE,
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
        cur.executescript(ALERT_TRIGGERS_SQL)
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

        # Table relance_config
        cur.execute("""
            CREATE TABLE IF NOT EXISTS relance_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER NOT NULL DEFAULT 1,
                frequency_days INTEGER NOT NULL DEFAULT 14,
                sender_name TEXT NOT NULL DEFAULT 'Syndic de copropriete',
                sender_email TEXT DEFAULT '',
                mailbox_imap_host TEXT DEFAULT '',
                mailbox_imap_port INTEGER NOT NULL DEFAULT 993,
                mailbox_imap_user TEXT DEFAULT '',
                mailbox_drafts_folder TEXT NOT NULL DEFAULT 'Drafts',
                mailbox_use_ssl INTEGER NOT NULL DEFAULT 1,
                mailbox_password_env TEXT NOT NULL DEFAULT 'RELANCE_MAILBOX_PASSWORD',
                mailbox_access_token_env TEXT NOT NULL DEFAULT 'RELANCE_MAILBOX_ACCESS_TOKEN',
                llm_provider TEXT NOT NULL DEFAULT 'mistral',
                llm_model TEXT NOT NULL DEFAULT 'mistral-small-latest',
                llm_api_base TEXT NOT NULL DEFAULT 'https://api.mistral.ai/v1',
                llm_api_key_env TEXT NOT NULL DEFAULT 'MISTRAL_API_KEY',
                llm_temperature REAL NOT NULL DEFAULT 0.4,
                tone_instruction TEXT NOT NULL DEFAULT 'courtois, professionnel et ferme',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("PRAGMA table_info(relance_config)")
        relance_config_columns = {row[1] for row in cur.fetchall()}
        if "mailbox_access_token_env" not in relance_config_columns:
            cur.execute(
                "ALTER TABLE relance_config ADD COLUMN mailbox_access_token_env "
                "TEXT NOT NULL DEFAULT 'RELANCE_MAILBOX_ACCESS_TOKEN'"
            )
        cur.execute("""
            INSERT OR IGNORE INTO relance_config (
                id,
                enabled,
                frequency_days,
                sender_name,
                sender_email,
                mailbox_imap_host,
                mailbox_imap_port,
                mailbox_imap_user,
                mailbox_drafts_folder,
                mailbox_use_ssl,
                mailbox_password_env,
                llm_provider,
                llm_model,
                llm_api_base,
                llm_api_key_env,
                llm_temperature,
                tone_instruction,
                updated_at
            )
            VALUES (1, 1, 14, 'Syndic de copropriete', '', '', 993, '', 'Drafts', 1,
                    'RELANCE_MAILBOX_PASSWORD', 'mistral', 'mistral-small-latest',
                    'https://api.mistral.ai/v1', 'MISTRAL_API_KEY', 0.4,
                    'courtois, professionnel et ferme', CURRENT_TIMESTAMP)
        """)
        logger.success("Table 'relance_config' vérifiée/créée.")

        # Table relance_destinataire
        cur.execute("""
            CREATE TABLE IF NOT EXISTS relance_destinataire (
                code_proprietaire TEXT PRIMARY KEY,
                email_to TEXT NOT NULL,
                contact_name TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(code_proprietaire) REFERENCES coproprietaires(code_proprietaire)
            )
        """)
        logger.success("Table 'relance_destinataire' vérifiée/créée.")

        # Table relance_draft
        cur.execute("""
            CREATE TABLE IF NOT EXISTS relance_draft (
                draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_proprietaire TEXT NOT NULL,
                nom_proprietaire TEXT,
                debit REAL,
                email_to TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                llm_provider TEXT,
                llm_model TEXT,
                status TEXT NOT NULL DEFAULT 'draft_local',
                remote_draft_id TEXT,
                error_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                validated_at DATETIME,
                sent_at DATETIME,
                FOREIGN KEY(code_proprietaire) REFERENCES coproprietaires(code_proprietaire)
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_relance_draft_code_created ON relance_draft(code_proprietaire, created_at DESC)"
        )
        logger.success("Table 'relance_draft' vérifiée/créée.")

        # Table relance_template
        cur.execute("""
            CREATE TABLE IF NOT EXISTS relance_template (
                template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                subject_template TEXT NOT NULL,
                body_template TEXT NOT NULL,
                generation_mode TEXT NOT NULL DEFAULT 'static',
                tone_instruction TEXT NOT NULL DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.success("Table 'relance_template' vérifiée/créée.")

        conn.commit()
        logger.success(f"Base de données '{db_path}' créée avec succès.")
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error as rollback_error:
                logger.warning(f"Rollback impossible lors de la création DB : {rollback_error}")
        logger.error(f"Erreur lors de la création de la base de données : {e}")
        raise
    finally:
        if conn is not None:
            conn.close()


def integrite_db(db_path: str) -> dict[str, Any]:
    """
    Vérifie l'existence des composants de la base et crée ceux qui manquent.

    Retourne un dict récapitulatif contenant l'état après vérification et la liste
    des éléments créés.
    """
    verif_repertoire_db(db_path)
    created = []
    conn = None
    has_config_alerte = False

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Table charge
        logger.info("Vérification de la présence de la table 'charge'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='charge';")
        if cur.fetchone():
            has_charge = True
            logger.info("Table 'charge' existe.")
            # Vérifier/créer l'index UNIQUE pour éviter les doublons
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_charge_unique';"
            )
            if not cur.fetchone():
                logger.info("Création de l'index UNIQUE sur (code_proprietaire, date)...")
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
            cur.execute("PRAGMA table_info(alertes_debit_eleve)")
            colonnes_alertes = {row[1] for row in cur.fetchall()}
            if "date_origin" not in colonnes_alertes:
                cur.execute("ALTER TABLE alertes_debit_eleve ADD COLUMN date_origin DATE")
                created.append("alertes_debit_eleve.date_origin")
                logger.info("Colonne 'date_origin' ajoutée à 'alertes_debit_eleve'.")
            # Safety net permanent : corrige les type_alerte corrompus (vides ou NULL)
            cur.execute("""
                UPDATE alertes_debit_eleve
                SET type_alerte = COALESCE(
                    (SELECT LOWER(cp.type_apt) FROM coproprietaires cp
                     WHERE cp.code_proprietaire = alertes_debit_eleve.code_proprietaire
                       AND cp.type_apt != ''),
                    'na'
                )
                WHERE type_alerte IS NULL OR type_alerte = ''
            """)
            fixed_types = cur.rowcount
            if fixed_types:
                created.append(f"alertes_debit_eleve.type_alerte({fixed_types} lignes)")
                logger.info(
                    f"{fixed_types} ligne(s) 'alertes_debit_eleve' avec type_alerte vide corrigée(s)."
                )
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
                    date_origin DATE,
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
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config_alerte';")
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
        logger.info("Vérification et mise à jour des triggers 'alerte_debit_eleve'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='alerte_debit_eleve_insert';"
        )
        if cur.fetchone():
            has_trigger = True
            logger.info("Trigger 'alerte_debit_eleve' existe.")
        else:
            logger.warning("Trigger 'alerte_debit_eleve' manquant, création en cours.")
            has_trigger = False
            created.append("alerte_debit_eleve")

        cur.executescript(ALERT_TRIGGERS_SQL)

        # Table coproprietaires
        logger.info("Vérification de la présence de la table 'coproprietaires'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coproprietaires';")
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
        logger.info("Vérification de la présence de la vue 'vw_charge_coproprietaires'.")
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
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='suivi_alertes';")
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

        # Table relance_config
        logger.info("Vérification de la présence de la table 'relance_config'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='relance_config';")
        if cur.fetchone():
            has_relance_config = True
            logger.info("Table 'relance_config' existe.")
            cur.execute("PRAGMA table_info(relance_config)")
            relance_config_columns = {row[1] for row in cur.fetchall()}
            if "mailbox_access_token_env" not in relance_config_columns:
                logger.warning(
                    "Colonne 'mailbox_access_token_env' manquante dans 'relance_config', ajout en cours."
                )
                cur.execute(
                    "ALTER TABLE relance_config ADD COLUMN mailbox_access_token_env "
                    "TEXT NOT NULL DEFAULT 'RELANCE_MAILBOX_ACCESS_TOKEN'"
                )
        else:
            has_relance_config = False
            logger.warning("Table 'relance_config' manquante, création en cours.")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    frequency_days INTEGER NOT NULL DEFAULT 14,
                    sender_name TEXT NOT NULL DEFAULT 'Syndic de copropriete',
                    sender_email TEXT DEFAULT '',
                    mailbox_imap_host TEXT DEFAULT '',
                    mailbox_imap_port INTEGER NOT NULL DEFAULT 993,
                    mailbox_imap_user TEXT DEFAULT '',
                    mailbox_drafts_folder TEXT NOT NULL DEFAULT 'Drafts',
                    mailbox_use_ssl INTEGER NOT NULL DEFAULT 1,
                    mailbox_password_env TEXT NOT NULL DEFAULT 'RELANCE_MAILBOX_PASSWORD',
                    mailbox_access_token_env TEXT NOT NULL DEFAULT 'RELANCE_MAILBOX_ACCESS_TOKEN',
                    llm_provider TEXT NOT NULL DEFAULT 'mistral',
                    llm_model TEXT NOT NULL DEFAULT 'mistral-small-latest',
                    llm_api_base TEXT NOT NULL DEFAULT 'https://api.mistral.ai/v1',
                    llm_api_key_env TEXT NOT NULL DEFAULT 'MISTRAL_API_KEY',
                    llm_temperature REAL NOT NULL DEFAULT 0.4,
                    tone_instruction TEXT NOT NULL DEFAULT 'courtois, professionnel et ferme',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                INSERT OR IGNORE INTO relance_config (
                    id,
                    enabled,
                    frequency_days,
                    sender_name,
                    sender_email,
                    mailbox_imap_host,
                    mailbox_imap_port,
                    mailbox_imap_user,
                    mailbox_drafts_folder,
                    mailbox_use_ssl,
                    mailbox_password_env,
                    mailbox_access_token_env,
                    llm_provider,
                    llm_model,
                    llm_api_base,
                    llm_api_key_env,
                    llm_temperature,
                    tone_instruction,
                    updated_at
                )
                VALUES (1, 1, 14, 'Syndic de copropriete', '', '', 993, '', 'Drafts', 1,
                    'RELANCE_MAILBOX_PASSWORD', 'RELANCE_MAILBOX_ACCESS_TOKEN', 'mistral', 'mistral-small-latest',
                        'https://api.mistral.ai/v1', 'MISTRAL_API_KEY', 0.4,
                        'courtois, professionnel et ferme', CURRENT_TIMESTAMP)
            """)
            created.append("relance_config")

        # Table relance_destinataire
        logger.info("Vérification de la présence de la table 'relance_destinataire'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='relance_destinataire';"
        )
        if cur.fetchone():
            has_relance_destinataire = True
            logger.info("Table 'relance_destinataire' existe.")
        else:
            has_relance_destinataire = False
            logger.warning("Table 'relance_destinataire' manquante, création en cours.")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_destinataire (
                    code_proprietaire TEXT PRIMARY KEY,
                    email_to TEXT NOT NULL,
                    contact_name TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(code_proprietaire) REFERENCES coproprietaires(code_proprietaire)
                )
            """)
            created.append("relance_destinataire")

        # Table relance_draft
        logger.info("Vérification de la présence de la table 'relance_draft'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='relance_draft';")
        if cur.fetchone():
            has_relance_draft = True
            logger.info("Table 'relance_draft' existe.")
        else:
            has_relance_draft = False
            logger.warning("Table 'relance_draft' manquante, création en cours.")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_draft (
                    draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_proprietaire TEXT NOT NULL,
                    nom_proprietaire TEXT,
                    debit REAL,
                    email_to TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    llm_provider TEXT,
                    llm_model TEXT,
                    status TEXT NOT NULL DEFAULT 'draft_local',
                    remote_draft_id TEXT,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    validated_at DATETIME,
                    sent_at DATETIME,
                    FOREIGN KEY(code_proprietaire) REFERENCES coproprietaires(code_proprietaire)
                )
            """)
            created.append("relance_draft")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_relance_draft_code_created ON relance_draft(code_proprietaire, created_at DESC)"
        )

        # Table relance_template
        logger.info("Vérification de la présence de la table 'relance_template'.")
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='relance_template';"
        )
        if cur.fetchone():
            has_relance_template = True
            logger.info("Table 'relance_template' existe.")
            cur.execute("PRAGMA table_info(relance_template)")
            relance_template_columns = {row[1] for row in cur.fetchall()}
            if "generation_mode" not in relance_template_columns:
                logger.warning(
                    "Colonne 'generation_mode' manquante dans 'relance_template', ajout en cours."
                )
                cur.execute(
                    "ALTER TABLE relance_template ADD COLUMN generation_mode "
                    "TEXT NOT NULL DEFAULT 'static'"
                )
            if "tone_instruction" not in relance_template_columns:
                logger.warning(
                    "Colonne 'tone_instruction' manquante dans 'relance_template', ajout en cours."
                )
                cur.execute(
                    "ALTER TABLE relance_template ADD COLUMN tone_instruction "
                    "TEXT NOT NULL DEFAULT ''"
                )
        else:
            has_relance_template = False
            logger.warning("Table 'relance_template' manquante, création en cours.")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_template (
                    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    subject_template TEXT NOT NULL,
                    body_template TEXT NOT NULL,
                    generation_mode TEXT NOT NULL DEFAULT 'static',
                    tone_instruction TEXT NOT NULL DEFAULT '',
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            created.append("relance_template")

        # Commit final explicite pour persister toutes les creations/migrations.
        conn.commit()

    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error as rollback_error:
                logger.warning(f"Rollback impossible lors de la vérification DB : {rollback_error}")
        logger.error(f"Erreur lors de la vérification/création des composants DB : {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

    return {
        "charge": has_charge,
        "alertes_debit_eleve": has_alertes,
        "alerte_debit_eleve": has_trigger,
        "coproprietaires": has_coproprietaires,
        "nombre_alertes": has_nombre_alertes,
        "config_alerte": has_config_alerte,
        "relance_config": has_relance_config,
        "relance_destinataire": has_relance_destinataire,
        "relance_draft": has_relance_draft,
        "relance_template": has_relance_template,
        "created": created,
    }


def purger_alertes_pour_rebuild(db_path: str) -> None:
    """Vide alertes_debit_eleve et nettoie suivi_alertes des entrées sans charge correspondante."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM alertes_debit_eleve")
        # Supprimer les entrées suivi_alertes dont date_releve n'a pas de charge
        # correspondante — artefacts de l'ancienne sémantique MAX(last_detection).
        conn.execute("""
            DELETE FROM suivi_alertes
            WHERE NOT EXISTS (
                SELECT 1 FROM charge WHERE date = suivi_alertes.date_releve
            )
        """)
        conn.commit()
        logger.info(
            "Tables 'alertes_debit_eleve' et 'suivi_alertes' (entrées orphelines) purgées après restore pCloud."
        )
    except Exception as e:
        conn.rollback()
        logger.error(f"Erreur lors de la purge des alertes : {e}")
        raise
    finally:
        conn.close()
