import asyncio
import sys
import os
from selectolax.parser import HTMLParser
import cptcopro.Parsing_Charge_Copro as pss
import cptcopro.Traitement_Parsing as tp
import cptcopro.Data_To_BDD as dtb
import cptcopro.Backup_DB as bdb
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

DB_PATH = str(os.path.join(os.getcwd(), "BDD", "copropriete.sqlite"))
"""
## Charger le contenu du fichier HTML
with open(
    "src\\cptcopro\\Solde_copro3.htm",
    "r",
    encoding="utf-8",
 ) as file:
    html_content = file.read()
"""
dtb.integrite_db(DB_PATH)


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
    html_content = asyncio.run(pss.recup_html_suivicopro(headless=not args.no_headless))
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
        # Ensure path type compatibility: modules expect a string path
        dtb.verif_repertoire_db(DB_PATH)
        dtb.verif_presence_db(DB_PATH)
        bdb.backup_db(DB_PATH)
        dtb.enregistrer_donnees_sqlite(data, DB_PATH)
        logger.info("Traitement terminé et données sauvegardées.")
    except Exception as exc:
        logger.error(f"Erreur lors des opérations BDD/backup : {exc}")


if __name__ == "__main__":
    main()
