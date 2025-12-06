import sys
from playwright.async_api import async_playwright
from loguru import logger

# Import lazy des credentials - seront chargés à l'utilisation
from cptcopro.utils.env_loader import get_credentials
from cptcopro.utils.browser_launcher import launch_browser

logger.remove()
logger = logger.bind(type_log="PARSING")

# Variables globales pour le cache des credentials
_credentials_cache: tuple[str, str, str] | None = None


def _get_cached_credentials() -> tuple[str, str, str]:
    """Récupère les credentials de manière lazy avec cache."""
    global _credentials_cache
    if _credentials_cache is None:
        _credentials_cache = get_credentials()
        logger.info("Credentials chargés avec succès")
    return _credentials_cache

logger.info("Module Parsing_Charge_Copro chargé")


async def recup_html_suivicopro(headless: bool = True) -> str:
    """
    Récupère le HTML via Playwright.

    Paramètres:
    - headless (bool): Si False lance le navigateur en mode visible (utile pour debug).
    """
    # Charger les credentials au moment de l'exécution
    login_site_copro, password_site_copro, url_site_copro = _get_cached_credentials()
    logger.info("Debut de la récupération du HTML via Playwright")
    
    async with async_playwright() as p:
        browser = await launch_browser(p, headless=headless)
        if browser is None:
            return "KO_OPEN_BROWSER"

        try:
            page = await browser.new_page()
            logger.info("Nouvelle page ouverte")
        except Exception as e:
            logger.error(f"Erreur lors de l'ouverture d'une nouvelle page : {e}")
            await browser.close()
            return "KO_NEW_PAGE"
        try:
            await page.goto(url_site_copro, timeout=30000)
            logger.info(f"Accès à l'URL : {url_site_copro}")
        except Exception as e:
            logger.error(f"Erreur lors de l'accès à l'URL : {e}")
            await browser.close()
            return "KO_GO_TO_URL"
        try:
            await page.fill('input[name="A16"]', login_site_copro)
            logger.info("Champ login rempli")
        except Exception as e:
            logger.error(f"Erreur lors du remplissage du champ login : {e}")
            return "KO_FILL_LOGIN"
        try:
            await page.fill('input[name="A17"]', password_site_copro)
            logger.info("Champ mot de passe rempli")
        except Exception as e:
            logger.error(f"Erreur lors du remplissage du champ mot de passe : {e}")
            return "KO_FILL_PASSWORD"
        try:
            await page.click("span#z_A7_IMG")
            logger.info("Bouton Se connecter cliqué")
        except Exception as e:
            logger.error(f"Erreur lors du clic sur le bouton Se connecter : {e}")
            await browser.close()
            return "KO_CLICK_LOGIN"
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
            logger.info("Attente de la fin du chargement après connexion")
        except Exception as e:
            logger.error(f"Erreur lors de l'attente du chargement : {e}")
            await browser.close()
            return "KO_WAIT_FOR_LOAD"
        try:
            await page.click("#z_M12_IMG")
            logger.info("Bouton menu cliqué")
        except Exception as e:
            logger.error(f"Erreur lors du clic sur le bouton menu : {e}")
            await browser.close()
            return "KO_CLICK_MENU"
        try:
            await page.click("a#A3")
            logger.info("Lien Afficher le solde des copropriétaires cliqué")
        except Exception as e:
            logger.error(f"Erreur lors du clic sur le lien solde copropriétaires : {e}")
            await browser.close()
            return "KO_CLICK_SOLDE_COPRO"
        try:
            await page.wait_for_load_state("networkidle")
            logger.info("Attente de la fin du chargement après affichage du solde")
        except Exception as e:
            logger.error(f"Erreur lors de l'attente du chargement final : {e}")
            await browser.close()
            return "KO_WAIT_FOR_FINAL_LOAD"
        try:
            html_content = await page.content()  # Récupère le HTML de la page courante
            logger.info("HTML de la page récupéré")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du HTML : {e}")
            await browser.close()
            return "KO_GET_HTML"

        try:
            await browser.close()
            logger.info("Navigateur fermé")
        except Exception as e:
            logger.error(f"Erreur lors de la fermeture du navigateur : {e}")
            return "KO_CLOSE_BROWSER"

        return html_content  # Retourne le contenu HTML pour vérification
