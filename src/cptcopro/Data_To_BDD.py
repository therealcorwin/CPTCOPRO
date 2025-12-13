"""Module de gestion de la base de données SQLite.

Ce module gère :
- La création et vérification des tables (charge, alertes_debit_eleve, coproprietaires, suivi_alertes, config_alerte)
- Les triggers pour la détection automatique des alertes de débit élevé (seuils configurables par type d'appartement)
- L'insertion des données de charges et copropriétaires
- La mise à jour des statistiques d'alertes

Tables:
    charge: Historique des charges par copropriétaire
    alertes_debit_eleve: Alertes pour les débits dépassant le seuil configuré
    coproprietaires: Liste des copropriétaires et leurs lots
    suivi_alertes: Statistiques journalières des alertes
    config_alerte: Configuration des seuils d'alerte par type d'appartement
"""
import os
import sqlite3
from loguru import logger
from typing import Any, Dict

logger.remove()
logger = logger.bind(type_log="BDD")

# Seuils d'alerte par défaut par type d'appartement
# Ces valeurs sont utilisées pour initialiser la table config_alerte
DEFAULT_ALERT_THRESHOLDS = {
    "2p": {"charge_moyenne": 1500.0, "taux": 1.33, "threshold": 2000.0},
    "3p": {"charge_moyenne": 1800.0, "taux": 1.33, "threshold": 2400.0},
    "4p": {"charge_moyenne": 2100.0, "taux": 1.33, "threshold": 2800.0},
    "5p": {"charge_moyenne": 2400.0, "taux": 1.33, "threshold": 3200.0},
}
# Seuil par défaut pour les types non configurés (NA, inconnu, etc.)
DEFAULT_THRESHOLD_FALLBACK = 2000.0

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
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT,
                    debit REAL,
                    credit REAL,
                    date DATE,
                    last_check DATE DEFAULT CURRENT_DATE
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
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT,
                    debit REAL NOT NULL,
                    type_alerte text NOT NULL,
                    -- renamed: last_detection stores the last detection timestamp
                    last_detection DATE DEFAULT CURRENT_DATE,
                    -- first_detection: timestamp of first detection for this alert
                    first_detection DATE DEFAULT CURRENT_DATE,
                    -- occurence: number of times this alert was triggered
                    occurence INTEGER NOT NULL,
                    FOREIGN KEY(id_origin) REFERENCES charge(id) ON DELETE CASCADE
                );
                """
            )
            logger.success("Table 'alertes_debit_eleve' vérifiée/créée.")

            # Création de la table 'config_alerte' pour les seuils par type d'appartement
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS config_alerte (
                    type_apt TEXT PRIMARY KEY,
                    charge_moyenne REAL NOT NULL,
                    taux REAL NOT NULL DEFAULT 1.33,
                    threshold REAL NOT NULL,
                    last_update DATE DEFAULT CURRENT_DATE
                );
                """
            )
            logger.success("Table 'config_alerte' vérifiée/créée.")
            
            # Initialiser les seuils par défaut
            for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
                cur.execute(
                    """
                    INSERT OR IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                    VALUES (?, ?, ?, ?, CURRENT_DATE)
                    """,
                    (type_apt, config["charge_moyenne"], config["taux"], config["threshold"])
                )
            # Ajouter un seuil par défaut pour les types non configurés
            cur.execute(
                """
                INSERT OR IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                VALUES ('default', ?, 1.0, ?, CURRENT_DATE)
                """,
                (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK)
            )
            logger.info("Seuils d'alerte par défaut initialisés.")

            # Créer un index unique sur code_proprietaire pour permettre l'UPSERT
            cur.executescript("""
                -- Index unique requis pour l'UPSERT (une alerte par proprietaire)
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alertes_code_proprietaire ON alertes_debit_eleve(code_proprietaire);

                -- INSERT (UPSERT) : si la nouvelle ligne (latest) dépasse le seuil configuré pour son type d'appartement
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                  AND NEW.debit > COALESCE(
                      (SELECT ca.threshold 
                       FROM config_alerte ca 
                       JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                       WHERE cp.code_proprietaire = NEW.code_proprietaire),
                      (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                      2000.0
                  )
                BEGIN
                    INSERT INTO alertes_debit_eleve (
                        id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte,
                        first_detection, last_detection, occurence
                    )
                    VALUES (
                        NEW.id, NEW.nom_proprietaire, NEW.code_proprietaire, NEW.debit,
                        COALESCE(
                            (SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = NEW.code_proprietaire),
                            'na'
                        ),
                        CURRENT_DATE, CURRENT_DATE, 1
                    )
                    ON CONFLICT(code_proprietaire) DO UPDATE SET
                        id_origin = excluded.id_origin,
                        nom_proprietaire = excluded.nom_proprietaire,
                        debit = excluded.debit,
                        type_alerte = excluded.type_alerte,
                        last_detection = CURRENT_DATE,
                        occurence = COALESCE(occurence, 0) + 1;
                END;

                -- INSERT_CLEAR : si la nouvelle ligne (latest) est sous le seuil, supprimer toute alerte existante
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert_clear
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                  AND NEW.debit <= COALESCE(
                      (SELECT ca.threshold 
                       FROM config_alerte ca 
                       JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                       WHERE cp.code_proprietaire = NEW.code_proprietaire),
                      (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                      2000.0
                  )
                BEGIN
                    DELETE FROM alertes_debit_eleve WHERE code_proprietaire = NEW.code_proprietaire;
                END;

                -- DELETE : si la ligne supprimée était la plus récente pour ce propriétaire,
                --          supprimer l'alerte existante et (si il y a une nouvelle latest > seuil) recréer une alerte unique
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_delete
                AFTER DELETE ON charge
                FOR EACH ROW
                WHEN OLD.id >= COALESCE((SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire), 0)
                BEGIN
                    DELETE FROM alertes_debit_eleve WHERE code_proprietaire = OLD.code_proprietaire;

                    INSERT INTO alertes_debit_eleve (
                        id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte,
                        first_detection, last_detection, occurence
                    )
                    SELECT c.id, c.nom_proprietaire, c.code_proprietaire, c.debit,
                           COALESCE(
                               (SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = c.code_proprietaire),
                               'na'
                           ),
                           CURRENT_DATE, CURRENT_DATE, 1
                    FROM charge c
                    WHERE c.code_proprietaire = OLD.code_proprietaire
                      AND c.id = (SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire)
                      AND c.debit > COALESCE(
                          (SELECT ca.threshold 
                           FROM config_alerte ca 
                           JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                           WHERE cp.code_proprietaire = OLD.code_proprietaire),
                          (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                          2000.0
                      );
                END;
            """)
            logger.info("Triggers 'alerte_debit_eleve' vérifiés/créés (insert/insert_clear/delete) avec seuils dynamiques.")
            # Creation Table coproprietaires
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS coproprietaires (
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT PRIMARY KEY,
                    num_apt TEXT DEFAULT 'NA',
                    type_apt TEXT DEFAULT 'NA',
                    last_check DATE DEFAULT CURRENT_DATE
                )
                """
            )
            logger.success("Table 'coproprietaires' vérifiée/créée.")

            logger.info("Création de la vue 'vw_charge_coproprietaires'...")
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
            
            logger.info("Creation de la table suivi_alertes")
            cur.execute(
                """
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
                """
            )
            logger.success("Table 'suivi_alertes' vérifiée/créée.")

            conn.commit()
            conn.close()
            logger.success("Tables Alerte_debit_eleve, charge et coproprietaires et trigger 'alerte_debit_eleve' créés.")
            logger.success(f"Base de données '{db_path}' et trigger créés avec succès.")
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
    - table `coproprietaires`
    - vue `vw_charge_coproprietaires`
    - table `nombre_alertes`
    - table `config_alerte`

    Retourne un dict récapitulatif contenant l'état après vérification et la liste
    des éléments créés.
    """
    verif_repertoire_db(db_path)
    created = []
    # Ensure the DB file exists by opening a connection
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    has_config_alerte = False
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
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT,
                    debit REAL,
                    credit REAL,
                    date DATE,
                    last_check DATE DEFAULT CURRENT_DATE
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
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT,
                    debit REAL NOT NULL,
                    type_alerte text NOT NULL,
                    last_detection DATE DEFAULT CURRENT_DATE,
                    first_detection DATE DEFAULT CURRENT_DATE,
                    occurence INTEGER NOT NULL,
                    FOREIGN KEY(id_origin) REFERENCES charge(id) ON DELETE CASCADE
                );
                """
            )
            created.append('alertes_debit_eleve')
            logger.info("Table 'alertes_debit_eleve' créée.")

        # config_alerte - table de configuration des seuils
        logger.info("Vérification de la présence de la table 'config_alerte'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config_alerte';")
        if cur.fetchone():
            has_config_alerte = True
            logger.info("Table 'config_alerte' existe.")
        else:
            logger.warning("Table 'config_alerte' manquante, création en cours.")
            has_config_alerte = False
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS config_alerte (
                    type_apt TEXT PRIMARY KEY,
                    charge_moyenne REAL NOT NULL,
                    taux REAL NOT NULL DEFAULT 1.33,
                    threshold REAL NOT NULL,
                    last_update DATE DEFAULT CURRENT_DATE
                );
                """
            )
            # Initialiser les seuils par défaut
            for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
                cur.execute(
                    """
                    INSERT OR IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                    VALUES (?, ?, ?, ?, CURRENT_DATE)
                    """,
                    (type_apt, config["charge_moyenne"], config["taux"], config["threshold"])
                )
            # Ajouter un seuil par défaut pour les types non configurés
            cur.execute(
                """
                INSERT OR IGNORE INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                VALUES ('default', ?, 1.0, ?, CURRENT_DATE)
                """,
                (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK)
            )
            created.append('config_alerte')
            logger.info("Table 'config_alerte' créée avec seuils par défaut.")

        # trigger alerte_debit_eleve
        logger.info("Vérification de la présence du trigger 'alerte_debit_eleve'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='alerte_debit_eleve_insert';")
        if cur.fetchone():
            has_trigger = True
            logger.info("Trigger 'alerte_debit_eleve' existe.")
        else:
            logger.warning("Trigger 'alerte_debit_eleve' manquant, création en cours.")
            has_trigger = False
            cur.executescript("""
                -- Index unique requis pour l'UPSERT (une alerte par proprietaire)
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alertes_code_proprietaire ON alertes_debit_eleve(code_proprietaire);
                
                -- INSERT (UPSERT) : si la nouvelle ligne (latest) dépasse le seuil configuré pour son type d'appartement
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                  AND NEW.debit > COALESCE(
                      (SELECT ca.threshold 
                       FROM config_alerte ca 
                       JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                       WHERE cp.code_proprietaire = NEW.code_proprietaire),
                      (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                      2000.0
                  )
                BEGIN
                    INSERT INTO alertes_debit_eleve (
                        id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte,
                        first_detection, last_detection, occurence
                    )
                    VALUES (
                        NEW.id, NEW.nom_proprietaire, NEW.code_proprietaire, NEW.debit,
                        COALESCE(
                            (SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = NEW.code_proprietaire),
                            'na'
                        ),
                        CURRENT_DATE, CURRENT_DATE, 1
                    )
                    ON CONFLICT(code_proprietaire) DO UPDATE SET
                        id_origin = excluded.id_origin,
                        nom_proprietaire = excluded.nom_proprietaire,
                        debit = excluded.debit,
                        type_alerte = excluded.type_alerte,
                        last_detection = CURRENT_DATE,
                        occurence = COALESCE(occurence, 0) + 1;
                END;
                
                -- INSERT_CLEAR : si la nouvelle ligne (latest) est sous le seuil, supprimer toute alerte existante
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert_clear
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                  AND NEW.debit <= COALESCE(
                      (SELECT ca.threshold 
                       FROM config_alerte ca 
                       JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                       WHERE cp.code_proprietaire = NEW.code_proprietaire),
                      (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                      2000.0
                  )
                BEGIN
                    DELETE FROM alertes_debit_eleve WHERE code_proprietaire = NEW.code_proprietaire;
                END;
                
                -- DELETE : si la ligne supprimée était la plus récente pour ce propriétaire,
                --          supprimer l'alerte existante et (si il y a une nouvelle latest > seuil) recréer une alerte unique
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_delete
                AFTER DELETE ON charge
                FOR EACH ROW
                WHEN OLD.id >= COALESCE((SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire), 0)
                BEGIN
                    DELETE FROM alertes_debit_eleve WHERE code_proprietaire = OLD.code_proprietaire;
                
                    INSERT INTO alertes_debit_eleve (
                        id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte,
                        first_detection, last_detection, occurence
                    )
                    SELECT c.id, c.nom_proprietaire, c.code_proprietaire, c.debit,
                           COALESCE(
                               (SELECT LOWER(cp.type_apt) FROM coproprietaires cp WHERE cp.code_proprietaire = c.code_proprietaire),
                               'na'
                           ),
                           CURRENT_DATE, CURRENT_DATE, 1
                    FROM charge c
                    WHERE c.code_proprietaire = OLD.code_proprietaire
                      AND c.id = (SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire)
                      AND c.debit > COALESCE(
                          (SELECT ca.threshold 
                           FROM config_alerte ca 
                           JOIN coproprietaires cp ON LOWER(cp.type_apt) = LOWER(ca.type_apt)
                           WHERE cp.code_proprietaire = OLD.code_proprietaire),
                          (SELECT threshold FROM config_alerte WHERE type_apt = 'default'),
                          2000.0
                      );
                END;
            """)
            created.append('alerte_debit_eleve')

        # coproprietaires
        logger.info("Vérification de la présence de la table 'coproprietaires'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coproprietaires';")
        if cur.fetchone():
            has_coproprietaires = True
            logger.info("Table 'coproprietaires' existe.")
        else:
            logger.warning("Table 'coproprietaires' manquante, création en cours.")
            has_coproprietaires = False
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS coproprietaires (
                    nom_proprietaire TEXT,
                    code_proprietaire TEXT PRIMARY KEY,
                    num_apt TEXT DEFAULT 'NA',
                    type_apt TEXT DEFAULT 'NA',
                    last_check DATE DEFAULT CURRENT_DATE
                )
                """
            )
            created.append('coproprietaires')
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
        # table suivi_alertes
        logger.info("Vérification de la présence de la table 'suivi_alertes'.")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='suivi_alertes';")
        if cur.fetchone():
            has_nombre_alertes = True
            logger.info("Table 'suivi_alertes' existe.")
        else:
            logger.warning("Table 'suivi_alertes' manquante, création en cours.")
            has_nombre_alertes = False
            cur.execute(
                """
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
                """
            )
            logger.success("Table 'suivi_alertes' vérifiée/créée.")
            created.append('suivi_alertes')
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
        'coproprietaires': has_coproprietaires,
        'nombre_alertes': has_nombre_alertes,
        'config_alerte': has_config_alerte,
        'created': created,
    }

def enregistrer_donnees_sqlite(data: list[Any], db_path: str) -> None:
    """
    Enregistre les données extraites dans une base de données SQLite.

    La fonction se connecte à la base de données SQLite spécifiée par `db_path`
    et insère les données fournies dans la table `charge`.

    Parameters:
    - data (list[Any]): Une liste de tuples contenant les données à enregistrer.
      Chaque tuple doit avoir le format suivant : (code_proprietaire, nom_proprietaire, debit, credit, date).
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


