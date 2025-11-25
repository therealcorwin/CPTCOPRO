import asyncio
import sys
import os
from selectolax.parser import HTMLParser
import cptcopro.Parsing_Charge_Copro as pcc
import cptcopro.Traitement_Charge_Copro as tp
import cptcopro.Data_To_BDD as dtb
import cptcopro.Backup_DB as bdb
import cptcopro.Parsing_Lots_Copro as pcl
import cptcopro.Traitement_Lots_Copro as tlc
import cptcopro.Dedoublonnage as doublon
import cptcopro.utils.streamlit_launcher as usl
from loguru import logger
import time
import atexit


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
    "app.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra[type_log]} |{name}: {function}: {line} |  {message}",
    level="INFO",
    rotation="10 MB",
    retention="1 month",
    compression="zip",
)

logger = logger.bind(type_log="MAIN")

DB_PATH = os.path.join(os.path.dirname(__file__), "BDD", "test.sqlite")
"""
## Charger le contenu du fichier HTML
with open(
    "src\\cptcopro\\Solde_copro3.htm",
    "r",
    encoding="utf-8",
 ) as file:
    html_content = file.read()
"""
#dtb.verif_repertoire_db(DB_PATH)
#dtb.verif_presence_db(DB_PATH)
#dtb.integrite_db(DB_PATH)
#bdb.backup_db(DB_PATH)
#exit()

