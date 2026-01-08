"""Utilitaires pour gérer les chemins de fichiers de manière portable.

Ce module fournit des fonctions pour déterminer les chemins corrects
que ce soit en mode développement ou depuis un bundle PyInstaller.

En mode PyInstaller (--onefile), les fichiers sont extraits dans un dossier
temporaire (_MEIPASS), mais les données persistantes (DB, logs, backup)
doivent être stockées dans le répertoire de l'exécutable.
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_LOG = logging.getLogger(__name__)

# État de chargement du .env
_env_loaded = False


def init_env() -> bool:
    """Charge le fichier .env depuis src/cptcopro/ ou à côté de l'exe.

    Cette fonction doit être appelée explicitement avant d'utiliser
    les variables d'environnement (CPTCOPRO_DB_NAME, etc.).

    Returns:
        True si le fichier .env a été chargé, False sinon.
    """
    global _env_loaded
    if _env_loaded:
        return True

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Mode PyInstaller: chercher à côté de l'exe
        env_path = Path(sys.executable).parent / ".env"
        location = "exe directory"
    else:
        # Mode développement: src/cptcopro/.env
        env_path = Path(__file__).parent.parent / ".env"
        location = "src/cptcopro"

    if env_path.exists():
        load_dotenv(env_path)
        _LOG.debug(f"Fichier .env chargé depuis {location}")
        _env_loaded = True
        return True

    _LOG.debug(f"Fichier .env non trouvé dans {location}")
    return False


def is_pyinstaller_bundle() -> bool:
    """Vérifie si on s'exécute depuis un bundle PyInstaller."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_app_dir() -> Path:
    """Retourne le répertoire de l'application.

    - En mode PyInstaller: répertoire contenant l'exe
    - En mode développement: répertoire src/cptcopro
    """
    if is_pyinstaller_bundle():
        # sys.executable pointe vers l'exe
        return Path(sys.executable).parent
    else:
        # Mode développement: src/cptcopro
        return Path(__file__).parent.parent


def get_bundle_dir() -> Path:
    """Retourne le répertoire des ressources bundlées (assets, config, etc.).

    - En mode PyInstaller: _MEIPASS (dossier temporaire avec les fichiers extraits)
    - En mode développement: src/cptcopro
    """
    if is_pyinstaller_bundle():
        return Path(sys._MEIPASS) / "cptcopro"
    else:
        return Path(__file__).parent.parent


def get_data_dir() -> Path:
    """Retourne le répertoire pour les données persistantes (DB, logs, backup).

    - En mode PyInstaller: répertoire de l'exe
    - En mode développement: src/cptcopro

    Ce répertoire est créé s'il n'existe pas.
    """
    data_dir = get_app_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


_DEFAULT_DB_NAME = "coproprietaires.sqlite"


