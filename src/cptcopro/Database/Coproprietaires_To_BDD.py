"""Module d'insertion des copropriétaires dans la base de données SQLite.

Ce module gère l'insertion/mise à jour des données des copropriétaires
avec leurs informations de lots (numéro et type d'appartement).
"""
import sqlite3
from typing import Any, List
from loguru import logger

logger = logger.bind(type_log="BDD")


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