def enregistrer_coproprietaires(data_coproprietaires: list[Any], db_path: str) -> None:
    """
    Insère des informations de copropriétaires dans la table `coproprietaires`.
    
    Args:
        data_coproprietaires: Liste de dictionnaires contenant les clés:
            - nom_proprietaire: nom du propriétaire
            - code_proprietaire: code du propriétaire
            - num_apt: numéro d'appartement
            - type_apt: type d'appartement
        db_path: Chemin vers la base de données SQLite

    Returns:
        None
    """    
    logger.info("Insertion des copropriétaires dans la base de données...")
    data = []
    for copro in data_coproprietaires:
        # Accept both old keys ('proprietaire','code') and new keys ('nom_proprietaire','code_proprietaire')
        nom = copro.get("nom_proprietaire") if copro.get("nom_proprietaire") is not None else copro.get("proprietaire")
        code = copro.get("code_proprietaire") if copro.get("code_proprietaire") is not None else copro.get("code")
        data.append((nom or "", code or "", copro.get("num_apt") or "", copro.get("type_apt") or ""))

    if not data:
        logger.info("Aucune donnée coproprietaires à insérer.")
        return 
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Pour éviter les doublons, on remplace la table existante
        cur.execute("DELETE FROM coproprietaires")

        if data:
            # La colonne last_check a une valeur par défaut ; on n'insère que les 4 colonnes attendues
            cur.executemany(
                "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt) VALUES (?, ?, ?, ?)",
                data,
            )
        conn.commit()
        nb_copro = len(data)
    except Exception as e:
        conn.rollback()
        logger.error(f"Erreur lors de l'insertion des coproprietaires : {e}")
        raise
    finally:
        conn.close()

    logger.info(f"{nb_copro} copropriétaires insérés (table remplacée).")
    return

