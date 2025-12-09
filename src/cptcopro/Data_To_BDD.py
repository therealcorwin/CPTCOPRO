"""Module de gestion de la base de données SQLite.

Ce module gère :
- La création et vérification des tables (charge, alertes_debit_eleve, coproprietaires, suivi_alertes)
- Les triggers pour la détection automatique des alertes de débit élevé
- L'insertion des données de charges et copropriétaires
- La mise à jour des statistiques d'alertes

Tables:
    charge: Historique des charges par copropriétaire
    alertes_debit_eleve: Alertes pour les débits > 500€
    coproprietaires: Liste des copropriétaires et leurs lots
    suivi_alertes: Statistiques journalières des alertes
"""
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

            # Créer un index unique sur code_proprietaire pour permettre l'UPSERT
            cur.executescript("""
                -- Index unique requis pour l'UPSERT (une alerte par proprietaire)
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alertes_code_proprietaire ON alertes_debit_eleve(code_proprietaire);

                -- INSERT (UPSERT) : si la nouvelle ligne (latest) a debit > 2000, créer ou mettre à jour l'alerte
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.debit > 2000.0
                  AND NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                BEGIN
                    INSERT INTO alertes_debit_eleve (
                        id_origin, nom_proprietaire, code_proprietaire, debit,
                        first_detection, last_detection, occurence
                    )
                    VALUES (
                        NEW.id, NEW.nom_proprietaire, NEW.code_proprietaire, NEW.debit,
                        CURRENT_DATE, CURRENT_DATE, 1
                    )
                    ON CONFLICT(code_proprietaire) DO UPDATE SET
                        id_origin = excluded.id_origin,
                        nom_proprietaire = excluded.nom_proprietaire,
                        debit = excluded.debit,
                        last_detection = CURRENT_DATE,
                        occurence = COALESCE(occurence, 0) + 1;
                END;

                -- INSERT_CLEAR : si la nouvelle ligne (latest) a debit <= 2000, supprimer toute alerte existante
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert_clear
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.debit <= 2000.0
                  AND NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
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
                        id_origin, nom_proprietaire, code_proprietaire, debit,
                        first_detection, last_detection, occurence
                    )
                    SELECT c.id, c.nom_proprietaire, c.code_proprietaire, c.debit,
                           CURRENT_DATE, CURRENT_DATE, 1
                    FROM charge c
                    WHERE c.code_proprietaire = OLD.code_proprietaire
                      AND c.id = (SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire)
                      AND c.debit > 2000.0;
                END;
            """)
            logger.info("Triggers 'alerte_debit_eleve' vérifiés/créés (insert/insert_clear/delete).")
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
                    total_debit REAL NOT NULL
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
                    last_detection DATE DEFAULT CURRENT_DATE,
                    first_detection DATE DEFAULT CURRENT_DATE,
                    occurence INTEGER NOT NULL,
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
            cur.executescript("""
                -- Index unique requis pour l'UPSERT (une alerte par proprietaire)
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alertes_code_proprietaire ON alertes_debit_eleve(code_proprietaire);
                
                -- INSERT (UPSERT) : si la nouvelle ligne (latest) a debit > 2000, créer ou mettre à jour l'alerte
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.debit > 2000.0
                  AND NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
                BEGIN
                    INSERT INTO alertes_debit_eleve (
                        id_origin, nom_proprietaire, code_proprietaire, debit,
                        first_detection, last_detection, occurence
                    )
                    VALUES (
                        NEW.id, NEW.nom_proprietaire, NEW.code_proprietaire, NEW.debit,
                        CURRENT_DATE, CURRENT_DATE, 1
                    )
                    ON CONFLICT(code_proprietaire) DO UPDATE SET
                        id_origin = excluded.id_origin,
                        nom_proprietaire = excluded.nom_proprietaire,
                        debit = excluded.debit,
                        last_detection = CURRENT_DATE,
                        occurence = COALESCE(occurence, 0) + 1;
                END;
                
                -- INSERT_CLEAR : si la nouvelle ligne (latest) a debit <= 2000, supprimer toute alerte existante
                CREATE TRIGGER IF NOT EXISTS alerte_debit_eleve_insert_clear
                AFTER INSERT ON charge
                FOR EACH ROW
                WHEN NEW.debit <= 2000.0
                  AND NEW.id = (SELECT MAX(id) FROM charge c WHERE c.code_proprietaire = NEW.code_proprietaire)
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
                        id_origin, nom_proprietaire, code_proprietaire, debit,
                        first_detection, last_detection, occurence
                    )
                    SELECT c.id, c.nom_proprietaire, c.code_proprietaire, c.debit,
                           CURRENT_DATE, CURRENT_DATE, 1
                    FROM charge c
                    WHERE c.code_proprietaire = OLD.code_proprietaire
                      AND c.id = (SELECT MAX(id) FROM charge WHERE code_proprietaire = OLD.code_proprietaire)
                      AND c.debit > 2000.0;
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
                    total_debit REAL NOT NULL
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
    Sauvegarde le nombre d'alertes pour une date de relevé donnée dans la table `nombre_alertes`.

    Args:
        db_path (str): Chemin vers la base de données SQLite.
    Returns:
        None
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Récupérer les valeurs à insérer
        cur.execute(
            """
            SELECT 
                MAX(last_detection) AS date_releve,
                COUNT(*) AS nombre_alertes,
                SUM(debit) AS total_debit
            FROM alertes_debit_eleve
            """
        )
        row = cur.fetchone()
        date_releve, nombre_alertes, total_debit = row[0], row[1], row[2]
        
        if date_releve is None:
            logger.warning("Aucune alerte trouvée, rien à sauvegarder.")
            return
        
        # UPSERT : INSERT OR REPLACE fonctionne grâce à UNIQUE(date_releve)
        cur.execute(
            """
            INSERT OR REPLACE INTO suivi_alertes (date_releve, nombre_alertes, total_debit)
            VALUES (?, ?, ?)
            """,
            (date_releve, nombre_alertes, total_debit)
        )
        conn.commit()
        logger.info(f"Nombre d'alertes ({nombre_alertes}) sauvegardé pour la date {date_releve}. Somme débit : {total_debit}.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Erreur lors de la sauvegarde du nombre d'alertes : {e}")
        raise
    finally:
        conn.close()
    return