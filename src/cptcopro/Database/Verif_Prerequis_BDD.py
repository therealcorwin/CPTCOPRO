"""Module de vérification des prérequis de la base de données SQLite.

Ce module gère :
- La vérification de l'existence du répertoire de la base
- La création du répertoire si nécessaire
"""
import os
from loguru import logger

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
