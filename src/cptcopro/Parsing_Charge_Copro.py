"""Module de parsing pour les charges des copropriétaires.

Ce module contient la logique de navigation spécifique pour récupérer
le HTML des charges depuis le site du syndic.
La connexion et l'orchestration sont gérées par Parsing_Common.
"""
from playwright.async_api import Page
from loguru import logger

logger.remove()
logger = logger.bind(type_log="PARSING_CHARGES")


async def recup_charges_coproprietaires(page: Page) -> str:
    """
    Navigation spécifique pour récupérer le HTML des charges.
    La page doit être déjà connectée et le menu ouvert.
    
    Args:
        page: Page Playwright avec menu ouvert
    
    Returns:
        Contenu HTML ou code d'erreur (str commençant par 'KO_')
    """
    try:
        await page.click("a#A3")
        logger.info("Lien Afficher le solde des copropriétaires cliqué")
    except Exception as e:
        logger.error(f"Erreur lors du clic sur le lien solde copropriétaires : {e}")
        return "KO_CLICK_SOLDE_COPRO"
    
    try:
        await page.wait_for_load_state("networkidle")
        logger.info("Attente de la fin du chargement après affichage du solde")
    except Exception as e:
        logger.error(f"Erreur lors de l'attente du chargement final : {e}")
        return "KO_WAIT_FOR_FINAL_LOAD"
    
    try:
        html_content = await page.content()
        logger.info("HTML des charges récupéré")
        return html_content
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du HTML : {e}")
        return "KO_GET_HTML"
