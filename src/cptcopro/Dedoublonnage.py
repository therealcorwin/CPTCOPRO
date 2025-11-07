"""
Module pour le nettoyage et la maintenance de la base de données.
"""

import sqlite3
from pathlib import Path
from typing import Union

from loguru import logger

logger.remove()
logger.bind(type_log="DEDOUBLONNAGE")


def dedoublonner_base_de_donnees(db_path: Union[str, Path]) -> None:
    """
    Dédoublonne la table 'coproprietaires' dans la base de données SQLite.

    La règle de dédoublonnage est la suivante : pour un ensemble de lignes
    ayant les mêmes 'code', 'coproprietaire' et 'date', seul l'enregistrement
    avec la date 'last_check' la plus récente est conservé. Les autres sont
    supprimés.

    Args:
        db_path (Union[str, Path]): Le chemin vers le fichier de la base de données SQLite.
    """
    logger.info("Début du processus de dédoublonnage de la base de données.")
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # La requête identifie les lignes à supprimer.
            # Pour chaque groupe (code_proprietaire, nom_proprietaire, date),
            # on conserve la ligne ayant le MAX(rowid) et on supprime les autres.
            query = """
            DELETE FROM coproprietaires
            WHERE rowid NOT IN (
                SELECT MAX(rowid)
                FROM coproprietaires
                GROUP BY code_proprietaire, nom_proprietaire, date
            );
            """
            cursor.execute(query)
            conn.commit()
            logger.success(
                f"{cursor.rowcount} enregistrement(s) en double supprimé(s)."
            )
    except sqlite3.Error as e:
        logger.error(f"Erreur lors du dédoublonnage de la base de données : {e}")


if __name__ == "__main__":
    # Exemple d'utilisation
    DB_FILE = Path(__file__).parent / "coproprietaires_test.sqlite"
    if DB_FILE.exists():
        dedoublonner_base_de_donnees(DB_FILE)
    else:
        logger.warning(f"La base de données '{DB_FILE}' n'a pas été trouvée.")
