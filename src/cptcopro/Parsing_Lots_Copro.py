"""Module de parsing pour les lots des copropriétaires.

Ce module contient la logique de navigation spécifique pour récupérer
le HTML des lots depuis le site du syndic.
La connexion et l'orchestration sont gérées par Parsing_Common.
"""
from playwright.async_api import Page
from loguru import logger

logger.remove()
logger = logger.bind(type_log="PARSING_LOTS")


async def recup_lots_coproprietaires(page: Page) -> str:
    """
    Navigation spécifique pour récupérer le HTML des lots.
    La page doit être déjà connectée et le menu ouvert.
    
    Args:
        page: Page Playwright avec menu ouvert
    
    Returns:
        Contenu HTML ou code d'erreur (str commençant par 'KO_')
    """
    try:
        await page.click("#A9")
        logger.info("Lien Afficher la liste des copropriétaires cliqué")
    except Exception as e:
        logger.error(f"Erreur lors du clic sur le lien liste copropriétaires : {e}")
        return "KO_CLICK_LISTE_COPRO"
    
    try:
        await page.wait_for_selector("#z_A1_IMG", state="visible", timeout=10000)
        await page.click("#z_A1_IMG", timeout=10000)
        logger.info("Lien Afficher la liste des copropriétaires dépliée cliqué")
    except Exception as e:
        logger.error(f"Erreur lors du clic sur le lien liste dépliée : {e}")
        return "KO_CLICK_LISTE_COPRO_EXPANDED"
    
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
        logger.info("Attente de la fin du chargement après affichage de la liste")
    except Exception as e:
        logger.error(f"Erreur lors de l'attente du chargement final : {e}")
        return "KO_WAIT_FOR_FINAL_LOAD"
    
    try:
        html_content = await page.content()
        logger.info("HTML des lots récupéré")
        return html_content
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du HTML : {e}")
        return "KO_GET_HTML"