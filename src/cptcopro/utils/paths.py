"""Utilitaires pour gérer les chemins de fichiers de manière portable.

Ce module fournit des fonctions pour déterminer les chemins corrects
que ce soit en mode développement ou depuis un bundle PyInstaller.

En mode PyInstaller (--onefile), les fichiers sont extraits dans un dossier
temporaire (_MEIPASS), mais les données persistantes (DB, logs, backup)
doivent être stockées dans le répertoire de l'exécutable.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_LOG = logging.getLogger(__name__)


def get_project_root_dir() -> Path:
    """Retourne la racine du projet en mode dev, sinon le répertoire de l'exe.

    En développement, les chemins de configuration utilisateur sont résolus
    depuis la racine du dépôt. En bundle PyInstaller, ils sont résolus à côté
    de l'exécutable.
    """
    if is_pyinstaller_bundle():
        return get_app_dir()
    return Path(__file__).parent.parent.parent.parent


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
        return Path(getattr(sys, "_MEIPASS", "")) / "cptcopro"
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


def get_env_file_path() -> Path | None:
    """Retourne le chemin vers le fichier .env s'il existe.

    Cherche dans l'ordre:
    1. Répertoire de l'exe (mode PyInstaller)
    2. Répertoire racine du projet (mode dev)
    3. Répertoire bundle (_MEIPASS/cptcopro)
    4. Répertoire src/cptcopro (compatibilité legacy)
    5. Répertoire courant

    Returns:
        Chemin vers .env ou None si non trouvé
    """
    if is_pyinstaller_bundle():
        app_env = get_app_dir() / ".env"
        if app_env.exists():
            return app_env

        bundle_env = get_bundle_dir() / ".env"
        if bundle_env.exists():
            return bundle_env

        return None

    project_env = get_project_root_dir() / ".env"
    if project_env.exists():
        return project_env

    bundle_env = get_bundle_dir() / ".env"
    if bundle_env.exists():
        return bundle_env

    app_env = get_app_dir() / ".env"
    if app_env.exists():
        return app_env

    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env

    return None


def get_streamlit_config_dir() -> Path | None:
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


def init_env() -> bool:
    """Charge le fichier .env (délégué à env_loader.load_env_file)."""
    from cptcopro.utils.env_loader import load_env_file

    return load_env_file()


# Afficher les chemins au chargement du module (debug)
if __name__ == "__main__":
    print(f"PyInstaller bundle: {is_pyinstaller_bundle()}")
    print(f"App dir: {get_app_dir()}")
    print(f"Bundle dir: {get_bundle_dir()}")
    print(f"Data dir: {get_data_dir()}")
    print(f"Log path: {get_log_path()}")
    print(f"Backup dir: {get_backup_dir()}")
    print(f"Env file: {get_env_file_path()}")
    print(f"Streamlit config: {get_streamlit_config_dir()}")
