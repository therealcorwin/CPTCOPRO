"""Point d'entrée principal de l'application CPTCOPRO.

Ce module orchestre :
- La récupération parallèle du HTML (charges et lots) via Playwright
- Le parsing des données avec selectolax
- La sauvegarde en base MariaDB
- Le lancement de l'interface Streamlit

Usage:
    python -m cptcopro.main [OPTIONS]

Options:
    --no-headless     Lance Playwright en mode visible (debug)
    --no-serve        Ne pas lancer Streamlit après le traitement
    --no-backup           Ne pas envoyer de backup sur pCloud après l'écriture
    --deco-pcloud         Se déconnecter de pCloud et supprimer le token local
    --show-console        Afficher les données dans la console (rich)
    --auto-relance-drafts Générer automatiquement les brouillons de relance pour les impayés
    --relance-imap        Déposer également les brouillons dans le dossier IMAP Drafts
"""

import argparse
import asyncio
import atexit
import pathlib
import subprocess
import sys
import time
from contextlib import suppress
from typing import Any, cast

from loguru import logger
from selectolax.parser import HTMLParser

# Valider toutes les variables d'environnement requises AVANT d'importer les
# modules applicatifs : certains d'entre eux (ex. Backup_DB_Pcloud) lisent le
# .env dès l'import et lèveraient sinon une erreur partielle (seulement leurs
# propres clés) qui masquerait les autres clés manquantes.
from cptcopro.utils.env_loader import validate_startup_env

validate_startup_env()

import cptcopro.Database as dtb
import cptcopro.Database.Backup_DB_Pcloud as bckp_pcloud
import cptcopro.Parsing.Commun as pc
import cptcopro.Traitement.Charge_Copro as tp
import cptcopro.Traitement.Lots_Copro as tlc
import cptcopro.utils.streamlit_launcher as usl
from cptcopro.utils.paths import get_log_path

dtb.verif_connexion_db()
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


