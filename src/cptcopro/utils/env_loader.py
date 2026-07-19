"""
Module utilitaire pour charger le fichier .env de manière robuste.
Supporte l'exécution normale et les exécutables PyInstaller.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

from cptcopro.utils.paths import get_env_file_path as resolve_env_file_path


REQUIRED_CORE_ENV_VARS = [
    "login_site_copro",
    "password_site_copro",
    "url_site_copro",
    "url_situation_copro",
]

REQUIRED_PCLOUD_ENV_VARS = [
    "pcloud_APP_KEY",
    "pcloud_APP_SECRET",
]

REQUIRED_PCLOUD_BACKUP_ENV_VARS = [
    "pcloud_location_id",
    "pcloud_backup_folder",
    "pcloud_backup_folder_id",
    "pcloud_backup_file",
]

REQUIRED_STARTUP_ENV_VARS = [
    *REQUIRED_CORE_ENV_VARS,
    *REQUIRED_PCLOUD_ENV_VARS,
    *REQUIRED_PCLOUD_BACKUP_ENV_VARS,
]


def get_app_base_path() -> Path:
    """
    Retourne le chemin de base de l'application.
    - Pour un exe PyInstaller: le dossier contenant l'exe
    - Pour une exécution normale: le dossier racine du projet (parent de src/)
    """
    if getattr(sys, "frozen", False):
        # Exécutable PyInstaller: le .env doit être à côté de l'exe
        return Path(sys.executable).parent
    else:
        # Exécution normale: remonter depuis src/cptcopro/utils jusqu'à la racine
        return Path(__file__).parent.parent.parent.parent


def get_env_file_path() -> Path:
    """
    Retourne le chemin du fichier .env.
    """
    env_path = resolve_env_file_path()
    if env_path is not None:
        return env_path
    return get_app_base_path() / ".env"


def load_env_file() -> bool:
    """
    Charge le fichier .env s'il existe.

    Returns:
        True si le fichier a été chargé, False sinon.
    """
    env_path = get_env_file_path()

    if env_path.exists():
        load_dotenv(env_path)
        logger.bind(type_log="ENV").info(
            f"Fichier .env chargé depuis: {env_path}")
        return True
    else:
        logger.bind(type_log="ENV").warning(
            f"Fichier .env non trouvé à: {env_path}")
        return False


def check_env_file_exists() -> bool:
    """
    Vérifie si le fichier .env existe.

    Returns:
        True si le fichier existe, False sinon.
    """
    return get_env_file_path().exists()


def validate_required_env_vars(required_vars: list[str]) -> tuple[bool, list[str]]:
    """
    Vérifie que toutes les variables d'environnement requises sont présentes.

    Args:
        required_vars: Liste des noms de variables requises.

    Returns:
        Tuple (success, missing_vars) où success est True si toutes les variables
        sont présentes, et missing_vars contient la liste des variables manquantes.
    """
    missing = [var for var in required_vars if not os.getenv(var)]
    return (len(missing) == 0, missing)


def load_and_validate_env(required_vars: list[str] | None = None) -> dict[str, str]:
    """
    Charge le fichier .env et valide les variables requises.

    Args:
        required_vars: Liste des variables requises. Si None, utilise les
                      variables par défaut pour l'application.

    Returns:
        Dictionnaire contenant les variables d'environnement.

    Raises:
        FileNotFoundError: Si le fichier .env n'existe pas.
        ValueError: Si des variables requises sont manquantes.
    """
    if required_vars is None:
        required_vars = REQUIRED_CORE_ENV_VARS

    env_path = get_env_file_path()

    # Vérifier l'existence du fichier
    if not env_path.exists():
        var_examples = "\n".join(
            f"  - {var}=VOTRE_VALEUR" for var in required_vars)
        error_msg = (
            f"Fichier .env introuvable!\n"
            f"Chemin attendu: {env_path}\n"
            f"Veuillez créer un fichier .env avec les variables suivantes:\n{var_examples}"
        )
        logger.bind(type_log="ENV").error(error_msg)
        raise FileNotFoundError(error_msg)

    # Charger le fichier
    load_dotenv(env_path)
    logger.bind(type_log="ENV").info(f"Fichier .env chargé depuis: {env_path}")

    # Valider les variables requises
    success, missing = validate_required_env_vars(required_vars)
    if not success:
        error_msg = (
            f"Variables d'environnement manquantes: {', '.join(missing)}\n"
            f"Veuillez vérifier votre fichier .env à: {env_path}"
        )
        logger.bind(type_log="ENV").error(error_msg)
        raise ValueError(error_msg)

    # Retourner les variables
    return {var: os.environ[var] for var in required_vars}


def get_credentials() -> dict[str, str]:
    """
    Charge et retourne les credentials du site copro.

    Returns:
        Dictionnaire avec les clés:
        - login_site_copro
        - password_site_copro
        - url_site_copro

    Raises:
        FileNotFoundError: Si le fichier .env n'existe pas.
        ValueError: Si des variables requises sont manquantes.
    """
    required_vars = [
        "login_site_copro",
        "password_site_copro",
        "url_site_copro",
    ]
    env_vars = load_and_validate_env(required_vars)

    return {
        "login_site_copro": env_vars["login_site_copro"],
        "password_site_copro": env_vars["password_site_copro"],
        "url_site_copro": env_vars["url_site_copro"],
    }


def get_pcloud_credentials() -> dict[str, str]:
    """
    Charge et retourne les credentials OAuth2 pCloud.

    Returns:
        Dictionnaire avec les clés:
        - pcloud_APP_KEY
        - pcloud_APP_SECRET

    Raises:
        FileNotFoundError: Si le fichier .env n'existe pas.
        ValueError: Si des variables requises sont manquantes.
    """
    required_vars = REQUIRED_PCLOUD_ENV_VARS
    env_vars = load_and_validate_env(required_vars)

    return {
        "pcloud_APP_KEY": env_vars["pcloud_APP_KEY"],
        "pcloud_APP_SECRET": env_vars["pcloud_APP_SECRET"],
    }


def get_pcloud_backup_config() -> dict[str, str | int]:
    """
    Charge et retourne la configuration de backup pCloud.

    Variables requises:
        - pcloud_location_id
        - pcloud_backup_folder
        - pcloud_backup_folder_id
        - pcloud_backup_file

    Returns:
        Dictionnaire avec les clés:
        - pcloud_location_id (int)
        - pcloud_backup_folder (str)
        - pcloud_backup_folder_id (str)
        - pcloud_backup_file (str)

    Raises:
        FileNotFoundError: Si le fichier .env n'existe pas.
        ValueError: Si des variables requises sont manquantes ou invalides.
    """
    required_vars = REQUIRED_PCLOUD_BACKUP_ENV_VARS
    env_vars = load_and_validate_env(required_vars)

    try:
        location_id = int(env_vars["pcloud_location_id"])
    except ValueError as exc:
        raise ValueError(
            "La variable pcloud_location_id doit etre un entier."
        ) from exc

    return {
        "pcloud_location_id": location_id,
        "pcloud_backup_folder": env_vars["pcloud_backup_folder"],
        "pcloud_backup_folder_id": env_vars["pcloud_backup_folder_id"],
        "pcloud_backup_file": env_vars["pcloud_backup_file"],
    }


def validate_startup_env() -> dict[str, str]:
    """
    Valide l'ensemble des variables d'environnement requises au lancement.

    Returns:
        Dictionnaire contenant toutes les variables requises au demarrage.

    Raises:
        FileNotFoundError: Si le fichier .env n'existe pas.
        ValueError: Si des variables requises sont manquantes.
    """
    env_vars = load_and_validate_env(REQUIRED_STARTUP_ENV_VARS)
    logger.bind(type_log="ENV").info(
        "Validation des variables d'environnement de demarrage reussie"
    )
    return env_vars
