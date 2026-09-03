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
    --no-backup       Ne pas envoyer de backup sur pCloud après l'écriture
    --deco-pcloud     Se déconnecter de pCloud et supprimer le token local
    --show-console    Afficher les données dans la console (rich)
"""

import argparse
import asyncio
import atexit
import pathlib
import subprocess
import sys
import time
from typing import Any

from loguru import logger
from selectolax.parser import HTMLParser

import cptcopro.Database as dtb
import cptcopro.Database.Backup_DB_Pcloud as bckp_pcloud
import cptcopro.Parsing.Commun as pc
import cptcopro.Traitement.Charge_Copro as tp
import cptcopro.Traitement.Lots_Copro as tlc
import cptcopro.utils.streamlit_launcher as usl
from cptcopro.utils.env_loader import validate_startup_env
from cptcopro.utils.paths import get_db_path, get_log_path

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


def _parse_cli_args() -> argparse.Namespace:
    """Analyse les arguments de ligne de commande."""
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
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Ne pas envoyer de backup sur pCloud après l'écriture",
    )
    parser.add_argument(
        "--deco-pcloud",
        action="store_true",
        help="Se déconnecter de pCloud et supprimer le token local en fin d'exécution",
    )
    return parser.parse_args()


def _scrape_and_parse(
    no_headless: bool,
) -> tuple[list[Any] | None, list[Any] | None, str | None]:
    """Récupère et parse les données de charges et de lots."""
    logger.info("Récupération parallèle du HTML (charges + lots) en cours...")
    html_charge, html_copro = asyncio.run(pc.recup_all_html_parallel(headless=not no_headless))

    if not html_charge or html_charge.startswith("KO_"):
        logger.error(f"Erreur récupération HTML charges: {html_charge}")
        return None, None, None
    logger.success("HTML des charges des copropriétaires récupéré.")

    if not html_copro or html_copro.startswith("KO_"):
        logger.error(f"Erreur récupération HTML lots: {html_copro}")
        return None, None, None
    logger.success("HTML des lots des copropriétaires récupéré.")

    logger.info("Parsing des charges des copropriétaires en cours...")
    parser_charges = HTMLParser(html_charge)
    logger.success("Parsing des charges des copropriétaires terminé.")

    logger.info("Récupération de la date de suivi des copropriétaires en cours...")
    date_suivi_copro = tp.recuperer_date_situation_copro(parser_charges)
    if not date_suivi_copro:
        logger.error("Date de situation introuvable, arrêt du traitement.")
        return None, None, None
    logger.success(f"Date de situation des copropriétaires récupérée : {date_suivi_copro}")

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

    return data_charges, data_coproprietaires, date_suivi_copro


def _restore_db_from_pcloud_if_missing(db_path: str) -> bool:
    """Restaure la base de données locale depuis pCloud si elle est absente."""
    if dtb.verif_presence_db(db_path):
        return False

    logger.warning(f"Base locale absente ('{db_path}'). Tentative de restauration depuis pCloud...")
    pcloud_client = bckp_pcloud.tester_token_et_connecter_pcloud()
    try:
        restore_result = bckp_pcloud.telecharger_dernier_backup_pcloud(
            pcloud_client,
            local_db_name=pathlib.Path(db_path).name,
            overwrite=True,
        )
    except RuntimeError as exc:
        if "Aucun fichier de backup .sqlite" in str(exc):
            logger.warning("Aucun backup pCloud trouvé. Création d'une nouvelle base locale...")
            dtb.creer_base_db(db_path)
            return False
        raise

    restored_path = pathlib.Path(restore_result["local_path"])
    target_path = pathlib.Path(db_path)
    if restored_path.resolve() != target_path.resolve():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            target_path.unlink()
        restored_path.replace(target_path)
        logger.info(f"Base restaurée déplacée vers le chemin cible '{target_path}'.")
    return True


def _save_data_to_db(
    db_path: str, data_charges: list[Any], data_coproprietaires: list[Any]
) -> None:
    """Enregistre les données extraites en base SQLite et met à jour les alertes."""
    dtb.verif_repertoire_db(db_path)
    restored = _restore_db_from_pcloud_if_missing(db_path)
    dtb.integrite_db(db_path)
    dtb.backup_db(db_path)

    if restored:
        dtb.purger_alertes_pour_rebuild(db_path)
        logger.info("Alertes purgées après restore pCloud (recomputation via triggers).")

    try:
        dtb.enregistrer_coproprietaires(data_coproprietaires, db_path)
    except Exception as exc_copro:
        logger.error(f"Insertion copropriétaires échouée (lots invalides) : {exc_copro}")
        logger.warning("Les charges seront quand même sauvegardées pour cette période.")

    dtb.enregistrer_donnees_sqlite(data_charges, db_path)
    logger.info("Traitement terminé et données sauvegardées.")

    try:
        logger.info("Mise à jour de la table 'suivi_alertes'...")
        dtb.sauvegarder_nombre_alertes(db_path)
        logger.success("Table 'suivi_alertes' mise à jour.")
    except Exception as exc:
        logger.error(f"Erreur lors de la mise à jour de la table 'suivi_alertes' : {exc}")


def _handle_pcloud_sync(db_path: str, no_backup: bool, deco_pcloud: bool) -> None:
    """Gère la sauvegarde vers pCloud et la déconnexion optionnelle."""
    if no_backup:
        logger.info("Sauvegarde pCloud ignorée via l'option --no-backup.")
    else:
        try:
            logger.info("Sauvegarde pCloud de la base locale en cours...")
            pcloud_client = bckp_pcloud.tester_token_et_connecter_pcloud()
            bckp_pcloud.sauvegarder_bdd_pcloud(pcloud_client, pathlib.Path(db_path))
            logger.success("Sauvegarde pCloud terminée avec succès.")
        except Exception as exc:
            logger.error(f"Erreur lors de la sauvegarde pCloud : {exc}")

    if deco_pcloud:
        try:
            logger.info("Déconnexion pCloud demandée via --deco-pcloud...")
            bckp_pcloud.deconnecter_pcloud()
            logger.success("Déconnexion pCloud terminée et token local supprimé.")
        except Exception as exc:
            logger.error(f"Erreur lors de la déconnexion pCloud : {exc}")


def _launch_streamlit_service(args: argparse.Namespace) -> None:
    """Lance l'interface Streamlit et gère le cycle de vie du processus."""
    if args.no_serve:
        return

    proc = None
    try:
        if usl.is_pyinstaller_bundle():
            logger.info("Lancement de Streamlit in-process (mode PyInstaller)...")
            usl.start_streamlit_inprocess(
                app_path="src/cptcopro/Affichage_Stream.py",
                port=args.serve_port,
                host=args.serve_host,
                open_browser=not args.streamlit_no_browser,
            )
            logger.info("Streamlit terminé")
            return

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

        def _stop_proc(p: subprocess.Popen[bytes] = proc) -> None:
            usl.stop_streamlit(p)

        atexit.register(_stop_proc)
    except Exception as exc:
        logger.error(f"Impossible de lancer Streamlit : {exc}")

    if proc is not None:
        try:
            print("Application principale en cours... Ctrl-C pour interrompre.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Interruption reçue, fermeture en cours...")
        finally:
            usl.stop_streamlit(proc)


