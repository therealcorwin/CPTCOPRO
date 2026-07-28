"""Module d'insertion des copropriétaires dans la base de données SQLite.

Ce module gère l'insertion/mise à jour des données des copropriétaires
avec leurs informations de lots (numéro et type d'appartement).
"""
import sqlite3
from collections import Counter
from typing import Any, List
from loguru import logger

logger = logger.bind(type_log="BDD")


class CollecteCoproprietairesInvalideError(RuntimeError):
    """Erreur levée quand la collecte copropriétaires/lots est incohérente."""


def _normaliser_lot_type(num_apt: str, type_apt: str) -> tuple[str, str]:
    """Normalise les clés lot/type pour comparaisons de stabilité."""
    return (str(num_apt).strip(), str(type_apt).strip().lower())


def _est_marqueur_non_lot(num_apt: str, type_apt: str) -> bool:
    """Retourne True pour les marqueurs non-lot explicites (NA)."""
    return str(num_apt).strip().upper() == "NA" and str(type_apt).strip().upper() == "NA"


def _valider_collecte(data: list[tuple[str, str, str, str]], cur: sqlite3.Cursor) -> None:
    """Valide la cohérence métier de la collecte avant remplacement de la table."""
    invalides: list[str] = []
    lots_entrants: list[tuple[str, str]] = []

    for nom, code, num_apt, type_apt in data:
        num_norm = str(num_apt).strip()
        type_norm = str(type_apt).strip()
        nom_norm = str(nom).strip()
        code_norm = str(code).strip()

        if _est_marqueur_non_lot(num_norm, type_norm):
            continue

        if not nom_norm or not code_norm:
            invalides.append(
                f"propriétaire/code vide pour lot={num_norm or '<vide>'}, type={type_norm or '<vide>'}"
            )
            continue

        if not num_norm or not type_norm:
            invalides.append(
                f"lot/type vide pour propriétaire={nom_norm or '<vide>'}, code={code_norm or '<vide>'}"
            )
            continue

        lots_entrants.append(_normaliser_lot_type(num_norm, type_norm))

    if invalides:
        details = "; ".join(invalides[:3])
        if len(invalides) > 3:
            details += f"; ... ({len(invalides)} anomalies au total)"
        raise CollecteCoproprietairesInvalideError(
            "Collecte lots invalide: au moins une association propriétaire/numéro de lot/type appartement est incohérente. "
            f"Détails: {details}."
        )

    doublons = [lot for lot, count in Counter(lots_entrants).items() if count > 1]
    if doublons:
        exemples = ", ".join(f"({num},{typ})" for num, typ in doublons[:5])
        raise CollecteCoproprietairesInvalideError(
            "Collecte lots invalide: doublons détectés sur les clés (numéro lot, type appartement): "
            f"{exemples}."
        )

    rows_existantes = cur.execute(
        """
        SELECT num_apt, type_apt
        FROM coproprietaires
        WHERE COALESCE(TRIM(num_apt), '') <> ''
          AND COALESCE(TRIM(type_apt), '') <> ''
          AND UPPER(TRIM(num_apt)) <> 'NA'
          AND UPPER(TRIM(type_apt)) <> 'NA'
        """
    ).fetchall()

    lots_existants = {
        _normaliser_lot_type(num_apt, type_apt)
        for num_apt, type_apt in rows_existantes
    }
    lots_entrants_set = set(lots_entrants)

    if not lots_existants:
        # Premier chargement: pas de baseline à comparer.
        return

    if len(lots_entrants_set) != len(lots_existants):
        raise CollecteCoproprietairesInvalideError(
            "Collecte lots invalide: le nombre de lots a changé. "
            f"attendu={len(lots_existants)}, collecté={len(lots_entrants_set)}."
        )

    if lots_entrants_set != lots_existants:
        manquants = sorted(lots_existants - lots_entrants_set)[:5]
        inattendus = sorted(lots_entrants_set - lots_existants)[:5]
        raise CollecteCoproprietairesInvalideError(
            "Collecte lots invalide: l'ensemble des associations (numéro lot, type appartement) diffère de la baseline. "
            f"Manquants={manquants}; Inattendus={inattendus}."
        )


def enregistrer_coproprietaires(data_coproprietaires: List[Any], db_path: str) -> None:
    """
    Insère des informations de copropriétaires dans la table `coproprietaires`.
    
    Args:
        data_coproprietaires: Liste de dictionnaires contenant les clés:
            - nom_proprietaire (ou proprietaire): nom du propriétaire
            - code_proprietaire (ou code): code du propriétaire
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
        return None
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        _valider_collecte(data, cur)

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
    return None
