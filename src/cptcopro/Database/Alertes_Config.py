"""Module de gestion de la configuration des alertes.

Ce module gère :
- La sauvegarde du suivi des alertes (nombre, débits par type)
- La récupération et mise à jour des seuils d'alerte par type d'appartement
- L'initialisation des seuils par défaut si absents
"""

import sqlite3
from typing import Dict, List
from loguru import logger

from .constants import DEFAULT_ALERT_THRESHOLDS, DEFAULT_THRESHOLD_FALLBACK

logger = logger.bind(type_log="BDD")


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
        nb_2p = stats_par_type.get("2p", (0, 0))[0]
        nb_3p = stats_par_type.get("3p", (0, 0))[0]
        nb_4p = stats_par_type.get("4p", (0, 0))[0]
        nb_5p = stats_par_type.get("5p", (0, 0))[0]
        nb_na = stats_par_type.get("na", (0, 0))[0]

        debit_2p = stats_par_type.get("2p", (0, 0))[1]
        debit_3p = stats_par_type.get("3p", (0, 0))[1]
        debit_4p = stats_par_type.get("4p", (0, 0))[1]
        debit_5p = stats_par_type.get("5p", (0, 0))[1]
        debit_na = stats_par_type.get("na", (0, 0))[1]

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
            (
                date_releve,
                nombre_alertes,
                total_debit,
                nb_2p,
                nb_3p,
                nb_4p,
                nb_5p,
                nb_na,
                debit_2p,
                debit_3p,
                debit_4p,
                debit_5p,
                debit_na,
            ),
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


def get_config_alertes(db_path: str) -> List[Dict]:
    """
    Récupère la configuration des seuils d'alerte depuis la base de données.

    Args:
        db_path (str): Chemin vers la base de données.

    Returns:
        List[Dict]: Liste de configurations {type_apt, charge_moyenne, taux, threshold, last_update}.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("""
            SELECT type_apt, charge_moyenne, taux, threshold, last_update
            FROM config_alerte
            ORDER BY type_apt
        """)

        rows = cur.fetchall()
        return [dict(row) for row in rows]

    except sqlite3.Error as e:
        logger.error(f"Erreur SQLite lors de la récupération de config_alerte : {e}")
        return []
    finally:
        if conn:
            conn.close()


def _valider_parametre_numerique(
    valeur: float | None,
    nom: str,
    allow_zero: bool = False,
) -> tuple[float | None, str | None]:
    """
    Valide et convertit un paramètre numérique.

    Args:
        valeur: La valeur à valider (peut être None).
        nom: Nom du paramètre pour les messages d'erreur.
        allow_zero: Si True, accepte >= 0. Si False, exige > 0.

    Returns:
        Tuple (valeur_convertie, erreur). Si erreur est None, la validation a réussi.
        Si valeur est None, retourne (None, None).
    """
    if valeur is None:
        return None, None

    try:
        valeur_float = float(valeur)
    except (TypeError, ValueError) as e:
        return None, f"{nom} invalide (non numérique): {valeur} - {e}"

    if allow_zero:
        if valeur_float < 0:
            return None, f"{nom} doit être >= 0, reçu: {valeur_float}"
    else:
        if valeur_float <= 0:
            return None, f"{nom} doit être > 0, reçu: {valeur_float}"

    return valeur_float, None


def update_config_alerte(
    db_path: str,
    type_apt: str,
    charge_moyenne: float | None = None,
    taux: float | None = None,
    threshold: float | None = None,
) -> bool:
    """
    Met à jour la configuration d'alerte pour un type d'appartement.

    Permet de mettre à jour un ou plusieurs paramètres pour un type donné.
    Si threshold n'est pas fourni mais charge_moyenne et/ou taux le sont,
    le threshold est recalculé automatiquement (charge_moyenne * taux).

    Args:
        db_path (str): Chemin vers la base de données.
        type_apt (str): Type d'appartement (2p, 3p, 4p, 5p, default).
        charge_moyenne (float, optional): Nouvelle charge moyenne.
        taux (float, optional): Nouveau coefficient multiplicateur.
        threshold (float, optional): Nouveau seuil d'alerte.

    Returns:
        bool: True si succès, False sinon.
    """
    # --- Validation des entrées ---
    charge_moyenne, err = _valider_parametre_numerique(
        charge_moyenne, "charge_moyenne", allow_zero=False
    )
    if err:
        logger.error(err)
        return False

    taux, err = _valider_parametre_numerique(taux, "taux", allow_zero=False)
    if err:
        logger.error(err)
        return False

    threshold, err = _valider_parametre_numerique(
        threshold, "threshold", allow_zero=True
    )
    if err:
        logger.error(err)
        return False

    # --- Opérations DB ---
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Récupérer les valeurs actuelles
        cur.execute(
            "SELECT charge_moyenne, taux, threshold FROM config_alerte WHERE type_apt = ?",
            (type_apt.lower(),),
        )
        row = cur.fetchone()
        if not row:
            logger.error(
                f"Type d'appartement '{type_apt}' non trouvé dans config_alerte"
            )
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
            if new_charge is None or new_taux is None:
                logger.error(
                    "Impossible de recalculer threshold: charge_moyenne ou taux manquant"
                )
                return False
            if new_charge <= 0 or new_taux <= 0:
                logger.error(
                    f"Valeurs invalides pour recalcul: charge_moyenne={new_charge}, taux={new_taux}"
                )
                return False
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
            (new_charge, new_taux, new_threshold, type_apt.lower()),
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
    Récupère le seuil d'alerte pour un type d'appartement donné.

    Args:
        db_path (str): Chemin vers la base de données.
        type_apt (str): Type d'appartement.

    Returns:
        float: Seuil d'alerte, ou valeur par défaut si non trouvé.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute(
            "SELECT threshold FROM config_alerte WHERE LOWER(type_apt) = LOWER(?)",
            (type_apt,),
        )
        row = cur.fetchone()

        if row:
            return float(row[0])

        # Fallback vers 'default'
        cur.execute("SELECT threshold FROM config_alerte WHERE type_apt = 'default'")
        row = cur.fetchone()

        if row:
            return float(row[0])

        return DEFAULT_THRESHOLD_FALLBACK

    except sqlite3.Error as e:
        logger.error(
            f"Erreur SQLite lors de la récupération du seuil pour {type_apt} : {e}"
        )
        return DEFAULT_THRESHOLD_FALLBACK
    finally:
        if conn:
            conn.close()


def init_config_alerte_if_missing(db_path: str) -> bool:
    """
    Initialise la table config_alerte avec les valeurs par défaut si elle est vide.

    Args:
        db_path (str): Chemin vers la base de données.

    Returns:
        bool: True si des valeurs ont été insérées, False si la table était déjà remplie.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM config_alerte")
        count = cur.fetchone()[0]

        if count > 0:
            logger.info("Table config_alerte déjà initialisée.")
            return False

        for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
            cur.execute(
                """
                INSERT INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
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
            INSERT INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update)
            VALUES ('default', ?, 1.0, ?, CURRENT_DATE)
            """,
            (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK),
        )

        conn.commit()
        logger.success("Table config_alerte initialisée avec les valeurs par défaut.")
        return True

    except sqlite3.Error as e:
        logger.error(f"Erreur SQLite lors de l'initialisation de config_alerte : {e}")
        return False
    finally:
        if conn:
            conn.close()
