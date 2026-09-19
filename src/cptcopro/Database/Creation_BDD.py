"""Module de creation et verification de l integrite de la base de donnees MariaDB.

Ce module gere :
- La creation des tables (charge, alertes_debit_eleve, coproprietaires, suivi_alertes, config_alerte,
  relance_config, relance_destinataire, relance_draft, relance_template)
- Les triggers pour la detection automatique des alertes de debit eleve (MariaDB)
- La verification de l integrite de la base de donnees (via INFORMATION_SCHEMA)
- La creation de la vue vw_charge_coproprietaires avec ROW_NUMBER()
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pymysql.cursors import Cursor

from .connection import get_db_connection, get_db_cursor
from .constants import DEFAULT_ALERT_THRESHOLDS, DEFAULT_THRESHOLD_FALLBACK

_logger = logger.bind(type_log="BDD")

# Triggers MariaDB individuels
TRIGGER_INSERT_SQL = """
CREATE OR REPLACE TRIGGER alerte_debit_eleve_insert
AFTER INSERT ON charge FOR EACH ROW
BEGIN
    IF NEW.date = (SELECT MAX(c.date) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
       AND NEW.debit > COALESCE(
           (SELECT ca.threshold FROM config_alerte ca
            JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
            WHERE cp.code_proprietaire = NEW.code_proprietaire),
           (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
           2000.0) THEN
        INSERT INTO alertes_debit_eleve
            (id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, date_origin, first_detection, last_detection, occurence)
        VALUES
            (NEW.id, NEW.nom_proprietaire, NEW.code_proprietaire, NEW.debit,
             COALESCE((SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = NEW.code_proprietaire), 'na'),
             NEW.date, CURRENT_DATE, CURRENT_DATE, 1)
        ON DUPLICATE KEY UPDATE
            id_origin = VALUES(id_origin),
            nom_proprietaire = VALUES(nom_proprietaire),
            debit = VALUES(debit),
            type_alerte = VALUES(type_alerte),
            last_detection = CASE
                WHEN VALUES(date_origin) > alertes_debit_eleve.date_origin
                THEN CURRENT_DATE
                ELSE alertes_debit_eleve.last_detection
            END,
            occurence = CASE
                WHEN VALUES(date_origin) > alertes_debit_eleve.date_origin
                THEN COALESCE(alertes_debit_eleve.occurence, 0) + 1
                ELSE COALESCE(alertes_debit_eleve.occurence, 1)
            END,
            date_origin = VALUES(date_origin);
    END IF;
END;
"""

TRIGGER_INSERT_CLEAR_SQL = """
CREATE OR REPLACE TRIGGER alerte_debit_eleve_insert_clear
AFTER INSERT ON charge FOR EACH ROW
BEGIN
    IF NEW.date = (SELECT MAX(c.date) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
       AND NEW.debit <= COALESCE(
           (SELECT ca.threshold FROM config_alerte ca
            JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
            WHERE cp.code_proprietaire = NEW.code_proprietaire),
           (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
           2000.0) THEN
        DELETE FROM alertes_debit_eleve WHERE code_proprietaire = NEW.code_proprietaire;
    END IF;
END;
"""

TRIGGER_DELETE_SQL = """
CREATE OR REPLACE TRIGGER alerte_debit_eleve_delete
AFTER DELETE ON charge FOR EACH ROW
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM charge c
        WHERE c.code_proprietaire = OLD.code_proprietaire
          AND c.date > OLD.date
    ) THEN
        DELETE FROM alertes_debit_eleve WHERE code_proprietaire = OLD.code_proprietaire;
        INSERT INTO alertes_debit_eleve
            (id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, date_origin, first_detection, last_detection, occurence)
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
    END IF;
END;
"""


def verif_presence_db(db_path: str | None = None) -> bool:
    """Verifie si la base de donnees est initialisee (presence de la table charge)."""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'charge'
            """)
            exists = cur.fetchone() is not None
            if exists:
                _logger.info("La table 'charge' existe dans MariaDB.")
            else:
                _logger.warning("La table 'charge' n'existe pas dans MariaDB.")
            return exists
    except Exception as exc:
        _logger.error(f"Erreur lors de la verification de la presence de la BDD : {exc}")
        return False


def creer_base_db(db_path: str | None = None) -> None:
    """Cree toutes les tables, vues, index et triggers dans MariaDB."""
    _logger.info("Creation de la base de donnees MariaDB...")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. Table charge (avec System Versioning)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS charge (
                    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    nom_proprietaire VARCHAR(255),
                    code_proprietaire VARCHAR(50),
                    debit DECIMAL(12, 2),
                    credit DECIMAL(12, 2),
                    date DATE,
                    last_check DATE DEFAULT CURRENT_DATE,
                    UNIQUE KEY uq_code_date (code_proprietaire, date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci WITH SYSTEM VERSIONING;
            """)
            _logger.info("Table 'charge' verifiee/creee.")

            # 2. Table config_alerte
            cur.execute("""
                CREATE TABLE IF NOT EXISTS config_alerte (
                    type_apt VARCHAR(50) PRIMARY KEY,
                    charge_moyenne DECIMAL(12, 2) NOT NULL,
                    taux DECIMAL(12, 2) NOT NULL DEFAULT 1.33,
                    threshold DECIMAL(12, 2) NOT NULL,
                    last_update DATE DEFAULT CURRENT_DATE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            _logger.success("Table 'config_alerte' verifiee/creee.")

            # Initialiser les seuils par defaut
            for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
                cur.execute(
                    """
                    INSERT IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                    VALUES (%s, %s, %s, %s, CURRENT_DATE)
                """,
                    (type_apt, config["charge_moyenne"], config["taux"], config["threshold"]),
                )

            cur.execute(
                """
                INSERT IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                VALUES ('default', %s, 1.0, %s, CURRENT_DATE)
            """,
                (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK),
            )
            _logger.info("Seuils d'alerte par defaut initialises.")

            # 3. Table coproprietaires
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coproprietaires (
                    nom_proprietaire VARCHAR(255),
                    code_proprietaire VARCHAR(50) PRIMARY KEY,
                    num_apt VARCHAR(50) DEFAULT 'NA',
                    type_apt VARCHAR(50) DEFAULT 'NA',
                    last_check DATE DEFAULT CURRENT_DATE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            _logger.success("Table 'coproprietaires' verifiee/creee.")

            # 4. Table alertes_debit_eleve
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alertes_debit_eleve (
                    alerte_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    id_origin INT UNSIGNED NOT NULL,
                    nom_proprietaire VARCHAR(255),
                    code_proprietaire VARCHAR(50),
                    debit DECIMAL(12, 2) NOT NULL,
                    type_alerte VARCHAR(50) NOT NULL,
                    date_origin DATE,
                    last_detection DATE DEFAULT CURRENT_DATE,
                    first_detection DATE DEFAULT CURRENT_DATE,
                    occurence INT NOT NULL,
                    UNIQUE KEY idx_alertes_code_proprietaire (code_proprietaire),
                    FOREIGN KEY (id_origin) REFERENCES charge(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            _logger.success("Table 'alertes_debit_eleve' verifiee/creee.")

            # 5. Index supplementaires
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_alertes_code ON alertes_debit_eleve(code_proprietaire);"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_charge_date ON charge(date DESC);")

            # 6. Triggers MariaDB
            cur.execute(TRIGGER_INSERT_SQL)
            cur.execute(TRIGGER_INSERT_CLEAR_SQL)
            cur.execute(TRIGGER_DELETE_SQL)
            _logger.info("Triggers 'alerte_debit_eleve' crees.")

            # 7. Vue vw_charge_coproprietaires avec ROW_NUMBER()
            cur.execute("""
                CREATE OR REPLACE VIEW vw_charge_coproprietaires AS
                SELECT
                    ROW_NUMBER() OVER (ORDER BY c.id) AS id,
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
            _logger.success("View 'vw_charge_coproprietaires' creee avec ROW_NUMBER().")

            # 8. Table suivi_alertes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS suivi_alertes (
                    date_releve DATE PRIMARY KEY,
                    nombre_alertes INT NOT NULL,
                    total_debit DECIMAL(12, 2) NOT NULL,
                    nb_2p INT DEFAULT 0,
                    nb_3p INT DEFAULT 0,
                    nb_4p INT DEFAULT 0,
                    nb_5p INT DEFAULT 0,
                    nb_na INT DEFAULT 0,
                    debit_2p DECIMAL(12, 2) DEFAULT 0,
                    debit_3p DECIMAL(12, 2) DEFAULT 0,
                    debit_4p DECIMAL(12, 2) DEFAULT 0,
                    debit_5p DECIMAL(12, 2) DEFAULT 0,
                    debit_na DECIMAL(12, 2) DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            _logger.success("Table 'suivi_alertes' verifiee/creee.")

            # 9. Table relance_config
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_config (
                    id INT PRIMARY KEY CHECK (id = 1),
                    enabled TINYINT(1) NOT NULL DEFAULT 1,
                    frequency_days INT NOT NULL DEFAULT 14,
                    sender_name VARCHAR(255) NOT NULL DEFAULT 'Syndic de copropriete',
                    sender_email VARCHAR(255) DEFAULT '',
                    mailbox_imap_host VARCHAR(255) DEFAULT '',
                    mailbox_imap_port INT NOT NULL DEFAULT 993,
                    mailbox_imap_user VARCHAR(255) DEFAULT '',
                    mailbox_drafts_folder VARCHAR(255) NOT NULL DEFAULT 'Drafts',
                    mailbox_use_ssl TINYINT(1) NOT NULL DEFAULT 1,
                    mailbox_password_env VARCHAR(255) NOT NULL DEFAULT 'RELANCE_MAILBOX_PASSWORD',
                    mailbox_access_token_env VARCHAR(255) NOT NULL DEFAULT 'RELANCE_MAILBOX_ACCESS_TOKEN',
                    llm_provider VARCHAR(50) NOT NULL DEFAULT 'mistral',
                    llm_model VARCHAR(100) NOT NULL DEFAULT 'mistral-small-latest',
                    llm_api_base VARCHAR(255) NOT NULL DEFAULT 'https://api.mistral.ai/v1',
                    llm_api_key_env VARCHAR(255) NOT NULL DEFAULT 'MISTRAL_API_KEY',
                    llm_temperature DECIMAL(3, 2) NOT NULL DEFAULT 0.40,
                    tone_instruction TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            cur.execute("""
                INSERT IGNORE INTO relance_config (
                    id, enabled, frequency_days, sender_name, sender_email,
                    mailbox_imap_host, mailbox_imap_port, mailbox_imap_user,
                    mailbox_drafts_folder, mailbox_use_ssl, mailbox_password_env,
                    mailbox_access_token_env, llm_provider, llm_model, llm_api_base,
                    llm_api_key_env, llm_temperature, tone_instruction, updated_at
                )
                VALUES (1, 1, 14, 'Syndic de copropriete', '', '', 993, '', 'Drafts', 1,
                        'RELANCE_MAILBOX_PASSWORD', 'RELANCE_MAILBOX_ACCESS_TOKEN', 'mistral',
                        'mistral-small-latest', 'https://api.mistral.ai/v1', 'MISTRAL_API_KEY',
                        0.40, 'courtois, professionnel et ferme', CURRENT_TIMESTAMP)
            """)
            _logger.success("Table 'relance_config' verifiee/creee.")

            # 10. Table relance_destinataire
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_destinataire (
                    code_proprietaire VARCHAR(50) PRIMARY KEY,
                    email_to VARCHAR(255) NOT NULL DEFAULT '',
                    contact_name VARCHAR(255),
                    notes TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (code_proprietaire) REFERENCES coproprietaires(code_proprietaire)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            _logger.success("Table 'relance_destinataire' verifiee/creee.")

            # 11. Table relance_draft
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_draft (
                    draft_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    code_proprietaire VARCHAR(50) NOT NULL,
                    nom_proprietaire VARCHAR(255),
                    debit DECIMAL(12, 2),
                    email_to VARCHAR(255) NOT NULL,
                    subject VARCHAR(500) NOT NULL,
                    body MEDIUMTEXT NOT NULL,
                    llm_provider VARCHAR(50),
                    llm_model VARCHAR(100),
                    status VARCHAR(50) NOT NULL DEFAULT 'draft_local',
                    remote_draft_id VARCHAR(255),
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    validated_at DATETIME,
                    sent_at DATETIME,
                    FOREIGN KEY (code_proprietaire) REFERENCES coproprietaires(code_proprietaire)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_relance_draft_code_created ON relance_draft(code_proprietaire, created_at DESC);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_relance_draft_status ON relance_draft(status, created_at DESC);"
            )
            _logger.success("Table 'relance_draft' verifiee/creee.")

            # 12. Table relance_template
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_template (
                    template_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    subject_template VARCHAR(500) NOT NULL,
                    body_template TEXT NOT NULL,
                    generation_mode VARCHAR(50) NOT NULL DEFAULT 'static',
                    tone_instruction TEXT,
                    is_default TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            _logger.success("Table 'relance_template' verifiee/creee.")

            # 13. Table relance_variable (variables de relance personnalisees)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_variable (
                    var_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    description VARCHAR(255) DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            _logger.success("Table 'relance_variable' verifiee/creee.")

            # 14. Table relance_snippet (paragraphes types de relance)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS relance_snippet (
                    snippet_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(150) NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    description VARCHAR(255) DEFAULT '',
                    sort_order INT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            _logger.success("Table 'relance_snippet' verifiee/creee.")

    _logger.success("Base de donnees MariaDB initialisee avec succes.")


def integrite_db(db_path: str | None = None) -> dict[str, Any]:
    """Verifie l'existence des composants de la base et cree ceux qui manquent (via INFORMATION_SCHEMA)."""
    created: list[str] = []

    def _has_table(cur: Cursor, table_name: str) -> bool:
        cur.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (table_name,),
        )
        return cur.fetchone() is not None

    def _has_column(cur: Cursor, table_name: str, col_name: str) -> bool:
        cur.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            (table_name, col_name),
        )
        return cur.fetchone() is not None

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Table charge
            _logger.info("Verification presence table 'charge'.")
            has_charge = _has_table(cur, "charge")
            if not has_charge:
                _logger.warning("Table 'charge' manquante, creation...")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS charge (
                        id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        nom_proprietaire VARCHAR(255),
                        code_proprietaire VARCHAR(50),
                        debit DECIMAL(12, 2),
                        credit DECIMAL(12, 2),
                        date DATE,
                        last_check DATE DEFAULT CURRENT_DATE,
                        UNIQUE KEY uq_code_date (code_proprietaire, date)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci WITH SYSTEM VERSIONING;
                """)
                created.append("charge")

            # Table config_alerte
            _logger.info("Verification presence table 'config_alerte'.")
            has_config_alerte = _has_table(cur, "config_alerte")
            if not has_config_alerte:
                _logger.warning("Table 'config_alerte' manquante, creation...")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS config_alerte (
                        type_apt VARCHAR(50) PRIMARY KEY,
                        charge_moyenne DECIMAL(12, 2) NOT NULL,
                        taux DECIMAL(12, 2) NOT NULL DEFAULT 1.33,
                        threshold DECIMAL(12, 2) NOT NULL,
                        last_update DATE DEFAULT CURRENT_DATE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
                    cur.execute(
                        """
                        INSERT IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                        VALUES (%s, %s, %s, %s, CURRENT_DATE)
                    """,
                        (type_apt, config["charge_moyenne"], config["taux"], config["threshold"]),
                    )
                cur.execute(
                    """
                    INSERT IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                    VALUES ('default', %s, 1.0, %s, CURRENT_DATE)
                """,
                    (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK),
                )
                created.append("config_alerte")

            # Table coproprietaires
            _logger.info("Verification presence table 'coproprietaires'.")
            has_coproprietaires = _has_table(cur, "coproprietaires")
            if not has_coproprietaires:
                _logger.warning("Table 'coproprietaires' manquante, creation...")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS coproprietaires (
                        nom_proprietaire VARCHAR(255),
                        code_proprietaire VARCHAR(50) PRIMARY KEY,
                        num_apt VARCHAR(50) DEFAULT 'NA',
                        type_apt VARCHAR(50) DEFAULT 'NA',
                        last_check DATE DEFAULT CURRENT_DATE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                created.append("coproprietaires")

            # Table alertes_debit_eleve
            _logger.info("Verification presence table 'alertes_debit_eleve'.")
            has_alertes = _has_table(cur, "alertes_debit_eleve")
            if not has_alertes:
                _logger.warning("Table 'alertes_debit_eleve' manquante, creation...")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS alertes_debit_eleve (
                        alerte_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_origin INT UNSIGNED NOT NULL,
                        nom_proprietaire VARCHAR(255),
                        code_proprietaire VARCHAR(50),
                        debit DECIMAL(12, 2) NOT NULL,
                        type_alerte VARCHAR(50) NOT NULL,
                        date_origin DATE,
                        last_detection DATE DEFAULT CURRENT_DATE,
                        first_detection DATE DEFAULT CURRENT_DATE,
                        occurence INT NOT NULL,
                        UNIQUE KEY idx_alertes_code_proprietaire (code_proprietaire),
                        FOREIGN KEY (id_origin) REFERENCES charge(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                created.append("alertes_debit_eleve")
            else:
                if not _has_column(cur, "alertes_debit_eleve", "date_origin"):
                    cur.execute("ALTER TABLE alertes_debit_eleve ADD COLUMN date_origin DATE")
                    created.append("alertes_debit_eleve.date_origin")

                # Safety net type_alerte corrompus
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

            # Triggers
            cur.execute("""
                SELECT 1 FROM INFORMATION_SCHEMA.TRIGGERS
                WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = 'alerte_debit_eleve_insert'
            """)
            has_trigger = cur.fetchone() is not None
            cur.execute(TRIGGER_INSERT_SQL)
            cur.execute(TRIGGER_INSERT_CLEAR_SQL)
            cur.execute(TRIGGER_DELETE_SQL)
            if not has_trigger:
                created.append("alerte_debit_eleve_triggers")

            # Vue vw_charge_coproprietaires
            cur.execute("""
                CREATE OR REPLACE VIEW vw_charge_coproprietaires AS
                SELECT
                    ROW_NUMBER() OVER (ORDER BY c.id) AS id,
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

            # Table suivi_alertes
            has_nombre_alertes = _has_table(cur, "suivi_alertes")
            if not has_nombre_alertes:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS suivi_alertes (
                        date_releve DATE PRIMARY KEY,
                        nombre_alertes INT NOT NULL,
                        total_debit DECIMAL(12, 2) NOT NULL,
                        nb_2p INT DEFAULT 0,
                        nb_3p INT DEFAULT 0,
                        nb_4p INT DEFAULT 0,
                        nb_5p INT DEFAULT 0,
                        nb_na INT DEFAULT 0,
                        debit_2p DECIMAL(12, 2) DEFAULT 0,
                        debit_3p DECIMAL(12, 2) DEFAULT 0,
                        debit_4p DECIMAL(12, 2) DEFAULT 0,
                        debit_5p DECIMAL(12, 2) DEFAULT 0,
                        debit_na DECIMAL(12, 2) DEFAULT 0
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                created.append("suivi_alertes")

            # Table relance_config
            has_relance_config = _has_table(cur, "relance_config")
            if not has_relance_config:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS relance_config (
                        id INT PRIMARY KEY CHECK (id = 1),
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        frequency_days INT NOT NULL DEFAULT 14,
                        sender_name VARCHAR(255) NOT NULL DEFAULT 'Syndic de copropriete',
                        sender_email VARCHAR(255) DEFAULT '',
                        mailbox_imap_host VARCHAR(255) DEFAULT '',
                        mailbox_imap_port INT NOT NULL DEFAULT 993,
                        mailbox_imap_user VARCHAR(255) DEFAULT '',
                        mailbox_drafts_folder VARCHAR(255) NOT NULL DEFAULT 'Drafts',
                        mailbox_use_ssl TINYINT(1) NOT NULL DEFAULT 1,
                        mailbox_password_env VARCHAR(255) NOT NULL DEFAULT 'RELANCE_MAILBOX_PASSWORD',
                        mailbox_access_token_env VARCHAR(255) NOT NULL DEFAULT 'RELANCE_MAILBOX_ACCESS_TOKEN',
                        llm_provider VARCHAR(50) NOT NULL DEFAULT 'mistral',
                        llm_model VARCHAR(100) NOT NULL DEFAULT 'mistral-small-latest',
                        llm_api_base VARCHAR(255) NOT NULL DEFAULT 'https://api.mistral.ai/v1',
                        llm_api_key_env VARCHAR(255) NOT NULL DEFAULT 'MISTRAL_API_KEY',
                        llm_temperature DECIMAL(3, 2) NOT NULL DEFAULT 0.40,
                        tone_instruction TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                cur.execute("""
                    INSERT IGNORE INTO relance_config (
                        id, enabled, frequency_days, sender_name, sender_email,
                        mailbox_imap_host, mailbox_imap_port, mailbox_imap_user,
                        mailbox_drafts_folder, mailbox_use_ssl, mailbox_password_env,
                        mailbox_access_token_env, llm_provider, llm_model, llm_api_base,
                        llm_api_key_env, llm_temperature, tone_instruction, updated_at
                    )
                    VALUES (1, 1, 14, 'Syndic de copropriete', '', '', 993, '', 'Drafts', 1,
                            'RELANCE_MAILBOX_PASSWORD', 'RELANCE_MAILBOX_ACCESS_TOKEN', 'mistral',
                            'mistral-small-latest', 'https://api.mistral.ai/v1', 'MISTRAL_API_KEY',
                            0.40, 'courtois, professionnel et ferme', CURRENT_TIMESTAMP)
                """)
                created.append("relance_config")

            # Table relance_destinataire
            has_relance_destinataire = _has_table(cur, "relance_destinataire")
            if not has_relance_destinataire:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS relance_destinataire (
                        code_proprietaire VARCHAR(50) PRIMARY KEY,
                        email_to VARCHAR(255) NOT NULL DEFAULT '',
                        contact_name VARCHAR(255),
                        notes TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (code_proprietaire) REFERENCES coproprietaires(code_proprietaire)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                created.append("relance_destinataire")
            else:
                cur.execute("SHOW COLUMNS FROM relance_destinataire LIKE 'notes'")
                if not cur.fetchone():
                    cur.execute("ALTER TABLE relance_destinataire ADD COLUMN notes TEXT")

            # Table relance_draft
            has_relance_draft = _has_table(cur, "relance_draft")
            if not has_relance_draft:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS relance_draft (
                        draft_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        code_proprietaire VARCHAR(50) NOT NULL,
                        nom_proprietaire VARCHAR(255),
                        debit DECIMAL(12, 2),
                        email_to VARCHAR(255) NOT NULL,
                        subject VARCHAR(500) NOT NULL,
                        body MEDIUMTEXT NOT NULL,
                        llm_provider VARCHAR(50),
                        llm_model VARCHAR(100),
                        status VARCHAR(50) NOT NULL DEFAULT 'draft_local',
                        remote_draft_id VARCHAR(255),
                        error_message TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        validated_at DATETIME,
                        sent_at DATETIME,
                        FOREIGN KEY (code_proprietaire) REFERENCES coproprietaires(code_proprietaire)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_relance_draft_code_created ON relance_draft(code_proprietaire, created_at DESC);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_relance_draft_status ON relance_draft(status, created_at DESC);"
                )
                created.append("relance_draft")

            # Table relance_template
            has_relance_template = _has_table(cur, "relance_template")
            if not has_relance_template:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS relance_template (
                        template_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL UNIQUE,
                        subject_template VARCHAR(500) NOT NULL,
                        body_template TEXT NOT NULL,
                        generation_mode VARCHAR(50) NOT NULL DEFAULT 'static',
                        tone_instruction TEXT,
                        is_default TINYINT(1) NOT NULL DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                created.append("relance_template")

            # Table relance_variable
            has_relance_variable = _has_table(cur, "relance_variable")
            if not has_relance_variable:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS relance_variable (
                        var_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL UNIQUE,
                        value TEXT NOT NULL,
                        description VARCHAR(255) DEFAULT '',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                created.append("relance_variable")

            # Table relance_snippet
            has_relance_snippet = _has_table(cur, "relance_snippet")
            if not has_relance_snippet:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS relance_snippet (
                        snippet_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        title VARCHAR(150) NOT NULL UNIQUE,
                        content TEXT NOT NULL,
                        description VARCHAR(255) DEFAULT '',
                        sort_order INT DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                created.append("relance_snippet")

    # Initialisation des snippets par défaut si la table est vide
    try:
        from .Relance_Snippets import init_relance_snippets_if_missing
        init_relance_snippets_if_missing(db_path=db_path)
    except Exception as exc:
        _logger.warning(f"Impossible d'initialiser les snippets par défaut : {exc}")

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
        "relance_variable": has_relance_variable,
        "relance_snippet": has_relance_snippet,
        "created": created,
    }


def purger_alertes_pour_rebuild(db_path: str | None = None) -> None:
    """Vide alertes_debit_eleve et nettoie suivi_alertes de facon atomique."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM alertes_debit_eleve")
            cur.execute("""
                DELETE FROM suivi_alertes
                WHERE NOT EXISTS (
                    SELECT 1 FROM charge WHERE date = suivi_alertes.date_releve
                )
            """)
    _logger.info("Tables 'alertes_debit_eleve' et 'suivi_alertes' purgees.")
