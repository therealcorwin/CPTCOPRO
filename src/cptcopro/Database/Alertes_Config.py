"""Module de gestion de la configuration des alertes (MariaDB).

Ce module gere :
- La sauvegarde du suivi des alertes (nombre, debits par type)
- La recuperation et mise a jour des seuils d alerte par type d appartement
- L initialisation des seuils par defaut si absents

Optimisation reseau cle : sauvegarder_nombre_alertes() fusionne les 2
requetes SQLite (stats globales + stats par type) en 1 seule avec WITH ROLLUP.
"""

from typing import Any

from loguru import logger

from .connection import get_db_connection, get_db_cursor
from .constants import DEFAULT_ALERT_THRESHOLDS, DEFAULT_THRESHOLD_FALLBACK

_logger = logger.bind(type_log="BDD")


def sauvegarder_nombre_alertes() -> None:
    """Sauvegarde le nombre d alertes dans la table suivi_alertes.

    Optimisation : 1 seul aller-retour reseau via GROUP BY ... WITH ROLLUP.
    La ligne avec type_apt=NULL est le total global (produit par ROLLUP).
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # WITH ROLLUP : une seule passe sur alertes_debit_eleve pour
            # obtenir les stats globales ET par type d appartement.
            cur.execute("""
                SELECT
                    LOWER(COALESCE(NULLIF(type_alerte, ''), 'na')) AS type_apt,
                    MAX(date_origin) AS date_releve,
                    COUNT(*) AS nb,
                    COALESCE(SUM(debit), 0) AS total
                FROM alertes_debit_eleve
                GROUP BY type_apt WITH ROLLUP
            """)
            rows = cur.fetchall()

        if not rows:
            _logger.warning("Aucune alerte trouvee, rien a sauvegarder.")
            return

        # La ligne ROLLUP a type_apt=None -> total global
        rollup_row = next((r for r in rows if r["type_apt"] is None), None)
        if rollup_row is None:
            _logger.warning("Ligne ROLLUP absente.")
            return

        date_releve = rollup_row["date_releve"]
        nombre_alertes = rollup_row["nb"]
        total_debit = rollup_row["total"]

        if date_releve is None:
            _logger.warning("Aucune alerte trouvee, rien a sauvegarder.")
            return

        stats: dict[str, tuple[int, float]] = {
            r["type_apt"]: (r["nb"], float(r["total"])) for r in rows if r["type_apt"] is not None
        }

        nb_2p, debit_2p = stats.get("2p", (0, 0.0))
        nb_3p, debit_3p = stats.get("3p", (0, 0.0))
        nb_4p, debit_4p = stats.get("4p", (0, 0.0))
        nb_5p, debit_5p = stats.get("5p", (0, 0.0))
        nb_na, debit_na = stats.get("na", (0, 0.0))

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO suivi_alertes (
                        date_releve, nombre_alertes, total_debit,
                        nb_2p, nb_3p, nb_4p, nb_5p, nb_na,
                        debit_2p, debit_3p, debit_4p, debit_5p, debit_na
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        nombre_alertes = VALUES(nombre_alertes),
                        total_debit    = VALUES(total_debit),
                        nb_2p = VALUES(nb_2p), nb_3p = VALUES(nb_3p),
                        nb_4p = VALUES(nb_4p), nb_5p = VALUES(nb_5p), nb_na = VALUES(nb_na),
                        debit_2p = VALUES(debit_2p), debit_3p = VALUES(debit_3p),
                        debit_4p = VALUES(debit_4p), debit_5p = VALUES(debit_5p),
                        debit_na = VALUES(debit_na)
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

    _logger.info(
        f"Alertes sauvegardees pour {date_releve}: "
        f"total={nombre_alertes} ({total_debit}), "
        f"2p={nb_2p}, 3p={nb_3p}, 4p={nb_4p}, 5p={nb_5p}, na={nb_na}"
    )


def get_config_alertes() -> list[dict[str, Any]]:
    """Recupere la configuration des seuils d alerte depuis MariaDB.

    Returns:
        Liste de dicts {type_apt, charge_moyenne, taux, threshold, last_update}.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT type_apt, charge_moyenne, taux, threshold, last_update
                FROM config_alerte
                ORDER BY type_apt
            """)
            return list(cur.fetchall())
    except Exception as exc:
        _logger.error(f"Erreur lors de la recuperation de config_alerte : {exc}")
        return []


def _valider_parametre_numerique(
    valeur: float | None,
    nom: str,
    allow_zero: bool = False,
) -> tuple[float | None, str | None]:
    """Valide et convertit un parametre numerique."""
    if valeur is None:
        return None, None
    try:
        valeur_float = float(valeur)
    except (TypeError, ValueError) as exc:
        return None, f"{nom} invalide (non numerique): {valeur} - {exc}"
    if allow_zero:
        if valeur_float < 0:
            return None, f"{nom} doit etre >= 0, recu: {valeur_float}"
    else:
        if valeur_float <= 0:
            return None, f"{nom} doit etre > 0, recu: {valeur_float}"
    return valeur_float, None


def update_config_alerte(
    type_apt: str,
    charge_moyenne: float | None = None,
    taux: float | None = None,
    threshold: float | None = None,
) -> bool:
    """Met a jour la configuration d alerte pour un type d appartement.

    Args:
        type_apt: Type d appartement (2p, 3p, 4p, 5p, default).
        charge_moyenne: Nouvelle charge moyenne (optionnel).
        taux: Nouveau coefficient multiplicateur (optionnel).
        threshold: Nouveau seuil d alerte (optionnel).

    Returns:
        True si succes, False sinon.
    """
    charge_moyenne, err = _valider_parametre_numerique(charge_moyenne, "charge_moyenne")
    if err:
        _logger.error(err)
        return False
    taux, err = _valider_parametre_numerique(taux, "taux")
    if err:
        _logger.error(err)
        return False
    threshold, err = _valider_parametre_numerique(threshold, "threshold", allow_zero=True)
    if err:
        _logger.error(err)
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT charge_moyenne, taux, threshold FROM config_alerte WHERE type_apt = %s",
                    (type_apt.lower(),),
                )
                row = cur.fetchone()
                if not row:
                    _logger.error(f"Type '{type_apt}' non trouve dans config_alerte")
                    return False

                new_charge = (
                    charge_moyenne if charge_moyenne is not None else float(row["charge_moyenne"])
                )
                new_taux = taux if taux is not None else float(row["taux"])

                if threshold is not None:
                    new_threshold = threshold
                elif charge_moyenne is not None or taux is not None:
                    if new_charge <= 0 or new_taux <= 0:
                        _logger.error(f"Valeurs invalides: charge={new_charge}, taux={new_taux}")
                        return False
                    new_threshold = new_charge * new_taux
                else:
                    new_threshold = float(row["threshold"])

                cur.execute(
                    """
                    UPDATE config_alerte
                    SET charge_moyenne = %s, taux = %s, threshold = %s, last_update = CURRENT_DATE
                    WHERE type_apt = %s
                """,
                    (new_charge, new_taux, new_threshold, type_apt.lower()),
                )

        _logger.info(
            f"Config alerte '{type_apt}' mise a jour: "
            f"charge_moyenne={new_charge}, taux={new_taux}, threshold={new_threshold}"
        )
        return True
    except Exception as exc:
        _logger.error(f"Erreur lors de la mise a jour de config_alerte: {exc}")
        return False


def get_threshold_for_type(type_apt: str) -> float:
    """Recupere le seuil d alerte pour un type d appartement.

    Args:
        type_apt: Type d appartement.

    Returns:
        Seuil d alerte, ou valeur par defaut si non trouve.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT threshold FROM config_alerte WHERE LOWER(type_apt) = LOWER(%s)",
                (type_apt,),
            )
            row = cur.fetchone()
            if row:
                return float(row["threshold"])
            cur.execute("SELECT threshold FROM config_alerte WHERE type_apt = 'default'")
            row = cur.fetchone()
            if row:
                return float(row["threshold"])
            return DEFAULT_THRESHOLD_FALLBACK
    except Exception as exc:
        _logger.error(f"Erreur recuperation seuil pour {type_apt}: {exc}")
        return DEFAULT_THRESHOLD_FALLBACK


def init_config_alerte_if_missing() -> bool:
    """Initialise config_alerte avec les valeurs par defaut si vide.

    Returns:
        True si des valeurs ont ete inserees, False si deja remplie.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM config_alerte")
                row = cur.fetchone()
                if row and row["cnt"] > 0:
                    _logger.info("Table config_alerte deja initialisee.")
                    return False

                for type_apt, config in DEFAULT_ALERT_THRESHOLDS.items():
                    cur.execute(
                        "INSERT INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update) VALUES (%s, %s, %s, %s, CURRENT_DATE)",
                        (type_apt, config["charge_moyenne"], config["taux"], config["threshold"]),
                    )
                cur.execute(
                    "INSERT INTO config_alerte (type_apt, charge_moyenne, taux, threshold, last_update) VALUES ('default', %s, 1.0, %s, CURRENT_DATE)",
                    (DEFAULT_THRESHOLD_FALLBACK, DEFAULT_THRESHOLD_FALLBACK),
                )

        _logger.success("Table config_alerte initialisee avec les valeurs par defaut.")
        return True
    except Exception as exc:
        _logger.error(f"Erreur lors de l initialisation de config_alerte: {exc}")
        return False
