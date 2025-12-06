"""
Utilitaire pour lancer un navigateur Playwright avec fallback automatique.

Ordre de priorité : Edge → Chrome → Firefox
Utilise les navigateurs installés sur le système (pas les navigateurs bundlés Playwright).
"""

from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, Playwright
from loguru import logger

logger = logger.bind(type_log="BROWSER")
# Ordre de priorité des navigateurs
BROWSER_CHANNELS = [
    ("msedge", "chromium", "Microsoft Edge"),
    ("chrome", "chromium", "Google Chrome"),
    (None, "firefox", "Firefox"),  # Firefox n'a pas de channel, on utilise le browser type directement
]


async def launch_browser(playwright: Playwright, headless: bool = True) -> Browser | None:
    """
    Lance un navigateur en essayant plusieurs options dans l'ordre.
    
    Ordre de priorité:
    1. Microsoft Edge (préinstallé sur Windows)
    2. Google Chrome
    3. Firefox
    
    Args:
        playwright: Instance Playwright
        headless: Mode headless (True) ou visible (False)
        
    Returns:
        Browser ou None si aucun navigateur n'est disponible
    """
    
    for channel, browser_type, browser_name in BROWSER_CHANNELS:
        try:
            if browser_type == "chromium":
                browser = await playwright.chromium.launch(
                    headless=headless,
                    channel=channel
                )
            elif browser_type == "firefox":
                browser = await playwright.firefox.launch(
                    headless=headless
                )
            else:
                continue
                
            logger.success(f"Navigateur {browser_name} lancé avec succès (headless={headless})")
            return browser
            
        except Exception as e:
            logger.warning(f"{browser_name} non disponible: {e}")
            continue
    
    logger.error("Aucun navigateur disponible (Edge, Chrome, Firefox)")
    return None

@asynccontextmanager
async def launch_browser_with_context(headless: bool = True):
    """
    Context manager pour lancer un navigateur.
    
    Usage:
        async with launch_browser_with_context(headless=True) as browser:
            if browser:
                page = await browser.new_page()
                ...
    """
    async with async_playwright() as p:
        browser = await launch_browser(p, headless)
        try:
            yield browser
        finally:
            if browser:
                await browser.close()