def sauvegarder_nombre_alertes(db_path: str) -> None:
    """
    Sauvegarde le nombre d'alertes pour une date de relevé donnée dans la table `suivi_alertes`.
    
    Calcule les statistiques globales et par type d'appartement (2p, 3p, 4p, 5p, na).

    Args:
        db_path (str): Chemin vers la base de données SQLite.
    Returns:
        None
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Récupérer les valeurs globales
        cur.execute(
            """
            SELECT 
                MAX(last_detection) AS date_releve,
                COUNT(*) AS nombre_alertes,
                COALESCE(SUM(debit), 0) AS total_debit
            FROM alertes_debit_eleve
            """
        )
        row = cur.fetchone()
        date_releve, nombre_alertes, total_debit = row[0], row[1], row[2]
        
        if date_releve is None:
            logger.warning("Aucune alerte trouvée, rien à sauvegarder.")
            return
        
        # Récupérer les statistiques par type d'appartement
        cur.execute(
            """
            SELECT 
                LOWER(COALESCE(type_alerte, 'na')) AS type_apt,
                COUNT(*) AS nb,
                COALESCE(SUM(debit), 0) AS total
            FROM alertes_debit_eleve
            GROUP BY LOWER(COALESCE(type_alerte, 'na'))
            """
        )
        stats_par_type = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        
        # Extraire les valeurs par type (avec valeurs par défaut à 0)
        nb_2p = stats_par_type.get('2p', (0, 0))[0]
        nb_3p = stats_par_type.get('3p', (0, 0))[0]
        nb_4p = stats_par_type.get('4p', (0, 0))[0]
        nb_5p = stats_par_type.get('5p', (0, 0))[0]
        nb_na = stats_par_type.get('na', (0, 0))[0]
        
        debit_2p = stats_par_type.get('2p', (0, 0))[1]
        debit_3p = stats_par_type.get('3p', (0, 0))[1]
        debit_4p = stats_par_type.get('4p', (0, 0))[1]
        debit_5p = stats_par_type.get('5p', (0, 0))[1]
        debit_na = stats_par_type.get('na', (0, 0))[1]
        
        # UPSERT : INSERT OR REPLACE fonctionne grâce à PRIMARY KEY(date_releve)
        cur.execute(
            """
            INSERT OR REPLACE INTO suivi_alertes (
                date_releve, nombre_alertes, total_debit,
                nb_2p, nb_3p, nb_4p, nb_5p, nb_na,
                debit_2p, debit_3p, debit_4p, debit_5p, debit_na
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (date_releve, nombre_alertes, total_debit,
             nb_2p, nb_3p, nb_4p, nb_5p, nb_na,
             debit_2p, debit_3p, debit_4p, debit_5p, debit_na)
        )
        conn.commit()
        logger.info(
            f"Alertes sauvegardées pour {date_releve}: "
            f"total={nombre_alertes} ({total_debit}€), "
            f"2p={nb_2p}, 3p={nb_3p}, 4p={nb_4p}, 5p={nb_5p}, na={nb_na}"
        )
    except Exception as e:
        conn.rollback()
        logger.error(f"Erreur lors de la sauvegarde du nombre d'alertes : {e}")
        raise
    finally:
        conn.close()
    return


