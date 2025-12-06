"""
Module utilitaire pour charger le fichier .env de manière robuste.
Supporte l'exécution normale et les exécutables PyInstaller.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger


def get_app_base_path() -> Path:
    """
    Retourne le chemin de base de l'application.
    - Pour un exe PyInstaller: le dossier contenant l'exe
    - Pour une exécution normale: le dossier racine du projet (parent de src/)
    """
    if getattr(sys, 'frozen', False):
        # Exécutable PyInstaller: le .env doit être à côté de l'exe
        return Path(sys.executable).parent
    else:
        # Exécution normale: remonter depuis src/cptcopro/utils jusqu'à la racine
        return Path(__file__).parent.parent.parent.parent


def get_env_file_path() -> Path:
    """
    Retourne le chemin du fichier .env.
    """
    return get_app_base_path() / '.env'


def load_env_file() -> bool:
    """
    Charge le fichier .env s'il existe.
    
    Returns:
        True si le fichier a été chargé, False sinon.
    """
    env_path = get_env_file_path()
    
    if env_path.exists():
        load_dotenv(env_path)
        logger.bind(type_log="ENV").info(f"Fichier .env chargé depuis: {env_path}")
        return True
    else:
        logger.bind(type_log="ENV").warning(f"Fichier .env non trouvé à: {env_path}")
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
        required_vars = ['login_site_copro', 'password_site_copro', 'url_site_copro']
    
    env_path = get_env_file_path()
    
    # Vérifier l'existence du fichier
    if not env_path.exists():
        var_examples = '\n'.join(f"  - {var}=VOTRE_VALEUR" for var in required_vars)
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

def get_credentials() -> tuple[str, str, str]:
    """
    Charge et retourne les credentials du site copro.
    
    Returns:
        Tuple (login, password, url)
        
    Raises:
        FileNotFoundError: Si le fichier .env n'existe pas.
        ValueError: Si des variables requises sont manquantes.
    """
    env_vars = load_and_validate_env()
    return (
        env_vars['login_site_copro'],
        env_vars['password_site_copro'],
        env_vars['url_site_copro']
    )
