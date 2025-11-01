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
from loguru import logger


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
    level="DEBUG",
    rotation="10 MB",
    retention="1 month",
    compression="zip",
)

logger = logger.bind(type_log="MAIN")

DB_PATH = os.path.join(os.path.dirname(__file__), "BDD", "copropriete.sqlite")

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
    else:
        logger.success("HTML des charges des copropriétaires récupéré.")
    
    logger.info("Parsing des charges des copropriétaires en cours...")
    parser_charges = HTMLParser(html_charge)
    logger.success("Parsing des charges des copropriétaires terminé.")
   
    logger.info("Récupération de la date de suivi des copropriétaires en cours...")
    date_suivi_copro = tp.recuperer_date_situation_copro(parser_charges)
    if not date_suivi_copro:
        logger.error("Date de situation introuvable, arrêt du traitement.")
        return
    else:
        logger.success(f"Date de situation des copropriétaires récupérée : {date_suivi_copro}")

    logger.info("Récupération des données des charges des copropriétaires en cours...")
    data_charges = tp.recuperer_situation_copro(parser_charges, date_suivi_copro)
    logger.success(f"Données des charges des copropriétaires récupérées : {len(data_charges)} entrées.")
    
    logger.info("Récupération du HTML contenant les lots des copropriétaires en cours...")
    html_copro = asyncio.run(pcl.recup_html_lotscopro(headless=not args.no_headless))
    logger.success("HTML des lots des copropriétaires récupéré.")
    
    logger.info("Parsing des lots des copropriétaires en cours...")
    lots_coproprietaires = tlc.extraire_lignes_brutes(html_copro)
    logger.success(f"{len(lots_coproprietaires)} lots de copropriétaires extraits.")
    
    logger.info("Consolidation des lots des copropriétaires en cours...")
    data_coproprietaires = tlc.consolider_proprietaires_lots(lots_coproprietaires)
    logger.success(f"{len(data_coproprietaires)} copropriétaires/groupes consolidés.")

    if not data_charges and not data_coproprietaires:
        logger.warning("Aucune donnée extraite pour les charges et ou lots. Arrêt du traitement")
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
        #dtb.enregistrer_donnees_sqlite(data_charges, DB_PATH)
        dtb.enregistrer_coproprietaires(data_coproprietaires, DB_PATH)
        logger.info("Traitement terminé et données sauvegardées.")
    except Exception as exc:
        logger.error(f"Erreur lors des opérations BDD/backup : {exc}")


if __name__ == "__main__":
    main()