def main() -> None:
    """
    Point d'entrée principal : récupère le HTML, effectue le parsing,
    affiche les résultats et stocke les données en base.
    """
    # CLI: parser minimal pour debug / override
    import argparse

    parser = argparse.ArgumentParser(description="Suivi des copropriétaires")
    parser.add_argument("--no-headless", action="store_true", help="Lancer Playwright en mode visible (pour debugging)")
    parser.add_argument("--db-path", type=str, default=None, help="Chemin vers la base de données SQLite")
    # Streamlit sera lancé par défaut après le traitement. Utilisez
    # `--no-serve` pour **désactiver** le lancement automatique de l'UI.
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Ne PAS lancer l'interface Streamlit après le traitement",
    )
    parser.add_argument("--serve-port", type=int, default=8501, help="Port pour Streamlit (si utilisé)")
    parser.add_argument("--serve-host", type=str, default="127.0.0.1", help="Host pour Streamlit (si utilisé)")
    parser.add_argument(
        "--serve-python",
        type=str,
        default=None,
        help="Interpréteur Python à utiliser pour lancer Streamlit (optionnel)",
    )
    # Options Streamlit supplémentaires (contrôlent le comportement d'affichage)
    parser.add_argument("--streamlit-no-browser", action="store_true",
                        help="Ne pas ouvrir le navigateur pour Streamlit")
    parser.add_argument("--streamlit-no-console", action="store_true",
                        help="Ne pas ouvrir la console Windows pour Streamlit")
    parser.add_argument("--streamlit-use-cmd-start", action="store_true",
                        help="Sur Windows, utiliser `cmd /c start` pour forcer une fenêtre (voir limites)")
    parser.add_argument("--streamlit-log-file", type=str, default=None,
                        help="Fichier pour rediriger stdout/stderr de Streamlit (ex: streamlit_stdout.log)")
    args = parser.parse_args()

    # override DB_PATH si fourni
    global DB_PATH
    if args.db_path:
        DB_PATH = args.db_path


    logger.info("Démarrage du script principal")
    logger.info("Récupération du HTML contenant les charges des copropriétaires en cours...")
    html_charge = asyncio.run(pcc.recup_html_suivicopro(headless=not args.no_headless))
    if not html_charge:
        logger.error("Aucun HTML récupéré. Arrêt du traitement.")
        return
    logger.success("HTML des charges des copropriétaires récupéré.")
    
    logger.info("Parsing des charges des copropriétaires en cours...")
    parser_charges = HTMLParser(html_charge)
    logger.success("Parsing des charges des copropriétaires terminé.")
   
    logger.info("Récupération de la date de suivi des copropriétaires en cours...")
    date_suivi_copro = tp.recuperer_date_situation_copro(parser_charges)
    if not date_suivi_copro:
        logger.error("Date de situation introuvable, arrêt du traitement.")
        return
    logger.success(f"Date de situation des copropriétaires récupérée : {date_suivi_copro}")

    logger.info("Récupération des données des charges des copropriétaires en cours...")
    data_charges = tp.recuperer_situation_copro(parser_charges, date_suivi_copro)
    logger.success(f"Données des charges des copropriétaires récupérées : {len(data_charges)} entrées.")
    
    logger.info("Récupération du HTML contenant les lots des copropriétaires en cours...")
    html_copro = asyncio.run(pcl.recup_html_lotscopro(headless=not args.no_headless))
    if not html_copro:
        logger.error("Aucun HTML des lots récupéré. Arrêt du traitement.")
        return
    logger.success("HTML des lots des copropriétaires récupéré.")    
    
    logger.info("Parsing des lots des copropriétaires en cours...")
    lots_coproprietaires = tlc.extraire_lignes_brutes(html_copro)
    logger.success(f"{len(lots_coproprietaires)} lots de copropriétaires extraits.")
    
    logger.info("Consolidation des lots des copropriétaires en cours...")
    data_coproprietaires = tlc.consolider_proprietaires_lots(lots_coproprietaires)
    logger.success(f"{len(data_coproprietaires)} copropriétaires/groupes consolidés.")

    if not data_charges and not data_coproprietaires:
        logger.warning("Aucune donnée extraite pour les charges et/ou les lots. Arrêt du traitement.")
        return
    else:
        tp.afficher_etat_coproprietaire(data_charges, date_suivi_copro)
        tlc.afficher_avec_rich(data_coproprietaires)    
    try:
        # Ensure path type compatibility: modules expect a string path
        dtb.verif_repertoire_db(DB_PATH)
        dtb.verif_presence_db(DB_PATH)
        dtb.integrite_db(DB_PATH)
        bdb.backup_db(DB_PATH)
        dtb.enregistrer_donnees_sqlite(data_charges, DB_PATH)
        dtb.enregistrer_coproprietaires(data_coproprietaires, DB_PATH)
        logger.info("Traitement terminé et données sauvegardées.")
    except Exception as exc:
        logger.error(f"Erreur lors des opérations BDD/backup : {exc}")
    
    try:
        logger.info("Vérification des doublons dans la table 'charge'...")
        analyse = doublon.analyse_doublons(DB_PATH)
        if not analyse:
            logger.info("Aucun doublon détecté.")
        else:
            logger.info(f"Doublons détectés (ids à supprimer) : {len(analyse)}")
            doublon.rapport_doublon(DB_PATH, analyse)
            doublon.suppression_doublons(DB_PATH, analyse)
    except Exception as exc:
        logger.error(f"Erreur lors de la déduplication : {exc}")


    try:
        logger.info("Mise à jour de la table 'nombre_alertes'...")
        dtb.sauvegarder_nombre_alertes(DB_PATH)
        logger.success("Table 'nombre_alertes' mise à jour.")
    except Exception as exc:
        logger.error(f"Erreur lors de la mise à jour de la table 'nombre_alertes' : {exc}")
    
    # Par défaut, lancer Streamlit après le traitement, sauf si demandé sinon
    proc = None
    if not args.no_serve:
        try:
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

    try:
        # Placez ici le reste de votre logique main
        print("Application principale en cours... Ctrl-C pour interrompre.")
        while True:
            # exemple : simuler un travail principal
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interruption reçue, fermeture en cours...")
    finally:
        if proc is not None:
            usl.stop_streamlit(proc)

if __name__ == "__main__":
    main()