# ============================================================================
# Fonctions de gestion de la configuration des alertes
# ============================================================================

def get_config_alertes(db_path: str) -> list[Dict[str, Any]]:
    """
    Récupère la configuration des seuils d'alerte par type d'appartement.
    
    Args:
        db_path: Chemin vers la base de données SQLite.
    
    Returns:
        Liste de dictionnaires contenant pour chaque type d'appartement:
            - type_apt: Type d'appartement (2p, 3p, 4p, 5p, default)
            - charge_moyenne: Charge moyenne pour ce type
            - taux: Taux multiplicateur pour calculer le seuil
            - threshold: Seuil d'alerte en euros
            - last_update: Date de dernière mise à jour
    
    Example:
        >>> config = get_config_alertes("/path/to/db.sqlite")
        >>> print(config[0])
        {'type_apt': '2p', 'charge_moyenne': 1500.0, 'taux': 1.33, 'threshold': 2000.0, 'last_update': '2024-12-11'}
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT type_apt, charge_moyenne, taux, threshold, last_update
            FROM config_alerte
            ORDER BY type_apt
            """
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError as e:
        logger.warning(f"Table config_alerte non trouvée, retour des valeurs par défaut: {e}")
        # Retourner les valeurs par défaut si la table n'existe pas
        result = []
        for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
            result.append({
                "type_apt": type_apt,
                "charge_moyenne": config["charge_moyenne"],
                "taux": config["taux"],
                "threshold": config["threshold"],
                "last_update": None
            })
        result.append({
            "type_apt": "default",
            "charge_moyenne": DEFAULT_THRESHOLD_FALLBACK,
            "taux": 1.0,
            "threshold": DEFAULT_THRESHOLD_FALLBACK,
            "last_update": None
        })
        return result
    finally:
        conn.close()


