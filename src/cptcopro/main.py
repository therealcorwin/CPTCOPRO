"""Point d'entrée principal de l'application CPTCOPRO.

Ce module orchestre :
- La récupération parallèle du HTML (charges et lots) via Playwright
- Le parsing des données avec selectolax
- La sauvegarde en base SQLite
- Le lancement de l'interface Streamlit

Usage:
    python -m cptcopro.main [OPTIONS]

Options:
    --no-headless     Lance Playwright en mode visible (debug)
    --db-path PATH    Surcharge le chemin de la base de données
    --no-serve        Ne pas lancer Streamlit après le traitement
    --show-console    Afficher les données dans la console (rich)
"""

import sys
import cptcopro.Database.Backup_DB_Pcloud as bckp_pcloud
import pathlib
from cptcopro.utils.paths import get_db_path, get_log_path
from cptcopro.utils.env_loader import validate_startup_env
from cptcopro.pipeline import CptcoproPipeline, PipelineRuntimeOptions
from loguru import logger

# Charger et valider les variables d'environnement avant toute utilisation
validate_startup_env()

# Configurer les logs avec le bon chemin
LOG_PATH = str(get_log_path("app.log"))

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | <cyan>{extra[type_log]}</cyan> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>|  "
    "<level>{message}</level>",
    level="INFO",
    colorize=True,
)
logger.add(
    LOG_PATH,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra[type_log]} |{name}: {function}: {line} |  {message}",
    level="INFO",
    rotation="10 MB",
    retention="1 month",
    compression="zip",
)

logger = logger.bind(type_log="MAIN")

# Utiliser le chemin de DB portable
DB_PATH = str(get_db_path())

# dtb.verif_repertoire_db(DB_PATH)
# dtb.verif_presence_db(DB_PATH)
# dtb.integrite_db(DB_PATH)
# bdb.backup_db(DB_PATH)
# exit()

