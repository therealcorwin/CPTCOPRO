import asyncio
import sys
from selectolax.parser import HTMLParser
from pathlib import Path
import Parsing_Site_Syndic as pss
import Traitement_Parsing as tp
import Data_To_BDD as dtb
import Backup_DB as bdb
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

DB_PATH = Path(__file__).with_name("coproprietaires.sqlite")


def main() -> None:
    """
    Point d'entrée principal : récupère le HTML, effectue le parsing,
    affiche les résultats et stocke les données en base.
    """
    logger.info("Démarrage du script principal")
    html_content = asyncio.run(pss.recup_html_suivicopro())
    if not html_content:
        logger.error("Aucun HTML récupéré. Arrêt du traitement.")
        return

    parser = HTMLParser(html_content)
    date_suivi_copro, last_check = tp.recuperer_date_situation_copro(parser)
    if not date_suivi_copro:
        logger.error("Date de situation introuvable, arrêt du traitement.")
        return

    data = tp.recuperer_situation_copro(parser, date_suivi_copro, last_check)
    if not data:
        logger.warning("Aucune donnée extraite du tableau.")
    else:
        tp.afficher_etat_coproprietaire(data, date_suivi_copro)

    try:
        dtb.verif_presence_db(DB_PATH)
        bdb.backup_db(DB_PATH)
        dtb.enregistrer_donnees_sqlite(data, DB_PATH)
        logger.info("Traitement terminé et données sauvegardées.")
    except Exception as exc:
        logger.error(f"Erreur lors des opérations BDD/backup : {exc}")


if __name__ == "__main__":
    main()
