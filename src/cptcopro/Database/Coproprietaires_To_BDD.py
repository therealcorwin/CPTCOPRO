"""Module insertion coproprietaires MariaDB."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pymysql.cursors
from loguru import logger

from .connection import get_db_connection

_logger = logger.bind(type_log="BDD")


class CollecteCoproprietairesInvalideError(RuntimeError):
    pass


def _normaliser_lot_type(num_apt: str, type_apt: str) -> tuple[str, str]:
    return (str(num_apt).strip(), str(type_apt).strip().lower())


def _est_marqueur_non_lot(num_apt: str, type_apt: str) -> bool:
    return str(num_apt).strip().upper() == "NA" and str(type_apt).strip().upper() == "NA"


def _valider_collecte(
    data: list[tuple[str, str, str, str]], cur: pymysql.cursors.DictCursor
) -> None:
    invalides: list[str] = []
    lots_entrants: list[tuple[str, str]] = []
    for nom, code, num_apt, type_apt in data:
        num_norm = str(num_apt).strip()
        type_norm = str(type_apt).strip()
        if _est_marqueur_non_lot(num_norm, type_norm):
            continue
        if not str(nom).strip() or not str(code).strip():
            invalides.append(f"proprietaire/code vide lot={num_norm}")
            continue
        if not num_norm or not type_norm:
            invalides.append(f"lot/type vide proprietaire={nom}")
            continue
        lots_entrants.append(_normaliser_lot_type(num_norm, type_norm))
    if invalides:
        details = "; ".join(invalides[:3])
        raise CollecteCoproprietairesInvalideError(details)
    doublons = [lot for lot, c in Counter(lots_entrants).items() if c > 1]
    if doublons:
        raise CollecteCoproprietairesInvalideError(f"doublons: {doublons[:5]}")
    sql = (
        "SELECT num_apt, type_apt FROM coproprietaires"
        " WHERE UPPER(TRIM(num_apt)) != 'NA' AND UPPER(TRIM(type_apt)) != 'NA'"
        " AND TRIM(num_apt) != '' AND TRIM(type_apt) != ''"
    )
    cur.execute(sql)
    rows = cur.fetchall()
    existants = {_normaliser_lot_type(r["num_apt"], r["type_apt"]) for r in rows}
    entrants = set(lots_entrants)
    if not existants:
        return
    if len(entrants) != len(existants):
        raise CollecteCoproprietairesInvalideError(
            f"Nombre de lots change: attendu={len(existants)}, collecte={len(entrants)}"
        )
    if entrants != existants:
        manquants = sorted(existants - entrants)[:5]
        inattendus = sorted(entrants - existants)[:5]
        raise CollecteCoproprietairesInvalideError(
            f"Lots differents. Manquants={manquants} Inattendus={inattendus}"
        )


def enregistrer_coproprietaires(data_coproprietaires: list[Any]) -> None:
    """Insere coproprietaires via batch UPSERT MariaDB (1 seul aller-retour reseau)."""
    _logger.info("Insertion des coproprietaires...")
    data: list[tuple[str, str, str, str]] = []
    for copro in data_coproprietaires:
        nom = copro.get("nom_proprietaire") or copro.get("proprietaire") or ""
        code = copro.get("code_proprietaire") or copro.get("code") or ""
        data.append((nom, code, copro.get("num_apt") or "", copro.get("type_apt") or ""))
    if not data:
        _logger.info("Aucune donnee a inserer.")
        return
    upsert_sql = (
        "INSERT INTO coproprietaires"
        " (nom_proprietaire, code_proprietaire, num_apt, type_apt, last_check)"
        " VALUES (%s, %s, %s, %s, CURRENT_DATE)"
        " ON DUPLICATE KEY UPDATE"
        " nom_proprietaire=VALUES(nom_proprietaire),"
        " num_apt=VALUES(num_apt),"
        " type_apt=VALUES(type_apt),"
        " last_check=VALUES(last_check)"
    )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _valider_collecte(data, cur)
            cur.executemany(upsert_sql, data)
    _logger.info(f"{len(data)} coproprietaires UPSERT MariaDB.")