#if bckp_pcloud.tester_presence_token_pcloud():
#    logger.info("Fichier de token pCloud trouvé, tentative de connexion...")
#    try:
#        pcloud_client = bckp_pcloud.connecter_pcloud_via_token()
#        logger.success("Connexion à pCloud réussie via token existant.")
#        #bckp_pcloud.sauvegarder_bdd_pcloud(pcloud_client, DB_PATH)
#        #bckp_pcloud.lister_fichiers_et_dossiers_pcloud(pcloud_client)
#        bckp_pcloud.telecharger_dernier_backup_pcloud(pcloud_client, DB_PATH)
#    except Exception as e:
#        logger.error(f"Échec de la connexion à pCloud via token : {e}")
#        logger.info("Tentative de connexion via OAuth2...")
#        try:
#            pcloud_client = bckp_pcloud.connecter_pcloud_via_oauth()
#            logger.success("Connexion à pCloud réussie via OAuth2.")
#        except Exception as e:
#            logger.critical(f"Échec de la connexion à pCloud via OAuth2 : {e}")
#            sys.exit(1)
#    age_token = pcloud_client.get_credentials_info()
#    if age_token.get('age_days', 0) >= 25:  # Refresh before 30 days
#        logger.warning("⚠️ Token is getting old, consider refreshing")
#        try:
#            logger.info("Tentative de rafraichissement du token pCloud...")
#            bckp_pcloud.connecter_pcloud_via_oauth()
#            logger.success("Rafraichissement du token pCloud réussi.")
#        except Exception as e:
#            logger.error(f"Échec du rafraîchissement du token pCloud : {e}")
#else:
#    logger.warning(
#        "Fichier de token pCloud introuvable, tentative de connexion via OAuth2..."
#    )
#    try:
#        pcloud_client = bckp_pcloud.connecter_pcloud_via_oauth()
#        logger.success("Connexion à pCloud réussie via OAuth2.")
#    except Exception as e:
#        logger.critical(f"Échec de la connexion à pCloud via OAuth2 : {e}")
#        sys.exit(1)
##bckp_pcloud.deconnecter_pcloud(sdk=pcloud_client)
#exit()
def main() -> None:
    """
    Point d'entrée principal de l'application de suivi des copropriétaires.

    Cette fonction orchestre l'ensemble du processus:

    1. **Récupération HTML** : Lance deux navigateurs Playwright en parallèle
       pour récupérer le HTML des charges et des lots depuis l'extranet.

    2. **Parsing** : Parse le HTML avec selectolax pour extraire:
       - La date de situation
       - Les données des charges (nom, code, débit, crédit)
       - Les lots associés à chaque copropriétaire

    3. **Validation** : Vérifie la cohérence des données (64 copropriétaires).

    4. **Persistance** : Sauvegarde les données en base SQLite après backup.

    5. **Interface** : Lance l'interface Streamlit pour visualisation.

    Options CLI:
        --no-headless: Mode navigateur visible (debug)
        --db-path: Surcharge du chemin base de données
        --no-serve: Désactive le lancement automatique de Streamlit
        --show-console: Affiche les données dans la console (rich)

    Returns:
        None

    Raises:
        SystemExit: En cas d'erreur de récupération HTML ou de validation.

    Note:
        Les credentials sont chargés depuis le fichier .env via env_loader.
    """
    # CLI: parser minimal pour debug / override
    import argparse

    parser = argparse.ArgumentParser(description="Suivi des copropriétaires")
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Lancer Playwright en mode visible (pour debugging)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Chemin vers la base de données SQLite",
    )
    # Streamlit sera lancé par défaut après le traitement. Utilisez
    # `--no-serve` pour **désactiver** le lancement automatique de l'UI.
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Ne PAS lancer l'interface Streamlit après le traitement",
    )
    parser.add_argument(
        "--serve-port", type=int, default=8501, help="Port pour Streamlit (si utilisé)"
    )
    parser.add_argument(
        "--serve-host",
        type=str,
        default="127.0.0.1",
        help="Host pour Streamlit (si utilisé)",
    )
    parser.add_argument(
        "--serve-python",
        type=str,
        default=None,
        help="Interpréteur Python à utiliser pour lancer Streamlit (optionnel)",
    )
    # Options Streamlit supplémentaires (contrôlent le comportement d'affichage)
    parser.add_argument(
        "--streamlit-no-browser",
        action="store_true",
        help="Ne pas ouvrir le navigateur pour Streamlit",
    )
    parser.add_argument(
        "--streamlit-no-console",
        action="store_true",
        help="Ne pas ouvrir la console Windows pour Streamlit",
    )
    parser.add_argument(
        "--streamlit-use-cmd-start",
        action="store_true",
        help="Sur Windows, utiliser `cmd /c start` pour forcer une fenêtre (voir limites)",
    )
    parser.add_argument(
        "--streamlit-log-file",
        type=str,
        default=None,
        help="Fichier pour rediriger stdout/stderr de Streamlit (ex: streamlit_stdout.log)",
    )
    parser.add_argument(
        "--show-console",
        action="store_true",
        help="Afficher les données des copropriétaires dans la console (rich)",
    )
    args = parser.parse_args()

    # override DB_PATH si fourni
    global DB_PATH
    if args.db_path:
        DB_PATH = args.db_path

    logger.info("Démarrage du script principal")

    options = PipelineRuntimeOptions(
        no_headless=args.no_headless,
        db_path=DB_PATH,
        no_serve=args.no_serve,
        show_console=args.show_console,
        serve_port=args.serve_port,
        serve_host=args.serve_host,
        serve_python=args.serve_python,
        streamlit_no_browser=args.streamlit_no_browser,
        streamlit_no_console=args.streamlit_no_console,
        streamlit_use_cmd_start=args.streamlit_use_cmd_start,
        streamlit_log_file=args.streamlit_log_file,
    )

    CptcoproPipeline().run(options)


if __name__ == "__main__":
    main()
