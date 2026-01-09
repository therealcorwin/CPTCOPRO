"""Module commun pour le parsing avec Playwright.

Ce module gère :
- La connexion/authentification au site du syndic
- L'orchestration parallèle des récupérations HTML

Les navigations spécifiques sont déléguées à :
- Parsing.Charge_Copro : navigation pour les charges
- Parsing.Lots_Copro : navigation pour les lots
"""

from playwright.async_api import Page, async_playwright
from loguru import logger

from cptcopro.utils.env_loader import get_credentials
from cptcopro.utils.browser_launcher import launch_browser
from . import Charge_Copro as pcc
from . import Lots_Copro as pcl
from .constants import (
    ERROR_GO_TO_URL,
    ERROR_FILL_LOGIN,
    ERROR_FILL_PASSWORD,
    ERROR_CLICK_LOGIN,
    ERROR_WAIT_FOR_LOAD,
    ERROR_CLICK_MENU,
    ERROR_OPEN_BROWSER,
    TIMEOUT_URL_ACCESS,
    TIMEOUT_ELEMENT_WAIT,
    TIMEOUT_MENU_WAIT,
    TIMEOUT_PAGE_LOAD,
    DELAY_RETRY_URL,
    DELAY_RETRY_MENU,
    DELAY_PARALLEL_LOGIN,
    MAX_RETRY_URL,
    MAX_RETRY_MENU,
)

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


async def login_and_open_menu(
    page: Page, login: str, password: str, url: str
) -> str | None:
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
        # Premier accès avec retry - le serveur peut être lent à "se réveiller"
        for attempt in range(MAX_RETRY_URL):
            try:
                await page.goto(url, timeout=TIMEOUT_URL_ACCESS)
                logger.info("Accès à l'URL réussi")
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning(
                        f"Premier accès URL lent, nouvelle tentative... ({e})"
                    )
                    await page.wait_for_timeout(DELAY_RETRY_URL)
                    # On laisse la boucle faire un nouveau page.goto
                else:
                    raise
    except Exception as e:
        logger.error(f"Erreur lors de l'accès à l'URL : {e}")
        return ERROR_GO_TO_URL
    try:
        # Attendre que le champ login soit visible
        await page.wait_for_selector('input[name="A16"]', timeout=TIMEOUT_ELEMENT_WAIT)
        await page.fill('input[name="A16"]', login)
        logger.info("Champ login rempli")
    except Exception as e:
        logger.error(f"Erreur lors du remplissage du champ login : {e}")
        return ERROR_FILL_LOGIN

    try:
        await page.fill('input[name="A17"]', password)
        logger.info("Champ mot de passe rempli")
    except Exception as e:
        logger.error(f"Erreur lors du remplissage du champ mot de passe : {e}")
        return ERROR_FILL_PASSWORD

    try:
        await page.click("span#z_A7_IMG")
        logger.info("Bouton Se connecter cliqué")
    except Exception as e:
        logger.error(f"Erreur lors du clic sur le bouton Se connecter : {e}")
        return ERROR_CLICK_LOGIN

    try:
        # Attendre que le DOM soit chargé puis que le réseau soit inactif
        await page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)
        await page.wait_for_load_state("networkidle", timeout=TIMEOUT_PAGE_LOAD)
        logger.info("Attente de la fin du chargement après connexion")
    except Exception as e:
        logger.error(f"Erreur lors de l'attente du chargement : {e}")
        return ERROR_WAIT_FOR_LOAD

    try:
        # Attendre que le bouton menu soit visible et cliquable
        # Retry avec rechargement de page en cas d'échec (serveur lent au premier lancement)
        for attempt in range(MAX_RETRY_MENU):
            try:
                await page.wait_for_selector(
                    "#z_M12_IMG", state="visible", timeout=TIMEOUT_MENU_WAIT
                )
                await page.click("#z_M12_IMG")
                logger.info("Bouton menu cliqué")
                break
            except Exception:
                if attempt < MAX_RETRY_MENU - 1:
                    logger.warning(
                        f"Menu non visible, tentative {attempt + 2}/{MAX_RETRY_MENU} avec rechargement..."
                    )
                    # Recharger la page et re-tenter la connexion complète
                    await page.wait_for_timeout(DELAY_RETRY_MENU)
                    try:
                        await page.reload(timeout=TIMEOUT_PAGE_LOAD)
                        await page.wait_for_load_state(
                            "networkidle", timeout=TIMEOUT_PAGE_LOAD
                        )
                    except Exception as reload_err:
                        logger.warning(
                            f"Rechargement échoué: {reload_err}, on continue..."
                        )
                else:
                    raise
    except Exception as e:
        logger.error(f"Erreur lors du clic sur le bouton menu : {e}")
        return ERROR_CLICK_MENU

    return None  # Succès


# Les fonctions de navigation spécifiques sont maintenant dans leurs modules respectifs :
# - pcc.recup_charges_coproprietaires(page) pour les charges
# - pcl.recup_lots_coproprietaires(page) pour les lots


async def _recup_html_generic(
    headless: bool,
    login: str,
    password: str,
    url: str,
    section_name: str,
    fetch_func,
) -> str:
    """
    Fonction générique pour récupérer le HTML d'une section dans son propre navigateur.

    Args:
        headless: Si True, navigateur invisible.
        login: Identifiant de connexion.
        password: Mot de passe.
        url: URL du site.
        section_name: Nom de la section pour les logs (ex: "Charges", "Lots").
        fetch_func: Fonction async à appeler pour récupérer le HTML (prend une Page en paramètre).

    Returns:
        Contenu HTML ou code d'erreur (str commençant par 'KO_').
    """
    async with async_playwright() as p:
        browser = await launch_browser(p, headless=headless)
        if browser is None:
            logger.error(f"Impossible d'ouvrir le navigateur pour {section_name}")
            return ERROR_OPEN_BROWSER

        try:
            page = await browser.new_page()
            logger.info(f"[{section_name}] Navigateur démarré, connexion en cours...")

            error = await login_and_open_menu(page, login, password, url)
            if error:
                logger.error(f"[{section_name}] Erreur login: {error}")
                await browser.close()
                return error

            logger.success(
                f"[{section_name}] Connexion réussie, navigation en cours..."
            )
            html = await fetch_func(page)

            await browser.close()
            logger.info(f"[{section_name}] Navigateur fermé")
            return html

        except Exception as e:
            logger.error(f"[{section_name}] Exception: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return f"KO_{section_name.upper()}_EXCEPTION"


async def recup_html_charges(
    headless: bool, login: str, password: str, url: str
) -> str:
    """Récupère le HTML des charges dans son propre navigateur."""
    return await _recup_html_generic(
        headless,
        login,
        password,
        url,
        section_name="Charges",
        fetch_func=pcc.recup_charges_coproprietaires,
    )


async def recup_html_lots(headless: bool, login: str, password: str, url: str) -> str:
    """Récupère le HTML des lots dans son propre navigateur."""
    return await _recup_html_generic(
        headless,
        login,
        password,
        url,
        section_name="Lots",
        fetch_func=pcl.recup_lots_coproprietaires,
    )


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
        """Lance les charges avec un délai pour éviter collision de login."""
        # Attendre que les lots soient probablement connectés avant de démarrer
        await asyncio.sleep(DELAY_PARALLEL_LOGIN)
        return await recup_html_charges(headless, login, password, url)

    # Lancer les deux récupérations en parallèle (lots d'abord, charges avec délai)
    results = await asyncio.gather(
        _fetch_charges_delayed(),
        recup_html_lots(headless, login, password, url),
        return_exceptions=True,
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
