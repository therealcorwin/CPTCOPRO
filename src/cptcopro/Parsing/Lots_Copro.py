"""Module de parsing pour les lots des copropriétaires.

Ce module contient la logique de navigation spécifique pour récupérer
le HTML des lots depuis le site du syndic.
La connexion et l'orchestration sont gérées par Parsing.Commun.
"""

from loguru import logger
from playwright.async_api import Page

from .constants import TIMEOUT_PAGE_LOAD

logger.remove()
logger = logger.bind(type_log="PARSING_LOTS")


MIN_EXPECTED_LOTS_NODES = 100
MIN_EXPECTED_LOT_NODES = 120  # chaque copropriétaire a au moins 1 lot, souvent 2-3
STABILITY_SAMPLES = 3
STABILITY_INTERVAL_MS = 500
MAX_RETRY_LOTS_EXPANSION = 2  # tentatives de re-clic si la Phase 2 ne se charge pas


async def _mesurer_completude_lots(page: Page) -> dict[str, int]:
    """Mesure des indicateurs simples de complétude sur la liste des lots."""
    total_nodes = await page.locator("[id^='A17_']").count()
    lot_nodes = await page.locator("[id^='A17_']").filter(has_text="Lot").count()
    proprietaires_nodes = await page.locator("[id^='A17_']").evaluate_all(
        r"""
        (elements) => elements
          .map((e) => (e.textContent || '').trim())
          .filter((text) => /\(\d+[A-Za-z]?\)\s*$/.test(text))
          .length
        """
    )
    return {
        "total_nodes": int(total_nodes),
        "lot_nodes": int(lot_nodes),
        "proprietaires_nodes": int(proprietaires_nodes),
    }


async def _attendre_liste_lots_complete(page: Page) -> tuple[bool, dict[str, int]]:
    """Attend une liste lots stable et suffisamment riche pour un parsing fiable."""
    historique_totaux: list[int] = []
    max_iterations = max(1, TIMEOUT_PAGE_LOAD // STABILITY_INTERVAL_MS)
    dernieres_mesures: dict[str, int] = {
        "total_nodes": 0,
        "lot_nodes": 0,
        "proprietaires_nodes": 0,
    }

    # Phase 2 du chargement (rendu JS des lots) est purement client-side :
    # networkidle ne l'attend pas. On utilise wait_for_function pour détecter
    # dès que suffisamment de lot_nodes apparaissent, sans polling actif.
    try:
        await page.wait_for_function(
            f"() => document.querySelectorAll(\"[id^='A17_']\").length >= {MIN_EXPECTED_LOTS_NODES + MIN_EXPECTED_LOT_NODES}",
            timeout=TIMEOUT_PAGE_LOAD,
        )
    except Exception as e:
        logger.debug("wait_for_function lots: {} (fallback vers polling)", e)

    for _ in range(max_iterations):
        dernieres_mesures = await _mesurer_completude_lots(page)
        historique_totaux.append(dernieres_mesures["total_nodes"])
        if len(historique_totaux) > STABILITY_SAMPLES:
            historique_totaux.pop(0)

        stable = len(historique_totaux) == STABILITY_SAMPLES and len(set(historique_totaux)) == 1
        assez_riche = (
            dernieres_mesures["total_nodes"] >= MIN_EXPECTED_LOTS_NODES
            and dernieres_mesures["lot_nodes"] >= MIN_EXPECTED_LOT_NODES
        )
        if stable and assez_riche:
            logger.info(
                "Diagnostic lots OK: DOM stable et complet (total_nodes={}, lot_nodes={}, proprietaires_nodes={})",
                dernieres_mesures["total_nodes"],
                dernieres_mesures["lot_nodes"],
                dernieres_mesures["proprietaires_nodes"],
            )
            return True, dernieres_mesures

        await page.wait_for_timeout(STABILITY_INTERVAL_MS)

    logger.warning(
        "Diagnostic lots KO: DOM non stabilise ou incomplet apres attente (total_nodes={}, lot_nodes={}, proprietaires_nodes={}, min_total_nodes={})",
        dernieres_mesures["total_nodes"],
        dernieres_mesures["lot_nodes"],
        dernieres_mesures["proprietaires_nodes"],
        MIN_EXPECTED_LOTS_NODES,
    )
    return False, dernieres_mesures


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
        await page.wait_for_load_state("networkidle", timeout=TIMEOUT_PAGE_LOAD)
        logger.info("Attente de la fin du chargement après affichage de la liste")
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
        ok_collecte, mesures = await _attendre_liste_lots_complete(page)
        if not ok_collecte:
            # Phase 2 (rendu JS des lots) n'a pas abouti — ré-cliquer pour la déclencher.
            for attempt in range(1, MAX_RETRY_LOTS_EXPANSION + 1):
                logger.warning(
                    "Lots incomplets (lot_nodes={}) — re-clic #z_A1_IMG (tentative {}/{})",
                    mesures["lot_nodes"],
                    attempt,
                    MAX_RETRY_LOTS_EXPANSION,
                )
                try:
                    await page.click("#z_A1_IMG", timeout=10000)
                    await page.wait_for_load_state("networkidle", timeout=TIMEOUT_PAGE_LOAD)
                except Exception as e_retry:
                    logger.warning("Re-clic #z_A1_IMG échoué: {}", e_retry)
                ok_collecte, mesures = await _attendre_liste_lots_complete(page)
                if ok_collecte:
                    break
        if not ok_collecte:
            logger.error(
                "Collecte lots interrompue après {} tentatives: contenu partiel (total_nodes={}, lot_nodes={}, proprietaires_nodes={})",
                MAX_RETRY_LOTS_EXPANSION + 1,
                mesures["total_nodes"],
                mesures["lot_nodes"],
                mesures["proprietaires_nodes"],
            )
            return "KO_LOTS_INCOMPLETS"
    except Exception as e:
        logger.error(f"Erreur lors du diagnostic de complétude des lots : {e}")
        return "KO_LOTS_DIAGNOSTIC"

    try:
        html_content = await page.content()
        logger.info("HTML des lots récupéré")
        return html_content
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du HTML : {e}")
        return "KO_GET_HTML"