def main() -> None:
    """
    Point d'entrée principal de l'application de suivi des copropriétaires.

    Orchestre la collecte, le parsing, la persistance locale et distante,
    et enfin le lancement optionnel du dashboard de visualisation Streamlit.
    """
    args = _parse_cli_args()

    global DB_PATH
    if args.db_path:
        DB_PATH = args.db_path

    logger.info("Démarrage du script principal")
    data_charges, data_copros, date_suivi = _scrape_and_parse(args.no_headless)

    if not data_charges and not data_copros:
        logger.warning(
            "Aucune donnée extraite pour les charges et/ou les lots. Arrêt du traitement."
        )
        return

    if args.show_console:
        if data_charges and date_suivi:
            tp.afficher_etat_coproprietaire(data_charges, date_suivi)
        if data_copros:
            tlc.afficher_avec_rich(data_copros)

    try:
        if data_charges and data_copros:
            _save_data_to_db(DB_PATH, data_charges, data_copros)
    except Exception as exc:
        logger.error(f"Erreur lors des opérations BDD/backup : {exc}")
        raise RuntimeError(
            "ECHEC_CRITIQUE_COLLECTE_COPROPRIETAIRES: données lots invalides, base non écrasée."
        ) from exc

    _handle_pcloud_sync(DB_PATH, args.no_backup, args.deco_pcloud)
    _launch_streamlit_service(args)


if __name__ == "__main__":
    main()