def update_config_alerte(
    db_path: str, 
    type_apt: str, 
    charge_moyenne: float | None = None,
    taux: float | None = None,
    threshold: float | None = None
) -> bool:
    """
    Met à jour la configuration d'alerte pour un type d'appartement.
    
    Permet de mettre à jour un ou plusieurs paramètres pour un type donné.
    Si threshold n'est pas fourni mais charge_moyenne et/ou taux le sont,
    le threshold est recalculé automatiquement (charge_moyenne * taux).
    
    Args:
        db_path: Chemin vers la base de données SQLite.
        type_apt: Type d'appartement à mettre à jour (2p, 3p, 4p, 5p, default).
        charge_moyenne: Nouvelle charge moyenne (optionnel).
        taux: Nouveau taux multiplicateur (optionnel).
        threshold: Nouveau seuil d'alerte (optionnel, recalculé si non fourni).
    
    Returns:
        True si la mise à jour a réussi, False sinon.
    
    Example:
        >>> update_config_alerte("/path/to/db.sqlite", "3p", charge_moyenne=2000.0)
        True
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Récupérer les valeurs actuelles
        cur.execute(
            "SELECT charge_moyenne, taux, threshold FROM config_alerte WHERE type_apt = ?",
            (type_apt.lower(),)
        )
        row = cur.fetchone()
        if not row:
            logger.error(f"Type d'appartement '{type_apt}' non trouvé dans config_alerte")
            return False
        
        current_charge = row[0]
        current_taux = row[1]
        current_threshold = row[2]
        
        # Appliquer les nouvelles valeurs (ou garder les anciennes)
        new_charge = charge_moyenne if charge_moyenne is not None else current_charge
        new_taux = taux if taux is not None else current_taux
        
        # Recalculer threshold si non fourni explicitement
        if threshold is not None:
            new_threshold = threshold
        elif charge_moyenne is not None or taux is not None:
            # Recalculer automatiquement
            new_threshold = new_charge * new_taux
        else:
            new_threshold = current_threshold
        
        # Mettre à jour
        cur.execute(
            """
            UPDATE config_alerte 
            SET charge_moyenne = ?, taux = ?, threshold = ?, last_update = CURRENT_DATE
            WHERE type_apt = ?
            """,
            (new_charge, new_taux, new_threshold, type_apt.lower())
        )
        conn.commit()
        logger.info(
            f"Config alerte '{type_apt}' mise à jour: "
            f"charge_moyenne={new_charge}, taux={new_taux}, threshold={new_threshold}"
        )
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Erreur lors de la mise à jour de config_alerte: {e}")
        return False
    finally:
        conn.close()


def get_threshold_for_type(db_path: str, type_apt: str) -> float:
    """
    Récupère le seuil d'alerte pour un type d'appartement spécifique.
    
    Args:
        db_path: Chemin vers la base de données SQLite.
        type_apt: Type d'appartement (2p, 3p, 4p, 5p).
    
    Returns:
        Le seuil d'alerte configuré, ou le seuil par défaut si non trouvé.
    
    Example:
        >>> threshold = get_threshold_for_type("/path/to/db.sqlite", "3p")
        >>> print(threshold)
        2400.0
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT threshold FROM config_alerte WHERE LOWER(type_apt) = LOWER(?)",
            (type_apt,)
        )
        row = cur.fetchone()
        if row:
            return row[0]
        
        # Fallback au seuil par défaut
        cur.execute("SELECT threshold FROM config_alerte WHERE type_apt = 'default'")
        row = cur.fetchone()
        if row:
            return row[0]
        
        return DEFAULT_THRESHOLD_FALLBACK
    finally:
        conn.close()


