import os
import shutil
import sqlite3
from datetime import datetime
from loguru import logger

logger.remove()
logger = logger.bind(type_log="BACKUP")


def backup_db(db_path) -> None:
    """
    Sauvegarde la base de données SQLite dans un dossier 'BACKUP' du répertoire courant.
    Le fichier de sauvegarde est nommé au format 'backup_bdd-DD-MM-YY-HH-MM-SS'. Toutes les étapes et événements sont enregistrés dans le fichier 'backup.txt' via loguru.
    Args:
        db_path (str): Chemin vers la base de données à sauvegarder.
    """
    now: datetime = datetime.now()
    backup_dir: str = os.path.join(os.path.dirname(__file__), "BACKUP")
    backup_filename: str = f"backup_{os.path.basename(db_path)}-{now.strftime('%d-%m-%y-%H-%M-%S')}.sqlite"
    backup_path: str = os.path.join(backup_dir, backup_filename)

    logger.info("Démarrage de la sauvegarde de la base de données.")

    logger.info("Vérification de l'existence du répertoire de sauvegarde.")

    # Vérification et création du dossier backup
    if not os.path.exists(backup_dir):
        logger.warning("Le répertoire 'BACKUP' n'existe pas. Création en cours...")
        try:
            os.makedirs(backup_dir)
            logger.success("Répertoire 'BACKUP' créé.")
        except Exception as e:
            logger.error(f"Erreur lors de la création du répertoire 'BACKUP' : {e}")
            return
    else:
        logger.info("Répertoire 'BACKUP' déjà existant.")

    # Vérification de l'existence de la base de données
    if not os.path.exists(db_path):
        logger.error(f"Base de données '{db_path}' introuvable. Sauvegarde annulée.")
        return

    # Vérifier s'il y a une connexion persistante en cours
    try:
        # Tentative d'ouverture et fermeture propre
        conn = sqlite3.connect(db_path)
        conn.close()
        logger.info("Connexion à la base de données fermée avant sauvegarde.")
    except Exception as e:
        logger.error(f"Erreur lors de la fermeture de la connexion à la base : {e}")

    # Sauvegarde de la base de données
    try:
        logger.info("Sauvegarde de la base de données en cours...")
        shutil.copy2(db_path, backup_path)
        logger.info(f"Base de données sauvegardée sous '{backup_path}'.")
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de la base de données : {e}")
        return

    logger.info("Sauvegarde terminée avec succès.")
