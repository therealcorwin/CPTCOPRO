"""Module commun pour le parsing avec Playwright.

Ce module gère :
- La connexion/authentification au site du syndic
- L'orchestration parallèle des récupérations HTML

Les navigations spécifiques sont déléguées à :
- Parsing_Charge_Copro : navigation pour les charges
- Parsing_Lots_Copro : navigation pour les lots
"""
from playwright.async_api import Page
from loguru import logger

from cptcopro.utils.env_loader import get_credentials
from cptcopro.utils.browser_launcher import launch_browser
import cptcopro.Parsing_Charge_Copro as pcc
import cptcopro.Parsing_Lots_Copro as pcl

logger.remove()
logger = logger.bind(type_log="PARSING_COMMUN")

# Variables globales pour le cache des credentials
_credentials_cache: tuple[str, str, str] | None = None


def _get_cached_credentials() -> tuple[str, str, str]:
    """Récupère les credentials de manière lazy avec cache."""
    global _credentials_cache
    if _credentials_cache is None:
        _credentials_cache = get_credentials()
        logger.info("Credentials chargés avec succès")
    return _credentials_cache


async def login_and_open_menu(page: Page, login: str, password: str, url: str) -> str | None:
    """
    Effectue la connexion au site et ouvre le menu principal.
    
    Args:
        page: Page Playwright déjà créée
        login: Identifiant de connexion
        password: Mot de passe
        url: URL du site
    
    Returns:
        None si succès, sinon un code d'erreur (str)
    """
    try:
        await page.goto(url, timeout=30000)
        logger.info(f"Accès à l'URL : {url}")
    except Exception as e:
        logger.error(f"Erreur lors de l'accès à l'URL : {e}")
        return "KO_GO_TO_URL"
    
    try:
        # Attendre que le champ login soit visible
        await page.wait_for_selector('input[name="A16"]', timeout=10000)
        await page.fill('input[name="A16"]', login)
        logger.info("Champ login rempli")
    except Exception as e:
        logger.error(f"Erreur lors du remplissage du champ login : {e}")
        return "KO_FILL_LOGIN"
    
    try:
        await page.fill('input[name="A17"]', password)
        logger.info("Champ mot de passe rempli")
    except Exception as e:
        logger.error(f"Erreur lors du remplissage du champ mot de passe : {e}")
        return "KO_FILL_PASSWORD"
    
    try:
        await page.click("span#z_A7_IMG")
        logger.info("Bouton Se connecter cliqué")
    except Exception as e:
        logger.error(f"Erreur lors du clic sur le bouton Se connecter : {e}")
        return "KO_CLICK_LOGIN"
    
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
        logger.info("Attente de la fin du chargement après connexion")
    except Exception as e:
        logger.error(f"Erreur lors de l'attente du chargement : {e}")
        return "KO_WAIT_FOR_LOAD"
    
    try:
        # Attendre que le bouton menu soit visible et cliquable
        await page.wait_for_selector("#z_M12_IMG", state="visible", timeout=15000)
        await page.click("#z_M12_IMG")
        logger.info("Bouton menu cliqué")
    except Exception as e:
        logger.error(f"Erreur lors du clic sur le bouton menu : {e}")
        return "KO_CLICK_MENU"
    
    return None  # Succès


# Les fonctions de navigation spécifiques sont maintenant dans leurs modules respectifs :
# - pcc.recup_html_from_page(page) pour les charges
# - pcl.recup_html_from_page(page) pour les lots


async def recup_html_charges(headless: bool, login: str, password: str, url: str) -> str:
    """
    Récupère le HTML des charges dans son propre navigateur.
    """
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await launch_browser(p, headless=headless)
        if browser is None:
            logger.error("Impossible d'ouvrir le navigateur pour les charges")
            return "KO_OPEN_BROWSER"
        
        try:
            page = await browser.new_page()
            logger.info("[Charges] Navigateur démarré, connexion en cours...")
            
            error = await login_and_open_menu(page, login, password, url)
            if error:
                logger.error(f"[Charges] Erreur login: {error}")
                await browser.close()
                return error
            
            logger.success("[Charges] Connexion réussie, navigation vers solde...")
            html = await pcc.recup_charges_coproprietaires(page)
            
            await browser.close()
            logger.info("[Charges] Navigateur fermé")
            return html
            
        except Exception as e:
            logger.error(f"[Charges] Exception: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return "KO_CHARGES_EXCEPTION"


async def recup_html_lots(headless: bool, login: str, password: str, url: str) -> str:
    """
    Récupère le HTML des lots dans son propre navigateur.
    """
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await launch_browser(p, headless=headless)
        if browser is None:
            logger.error("Impossible d'ouvrir le navigateur pour les lots")
            return "KO_OPEN_BROWSER"
        
        try:
            page = await browser.new_page()
            logger.info("[Lots] Navigateur démarré, connexion en cours...")
            
            error = await login_and_open_menu(page, login, password, url)
            if error:
                logger.error(f"[Lots] Erreur login: {error}")
                await browser.close()
                return error
            
            logger.success("[Lots] Connexion réussie, navigation vers liste...")
            html = await pcl.recup_lots_coproprietaires(page)
            
            await browser.close()
            logger.info("[Lots] Navigateur fermé")
            return html
            
        except Exception as e:
            logger.error(f"[Lots] Exception: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return "KO_LOTS_EXCEPTION"


async def recup_all_html_parallel(headless: bool = True) -> tuple[str, str]:
    """
    Récupère les deux HTML (charges et lots) en parallèle avec 2 navigateurs séparés.
    Chaque navigateur gère sa propre session, évitant les conflits de cookies.
    
    Args:
        headless: Si True, navigateurs invisibles. Si False, mode visible pour debug.
    
    Returns:
        Tuple (html_charges, html_lots). En cas d'erreur, les valeurs sont des codes KO_*.
    """
    import asyncio
    
    login, password, url = _get_cached_credentials()
    logger.info("Démarrage de la récupération parallèle avec 2 navigateurs séparés")
    
    async def _fetch_charges_delayed():
        """Lance les charges avec un léger délai pour éviter collision de login."""
        await asyncio.sleep(0.8)  # Décalage de 800ms pour éviter conflit serveur
        return await recup_html_charges(headless, login, password, url)
    
    # Lancer les deux récupérations en parallèle (lots d'abord, charges avec délai)
    results = await asyncio.gather(
        _fetch_charges_delayed(),
        recup_html_lots(headless, login, password, url),
        return_exceptions=True
    )
    
    # Gérer les résultats
    if isinstance(results[0], Exception):
        logger.error(f"Exception charges: {results[0]}")
        html_charges = "KO_CHARGES_EXCEPTION"
    else:
        html_charges = str(results[0])
        
    if isinstance(results[1], Exception):
        logger.error(f"Exception lots: {results[1]}")
        html_lots = "KO_LOTS_EXCEPTION"
    else:
        html_lots = str(results[1])
    
    logger.success("Récupération parallèle terminée")
    return html_charges, html_lots
