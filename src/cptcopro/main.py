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

import asyncio
import sys
from selectolax.parser import HTMLParser
import cptcopro.Parsing.Commun as pc
import cptcopro.Traitement.Charge_Copro as tp
import cptcopro.Traitement.Lots_Copro as tlc
import cptcopro.Database as dtb
import cptcopro.utils.streamlit_launcher as usl
from cptcopro.utils.paths import get_db_path, get_log_path, init_env
from loguru import logger
import time
import atexit

# Charger les variables d'environnement avant toute utilisation
init_env()

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
"""
## Charger le contenu du fichier HTML
with open(
    "src\\cptcopro\\Solde_copro3.htm",
    "r",
    encoding="utf-8",
 ) as file:
    html_content = file.read()
"""
# dtb.verif_repertoire_db(DB_PATH)
# dtb.verif_presence_db(DB_PATH)
# dtb.integrite_db(DB_PATH)
# bdb.backup_db(DB_PATH)
# exit()


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

    # Récupération parallèle des deux HTML (charges et lots)
    logger.info("Récupération parallèle du HTML (charges + lots) en cours...")
    html_charge, html_copro = asyncio.run(
        pc.recup_all_html_parallel(headless=not args.no_headless)
    )

    if not html_charge or html_charge.startswith("KO_"):
        logger.error(f"Erreur récupération HTML charges: {html_charge}")
        return
    logger.success("HTML des charges des copropriétaires récupéré.")

    if not html_copro or html_copro.startswith("KO_"):
        logger.error(f"Erreur récupération HTML lots: {html_copro}")
        return
    logger.success("HTML des lots des copropriétaires récupéré.")

    logger.info("Parsing des charges des copropriétaires en cours...")
    parser_charges = HTMLParser(html_charge)
    logger.success("Parsing des charges des copropriétaires terminé.")

    logger.info("Récupération de la date de suivi des copropriétaires en cours...")
    date_suivi_copro = tp.recuperer_date_situation_copro(parser_charges)
    if not date_suivi_copro:
        logger.error("Date de situation introuvable, arrêt du traitement.")
        return
    logger.success(
        f"Date de situation des copropriétaires récupérée : {date_suivi_copro}"
    )

    logger.info("Récupération des données des charges des copropriétaires en cours...")
    data_charges = tp.recuperer_situation_copro(parser_charges, date_suivi_copro)
    logger.success(
        f"Données des charges des copropriétaires récupérées : {len(data_charges)} entrées."
    )

    logger.info("Parsing des lots des copropriétaires en cours...")
    lots_coproprietaires = tlc.extraire_lignes_brutes(html_copro)
    logger.success(f"{len(lots_coproprietaires)} lots de copropriétaires extraits.")

    logger.info("Consolidation des lots des copropriétaires en cours...")
    data_coproprietaires = tlc.consolider_proprietaires_lots(lots_coproprietaires)
    logger.success(f"{len(data_coproprietaires)} copropriétaires/groupes consolidés.")

    if not data_charges and not data_coproprietaires:
        logger.warning(
            "Aucune donnée extraite pour les charges et/ou les lots. Arrêt du traitement."
        )
        return
    elif args.show_console:
        tp.afficher_etat_coproprietaire(data_charges, date_suivi_copro)
        tlc.afficher_avec_rich(data_coproprietaires)
    try:
        # Ensure path type compatibility: modules expect a string path
        dtb.verif_repertoire_db(DB_PATH)
        dtb.verif_presence_db(DB_PATH)
        dtb.integrite_db(DB_PATH)
        dtb.backup_db(DB_PATH)
        dtb.enregistrer_donnees_sqlite(data_charges, DB_PATH)
        dtb.enregistrer_coproprietaires(data_coproprietaires, DB_PATH)
        logger.info("Traitement terminé et données sauvegardées.")
    except Exception as exc:
        logger.error(f"Erreur lors des opérations BDD/backup : {exc}")

    # Note: Le dédoublonnage n'est plus nécessaire grâce à l'index UNIQUE
    # et INSERT OR REPLACE dans enregistrer_donnees_sqlite()

    try:
        logger.info("Mise à jour de la table 'suivi_alertes'...")
        dtb.sauvegarder_nombre_alertes(DB_PATH)
        logger.success("Table 'suivi_alertes' mise à jour.")
    except Exception as exc:
        logger.error(
            f"Erreur lors de la mise à jour de la table 'suivi_alertes' : {exc}"
        )

    # Par défaut, lancer Streamlit après le traitement, sauf si demandé sinon
    proc = None
    if not args.no_serve:
        try:
            # Check if running from PyInstaller bundle
            if usl.is_pyinstaller_bundle():
                logger.info("Lancement de Streamlit in-process (mode PyInstaller)...")
                # start_streamlit_inprocess is BLOCKING - it runs Streamlit in the main thread
                # This is required to avoid "signal only works in main thread" error
                # The function only returns when Streamlit exits
                usl.start_streamlit_inprocess(
                    app_path="src/cptcopro/Affichage_Stream.py",
                    port=args.serve_port,
                    host=args.serve_host,
                    open_browser=not args.streamlit_no_browser,
                )
                # If we get here, Streamlit has exited
                logger.info("Streamlit terminé")
                return  # Exit the application
            else:
                logger.info("Lancement de Streamlit via utils.streamlit_launcher...")
                proc = usl.start_streamlit(
                    app_path="src/cptcopro/Affichage_Stream.py",
                    python_executable=args.serve_python,
                    port=args.serve_port,
                    host=args.serve_host,
                    show_console=not args.streamlit_no_console,
                    open_browser=not args.streamlit_no_browser,
                    use_cmd_start=args.streamlit_use_cmd_start,
                    log_file=args.streamlit_log_file,
                )
                logger.info(f"Streamlit lancé (pid={proc.pid})")
                # garantir arrêt propre même si main lève une exception
                atexit.register(lambda p=proc: usl.stop_streamlit(p))
        except Exception as exc:
            logger.error(f"Impossible de lancer Streamlit : {exc}")

    # This code only runs when NOT in PyInstaller bundle (subprocess mode)
    if proc is not None:
        try:
            print("Application principale en cours... Ctrl-C pour interrompre.")
            while True:
                # exemple : simuler un travail principal
                time.sleep(1)
        except KeyboardInterrupt:
            print("Interruption reçue, fermeture en cours...")
        finally:
            usl.stop_streamlit(proc)


if __name__ == "__main__":
    main()