def get_db_path(db_name: str | None = None) -> Path:
    """Retourne le chemin complet vers la base de données.

    Le nom du fichier est déterminé dans cet ordre de priorité:
    1. Paramètre `db_name` s'il est fourni
    2. Variable d'environnement `CPTCOPRO_DB_NAME` (depuis .env)
    3. Valeur par défaut: coproprietaires.sqlite

    Note: `CPTCOPRO_DB_PATH` permet de surcharger le chemin complet (pour CI/tests),
    tandis que `CPTCOPRO_DB_NAME` ne change que le nom du fichier.

    Args:
        db_name: Nom du fichier de base de données (optionnel)

    Returns:
        Chemin vers le fichier DB dans le sous-dossier BDD/

    Raises:
        OSError: Si le répertoire parent ne peut pas être créé
    """
    # Variable d'environnement pour override du chemin complet (CI, tests, etc.)
    env_path = os.getenv("CPTCOPRO_DB_PATH")
    if env_path and env_path.strip():
        # Convertir en chemin absolu
        path = Path(env_path).resolve()
        _LOG.info(f"DB path from environment variable: {path}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            _LOG.error(f"Cannot create DB directory '{path.parent}': {e}")
            raise OSError(f"Cannot create DB directory '{path.parent}': {e}") from e
        return path

    # Déterminer le nom de la BDD: paramètre > variable d'env > défaut
    if db_name is None:
        env_db_name = os.getenv("CPTCOPRO_DB_NAME")
        if env_db_name and env_db_name.strip():
            db_name = env_db_name.strip()
        else:
            db_name = _DEFAULT_DB_NAME

    db_dir = get_data_dir() / "BDD"
    try:
        db_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _LOG.error(f"Cannot create DB directory '{db_dir}': {e}")
        raise OSError(f"Cannot create DB directory '{db_dir}': {e}") from e
    return db_dir / db_name


def get_log_path(log_name: str = "cptcopro.log") -> Path:
    """Retourne le chemin complet vers le fichier de log.

    Args:
        log_name: Nom du fichier de log (défaut: cptcopro.log)

    Returns:
        Chemin vers le fichier de log dans le sous-dossier logs/

    Raises:
        OSError: Si le répertoire parent ne peut pas être créé
    """
    # Variable d'environnement pour override
    env_path = os.getenv("CPTCOPRO_LOG_FILE")
    if env_path and env_path.strip():
        path = Path(env_path).resolve()
        _LOG.debug(f"Log path from environment variable: {path}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            _LOG.error(f"Cannot create log directory '{path.parent}': {e}")
            raise OSError(f"Cannot create log directory '{path.parent}': {e}") from e
        return path

    log_dir = get_data_dir() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _LOG.error(f"Cannot create log directory '{log_dir}': {e}")
        raise OSError(f"Cannot create log directory '{log_dir}': {e}") from e
    return log_dir / log_name


def get_backup_dir() -> Path:
    """Retourne le répertoire pour les backups.

    Returns:
        Chemin vers le sous-dossier Backup/
    """
    backup_dir = get_data_dir() / "Backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def get_env_file_path() -> Optional[Path]:
    """Retourne le chemin vers le fichier .env s'il existe.

    Cherche dans l'ordre:
    1. Répertoire de l'exe (mode PyInstaller)
    2. Répertoire bundle (_MEIPASS/cptcopro)
    3. Répertoire src/cptcopro (mode dev)

    Returns:
        Chemin vers .env ou None si non trouvé
    """
    # D'abord chercher à côté de l'exe (pour config utilisateur)
    app_env = get_app_dir() / ".env"
    if app_env.exists():
        return app_env

    # Ensuite dans le bundle (config par défaut)
    bundle_env = get_bundle_dir() / ".env"
    if bundle_env.exists():
        return bundle_env

    # Mode dev: chercher dans le répertoire courant ou parent
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env

    return None


def get_streamlit_config_dir() -> Optional[Path]:
    """Retourne le répertoire de configuration Streamlit.

    Returns:
        Chemin vers .streamlit/ ou None si non trouvé
    """
    # D'abord à côté de l'exe (config utilisateur)
    app_config = get_app_dir() / ".streamlit"
    if app_config.is_dir():
        return app_config

    # Ensuite dans le bundle
    bundle_config = get_bundle_dir() / ".streamlit"
    if bundle_config.is_dir():
        return bundle_config

    return None


# Afficher les chemins au chargement du module (debug)
if __name__ == "__main__":
    print(f"PyInstaller bundle: {is_pyinstaller_bundle()}")
    print(f"App dir: {get_app_dir()}")
    print(f"Bundle dir: {get_bundle_dir()}")
    print(f"Data dir: {get_data_dir()}")
    print(f"DB path: {get_db_path()}")
    print(f"Log path: {get_log_path()}")
    print(f"Backup dir: {get_backup_dir()}")
    print(f"Env file: {get_env_file_path()}")
    print(f"Streamlit config: {get_streamlit_config_dir()}")