def init_config_alerte_if_missing(db_path: str) -> bool:
    """
    Initialise la table config_alerte avec les valeurs par défaut si elle est vide.
    
    Cette fonction est utile pour migrer une base existante vers le nouveau
    système de seuils configurables.
    
    Args:
        db_path: Chemin vers la base de données SQLite.
    
    Returns:
        True si des données ont été insérées, False si la table était déjà remplie.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Vérifier si la table existe
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config_alerte'")
        if not cur.fetchone():
            logger.warning("Table config_alerte inexistante, utiliser integrite_db() d'abord")
            return False
        
        # Vérifier si la table est vide
        cur.execute("SELECT COUNT(*) FROM config_alerte")
        count = cur.fetchone()[0]
        if count > 0:
            logger.info(f"Table config_alerte déjà initialisée avec {count} entrées")
            return False
        
        # Insérer les valeurs par défaut
        for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
            cur.execute(
                """
                INSERT INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
                VALUES (?, ?, ?, ?, CURRENT_DATE)
                """,
                (type_apt, config["charge_moyenne"], config["taux"], config["threshold"])
            )
        
        # Ajouter le seuil par défaut
        cur.execute(
            """
            INSERT INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
            VALUES ('default', ?, 1.0, ?, CURRENT_DATE)
            """,
            (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK)
        )
        
        conn.commit()
        logger.success("Table config_alerte initialisée avec les valeurs par défaut")
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Erreur lors de l'initialisation de config_alerte: {e}")
        return False
    finally:
        conn.close()