def _parse_cli_args() -> argparse.Namespace:
    """Analyse les arguments de ligne de commande."""
    parser = argparse.ArgumentParser(description="Suivi des copropriétaires")
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Lancer Playwright en mode visible (pour debugging)",
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
    parser.add_argument(
        "--auto-relance-drafts",
        action="store_true",
        help="Générer automatiquement les brouillons de relance pour les impayés après l'écriture BDD",
    )
    parser.add_argument(
        "--relance-imap",
        action="store_true",
        help="Déposer également les brouillons générés dans le dossier IMAP Drafts (avec --auto-relance-drafts)",
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
    if not data_charges:
        logger.error("Erreur critique : Aucune charge de copropriétaire n'a été extraite !")
        return None, None, None
    logger.success(
        f"Données des charges des copropriétaires récupérées : {len(data_charges)} entrées."
    )

    logger.info("Parsing des lots des copropriétaires en cours...")
    lots_coproprietaires = tlc.extraire_lignes_brutes(html_copro)
    logger.success(f"{len(lots_coproprietaires)} lots de copropriétaires extraits.")

    logger.info("Consolidation des lots des copropriétaires en cours...")
    data_coproprietaires = tlc.consolider_proprietaires_lots(lots_coproprietaires)
    logger.success(f"{len(data_coproprietaires)} copropriétaires/groupes consolidés.")

    if len(data_coproprietaires) != dtb.NOMBRE_LOTS_ATTENDU:
        logger.error(
            f"Erreur critique : {len(data_coproprietaires)} copropriétaires consolidés au lieu de {dtb.NOMBRE_LOTS_ATTENDU} attendus !"
        )
        return None, None, None

    return data_charges, data_coproprietaires, date_suivi_copro


def _valider_donnees_avant_sauvegarde(
    data_charges: list[Any] | None,
    data_copros: list[Any] | None,
) -> None:
    """Valide l'intégrité et la complétude des données avant toute opération BDD.

    Règles strictes :
    1. Lots : obligatoires et décompte exact égal à NOMBRE_LOTS_ATTENDU (64).
    2. Charges : obligatoires et non vides après normalisation.

    Raises:
        IncoherenceLotsError: Si les lots sont absents ou != NOMBRE_LOTS_ATTENDU.
        CollecteChargesVideError: Si les charges sont absentes ou vides.
    """
    if not data_copros:
        logger.critical(
            f"SÉCURITÉ BDD : Lots absents ou vides (0 trouvé, {dtb.NOMBRE_LOTS_ATTENDU} attendus). Aucune écriture en base."
        )
        raise dtb.IncoherenceLotsError(
            f"Incohérence lots : 0 lot trouvé au lieu de {dtb.NOMBRE_LOTS_ATTENDU} attendus !"
        )

    if len(data_copros) != dtb.NOMBRE_LOTS_ATTENDU:
        logger.critical(
            f"SÉCURITÉ BDD : Nombre de lots incorrect : {len(data_copros)} trouvé(s), {dtb.NOMBRE_LOTS_ATTENDU} attendus. Aucune écriture en base."
        )
        raise dtb.IncoherenceLotsError(
            f"Incohérence lots : {len(data_copros)} lot(s) trouvé(s) au lieu de {dtb.NOMBRE_LOTS_ATTENDU} attendus !"
        )

    if not data_charges:
        logger.critical("SÉCURITÉ BDD : Aucune charge extraite. Aucune écriture en base.")
        raise dtb.CollecteChargesVideError("Échec collecte des charges : aucune donnée extraite.")

    dtb.valider_charges_presentes(data_charges)


def _restore_db_from_pcloud_if_missing() -> bool:
    """Restaure la base de données depuis pCloud si elle est absente dans MariaDB."""
    if dtb.verif_presence_db():
        return False

    logger.warning(
        "Base de données absente dans MariaDB. Tentative de restauration depuis pCloud..."
    )
    pcloud_client = bckp_pcloud.tester_token_et_connecter_pcloud()
    try:
        bckp_pcloud.telecharger_dernier_backup_pcloud(
            pcloud_client,
            overwrite=True,
        )
    except RuntimeError as exc:
        if "Aucun fichier de backup" in str(exc):
            logger.warning(
                "Aucun backup pCloud trouvé. Initialisation d'une nouvelle base MariaDB..."
            )
            dtb.creer_base_db()
            return False
        raise
    return True


def _save_data_to_db(
    data_charges: list[Any],
    data_coproprietaires: list[Any],
) -> str | None:
    """Enregistre les données extraites en base MariaDB et met à jour les alertes."""
    # Validation stricte en amont : bloque tout si anomalie
    _valider_donnees_avant_sauvegarde(data_charges, data_coproprietaires)

    restored = _restore_db_from_pcloud_if_missing()
    dtb.integrite_db()
    backup_file = dtb.backup_db()

    if restored:
        dtb.purger_alertes_pour_rebuild()
        logger.info("Alertes purgées après restore pCloud (recomputation via triggers).")

    # STRICT : Tout ou rien. Pas d'insertion partielle si l'un des deux échoue !
    dtb.enregistrer_coproprietaires(data_coproprietaires, nombre_attendu=dtb.NOMBRE_LOTS_ATTENDU)
    dtb.enregistrer_charges(data_charges)
    logger.info("Traitement terminé et données sauvegardées.")

    try:
        logger.info("Mise à jour de la table 'suivi_alertes'...")
        dtb.sauvegarder_nombre_alertes()
        logger.success("Table 'suivi_alertes' mise à jour.")
    except Exception as exc:
        logger.error(f"Erreur lors de la mise à jour de la table 'suivi_alertes' : {exc}")
        raise

    return cast(str | None, backup_file)


def _handle_pcloud_sync(backup_path: str | None, no_backup: bool, deco_pcloud: bool) -> None:
    """Gère la sauvegarde vers pCloud et la déconnexion optionnelle."""
    if no_backup:
        logger.info("Sauvegarde pCloud ignorée via l'option --no-backup.")
    elif backup_path:
        try:
            logger.info("Sauvegarde pCloud du dump local en cours...")
            pcloud_client = bckp_pcloud.tester_token_et_connecter_pcloud()
            bckp_pcloud.sauvegarder_bdd_pcloud(pcloud_client, pathlib.Path(backup_path))
            logger.success("Sauvegarde pCloud terminée avec succès.")
        except Exception as exc:
            logger.error(f"Erreur lors de la sauvegarde pCloud : {exc}")
    else:
        logger.info("Aucun backup local généré à synchroniser vers pCloud.")

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
            while proc.poll() is None:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            with suppress(Exception, KeyboardInterrupt):
                print("\nInterruption reçue, fermeture de Streamlit en cours...")
            with suppress(Exception, KeyboardInterrupt):
                usl.stop_streamlit(proc)


def main() -> None:
    """
    Point d'entrée principal de l'application de suivi des copropriétaires.

    Orchestre la collecte, le parsing, la persistance locale et distante,
    et enfin le lancement optionnel du dashboard de visualisation Streamlit.
    """
    args = _parse_cli_args()

    logger.info("Démarrage du script principal")
    data_charges, data_copros, date_suivi = _scrape_and_parse(args.no_headless)

    if not data_charges or not data_copros:
        lots_count = len(data_copros) if data_copros else 0
        charges_count = len(data_charges) if data_charges else 0
        logger.critical(
            f"ARRÊT CRITIQUE : Données incomplètes ou manquantes après extraction "
            f"(charges: {charges_count}, lots: {lots_count}/{dtb.NOMBRE_LOTS_ATTENDU}). "
            "Aucune modification de la base de données."
        )
        sys.exit(1)

    if args.show_console:
        if data_charges and date_suivi:
            tp.afficher_etat_coproprietaire(data_charges, date_suivi)
        if data_copros:
            tlc.afficher_avec_rich(data_copros)

    backup_file = None
    try:
        backup_file = _save_data_to_db(data_charges, data_copros)
    except Exception as exc:
        logger.critical(
            f"ÉCHEC CRITIQUE BDD / SAUVEGARDE : {exc}. Base non modifiée ou opération annulée."
        )
        sys.exit(1)

    if args.auto_relance_drafts:
        try:
            logger.info("Génération automatique des brouillons de relance demandée...")
            from cptcopro.utils.relance_mailer import generer_brouillons_relances

            relance_res = generer_brouillons_relances(deposer_imap=args.relance_imap)
            logger.success(
                f"Relances traitées : {relance_res['generes']} brouillon(s) généré(s), "
                f"{relance_res['deposes_imap']} déposé(s) sur IMAP, "
                f"{len(relance_res['erreurs'])} erreur(s)."
            )
        except Exception as exc_relance:
            logger.error(f"Erreur lors de la génération automatique des relances : {exc_relance}")

    _handle_pcloud_sync(backup_file, args.no_backup, args.deco_pcloud)
    _launch_streamlit_service(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        with suppress(Exception):
            print("\nArrêt demandé par l'utilisateur.")
        sys.exit(0)
