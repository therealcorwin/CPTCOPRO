"""Module de parsing pour les charges des copropriétaires.

Ce module contient la logique de navigation spécifique pour récupérer
le HTML des charges depuis le site du syndic.
La connexion et l'orchestration sont gérées par Parsing.Commun.
"""

from loguru import logger
from playwright.async_api import Page

from .constants import TIMEOUT_PAGE_LOAD

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
        # `networkidle` peut rester bloqué selon le site (requêtes de fond persistantes).
        # On applique un timeout explicite puis on bascule sur un état plus tolérant.
        await page.wait_for_load_state("networkidle", timeout=TIMEOUT_PAGE_LOAD)
        logger.info("Attente de la fin du chargement après affichage du solde")
    except Exception as e:
        logger.warning(
            "networkidle non atteint dans le délai, fallback domcontentloaded: {}",
            e,
        )
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)
            logger.info("Fallback domcontentloaded atteint")
        except Exception as e2:
            logger.error(f"Erreur lors de l'attente du chargement final : {e2}")
            return "KO_WAIT_FOR_FINAL_LOAD"

    try:
        await page.wait_for_selector("table#A1_TB tr, table#ctzA1 tr", timeout=TIMEOUT_PAGE_LOAD)
        logger.info("Tableau des charges détecté dans le DOM")
    except Exception as e:
        logger.warning(f"Sélecteur de tableau non détecté dans le délai : {e}")

    try:
        html_content = await page.content()
        logger.info("HTML des charges récupéré")
        return html_content
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du HTML : {e}")
        return "KO_GET_HTML"
