"""Module d'automatisation de l'authentification OAuth2 pCloud avec Playwright."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from loguru import logger
from playwright.async_api import Error as PlaywrightError, Page, Route, async_playwright

from cptcopro.utils.browser_launcher import launch_browser

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext

logger = logger.bind(type_log="PCLOUD_OAUTH")


def extraire_code_depuis_url(url: str) -> str | None:
    """Extrait la valeur du paramètre 'code' depuis une URL."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        codes = params.get("code")
        if codes and codes[0]:
            return codes[0].strip()
    except Exception as exc:
        logger.debug(f"Erreur extraction paramètre code depuis '{url}': {exc}")
    return None


async def _configurer_interception_callback(
    page: Page,
    redirect_uri: str,
    code_event: asyncio.Event,
    result_holder: dict[str, str | None],
) -> None:
    """Configure l'interception de la redirection callback pour extraire le code OAuth."""
    parsed_redirect = urlparse(redirect_uri)
    callback_path = parsed_redirect.path or "/callback"

    async def handle_route(route: Route) -> None:
        url = route.request.url
        logger.debug(f"Interception requête callback: {url}")
        code = extraire_code_depuis_url(url)
        if code:
            result_holder["code"] = code
            code_event.set()
            html_response = (
                "<!DOCTYPE html>"
                "<html><head><meta charset='utf-8'><title>Connexion pCloud</title>"
                "<style>body{font-family:sans-serif;text-align:center;padding-top:50px;background:#f8f9fa;}"
                ".card{display:inline-block;background:white;padding:30px 40px;border-radius:8px;"
                "box-shadow:0 2px 10px rgba(0,0,0,0.1);max-width:500px;}"
                "h2{color:#28a745;}p{color:#495057;font-size:16px;}</style></head>"
                "<body><div class='card'>"
                "<h2>✓ Authentification pCloud réussie !</h2>"
                "<p>Le code d'autorisation a été récupéré automatiquement.<br>"
                "Cette fenêtre va se fermer.</p>"
                "</div></body></html>"
            )
            try:
                await route.fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=html_response,
                )
            except Exception as e:
                logger.debug(f"Impossible de répondre à la route callback : {e}")
        else:
            try:
                await route.continue_()
            except Exception:
                pass

    async def handle_frame_navigated(frame) -> None:
        url = frame.url
        if callback_path in url or (parsed_redirect.netloc and parsed_redirect.netloc in url):
            code = extraire_code_depuis_url(url)
            if code:
                result_holder["code"] = code
                code_event.set()

    # Intercepter à la fois les requêtes réseau et les navigations de frame
    await page.route(f"**{callback_path}*", handle_route)
    page.on("framenavigated", lambda frame: asyncio.create_task(handle_frame_navigated(frame)))


async def _page_necessite_interaction_utilisateur(page: Page) -> bool:
    """Détecte si la page pCloud nécessite une action manuelle de l'utilisateur."""
    try:
        content = await page.content()
        content_lower = content.lower()

        # Marqueurs spécifiques pCloud OAuth
        marqueurs = [
            "connect cpt_copro to your account",
            "wants to have access to your pcloud account",
            "sign in with pcloud",
            "oauth2",
            "password",
            "autoriser",
            "connexion",
        ]
        for marqueur in marqueurs:
            if marqueur in content_lower:
                return True
    except Exception as exc:
        logger.debug(f"Erreur analyse contenu page: {exc}")
    return True


async def recuperer_code_oauth_playwright(
    auth_url: str,
    redirect_uri: str = "http://localhost:8000/callback",
    timeout_seconds: int = 180,
) -> str | None:
    """
    Récupère automatiquement le code OAuth pCloud via Playwright.

    1. Démarre en headless pour inspecter l'URL d'autorisation.
    2. Si une interaction utilisateur est requise (connexion/autorisation), bascule en mode visible.
    3. Intercepte la redirection vers la callback URI pour extraire le paramètre `code`.
    """
    logger.info("Tentative de récupération automatique du code OAuth pCloud via Playwright...")

    async with async_playwright() as p:
        # Étape 1 : Essai en mode Headless
        logger.info("Vérification initiale de la page OAuth (mode headless)...")
        browser: Browser | None = await launch_browser(p, headless=True)
        if not browser:
            logger.warning("Impossible de lancer le navigateur Playwright en headless.")
            return None

        result_holder: dict[str, str | None] = {"code": None}
        code_event = asyncio.Event()

        try:
            context: BrowserContext = await browser.new_context()
            page: Page = await context.new_page()
            await _configurer_interception_callback(page, redirect_uri, code_event, result_holder)

            try:
                await page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                logger.debug(f"Navigation headless terminée avec message: {exc}")

            if result_holder.get("code"):
                logger.success("Code d'autorisation pCloud récupéré immédiatement en headless.")
                await browser.close()
                return result_holder["code"]

            interaction_requise = await _page_necessite_interaction_utilisateur(page)
        finally:
            await browser.close()

        # Étape 2 : Si interaction requise, lancer en mode visible
        if interaction_requise:
            logger.info(
                "Authentification pCloud requise : ouverture du navigateur visible "
                "pour la connexion utilisateur..."
            )
            browser_visible = await launch_browser(p, headless=False)
            if not browser_visible:
                logger.warning("Impossible d'ouvrir le navigateur visible pour l'autorisation OAuth.")
                return None

            try:
                context_visible = await browser_visible.new_context()
                page_visible = await context_visible.new_page()
                await _configurer_interception_callback(
                    page_visible, redirect_uri, code_event, result_holder
                )

                try:
                    await page_visible.goto(auth_url, wait_until="domcontentloaded", timeout=45000)
                except Exception as exc:
                    logger.debug(f"Navigation visible initiée: {exc}")

                logger.info(
                    "Veuillez vous connecter et autoriser l'application dans la fenêtre de navigateur ouverte..."
                )

                try:
                    await asyncio.wait_for(code_event.wait(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Délai d'attente dépassé ({timeout_seconds}s) pour l'autorisation OAuth pCloud."
                    )
                    return None

                if result_holder.get("code"):
                    logger.success("Code d'autorisation pCloud intercepté avec succès !")
                    # Laisser le temps à l'utilisateur de voir la confirmation
                    await asyncio.sleep(1.5)
                    return result_holder["code"]

            except PlaywrightError as pe:
                logger.warning(f"Erreur Playwright pendant l'autorisation OAuth: {pe}")
            finally:
                await browser_visible.close()

    return result_holder.get("code")


def obtenir_code_oauth_automatique(
    auth_url: str,
    redirect_uri: str = "http://localhost:8000/callback",
    timeout_seconds: int = 180,
) -> str | None:
    """Wrapper synchrone pour exécuter la récupération automatique du code OAuth pCloud."""
    try:
        return asyncio.run(
            recuperer_code_oauth_playwright(
                auth_url=auth_url,
                redirect_uri=redirect_uri,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception as exc:
        logger.error(f"Échec de l'automatisation OAuth pCloud: {exc}")
        return None

