"""Composable stages for CPTCOPRO pipeline orchestration."""

from __future__ import annotations

import asyncio
import time

from loguru import logger
from selectolax.parser import HTMLParser

import cptcopro.Database as dtb
import cptcopro.Parsing.Commun as pc
import cptcopro.Traitement.Charge_Copro as tp
import cptcopro.Traitement.Lots_Copro as tlc
import cptcopro.utils.streamlit_launcher as usl

from .errors import HtmlCollectionError, ParsingError, PersistenceError, ServingError
from .models import ParsedPayload, PersistenceResult, PipelineRuntimeOptions, RawHtmlPayload

logger = logger.bind(type_log="PIPELINE")


def collect_raw_html(options: PipelineRuntimeOptions) -> RawHtmlPayload:
    """Stage 1: collect charges/lots HTML in parallel."""
    logger.info("Stage collect_html: récupération parallèle HTML (charges + lots).")
    html_charge, html_lots = asyncio.run(
        pc.recup_all_html_parallel(headless=not options.no_headless)
    )

    if not html_charge or html_charge.startswith("KO_"):
        raise HtmlCollectionError(
            "collect_html",
            f"Erreur récupération HTML charges: {html_charge}",
        )
    if not html_lots or html_lots.startswith("KO_"):
        raise HtmlCollectionError(
            "collect_html",
            f"Erreur récupération HTML lots: {html_lots}",
        )

    logger.success("Stage collect_html: collecte HTML terminée.")
    return RawHtmlPayload(html_charges=html_charge, html_lots=html_lots)


def parse_domain_data(raw: RawHtmlPayload, options: PipelineRuntimeOptions) -> ParsedPayload:
    """Stage 2-4: parse charges/lots and stabilize lots collection quality."""
    logger.info("Stage parse_charges: parsing charges en cours.")
    parser_charges = HTMLParser(raw.html_charges)

    date_suivi = tp.recuperer_date_situation_copro(parser_charges)
    if not date_suivi:
        raise ParsingError("parse_charges", "Date de situation introuvable.")

    data_charges = tp.recuperer_situation_copro(parser_charges, date_suivi)

    logger.info("Stage parse_lots: collecte consolidée des lots en cours.")
    lots_lignes, data_copro = tlc.collecter_lots_coproprietaires_fiable(
        raw.html_lots,
        retry_html_provider=lambda: asyncio.run(
            pc.recup_html_lots_only(headless=not options.no_headless)
        ),
    )
    lots_anomalies = tlc.compter_lots_types_vides(data_copro)

    if not data_charges and not data_copro:
        raise ParsingError(
            "parse_domain",
            "Aucune donnée extraite pour les charges et les lots.",
        )

    logger.success(
        "Stage parse_domain: charges={} lots_lignes={} copro={} anomalies_lots={}",
        len(data_charges),
        len(lots_lignes),
        len(data_copro),
        lots_anomalies,
    )
    return ParsedPayload(
        date_suivi_copro=date_suivi,
        data_charges=data_charges,
        lots_lignes_brutes=lots_lignes,
        data_coproprietaires=data_copro,
        lots_anomalies=lots_anomalies,
    )


def persist_domain_data(parsed: ParsedPayload, db_path: str) -> PersistenceResult:
    """Stage 5-6: guardrails and atomic persistence."""
    logger.info("Stage persist: vérification BDD, backup et écriture en cours.")
    try:
        dtb.verif_repertoire_db(db_path)
        if not dtb.verif_presence_db(db_path):
            dtb.creer_base_db(db_path)
        dtb.integrite_db(db_path)
        dtb.backup_db(db_path)
        dtb.enregistrer_donnees_sqlite(parsed.data_charges, db_path)
        dtb.enregistrer_coproprietaires(parsed.data_coproprietaires, db_path)
    except Exception as exc:
        raise PersistenceError(
            "persist",
            (
                "ECHEC_CRITIQUE_COLLECTE_COPROPRIETAIRES: "
                "données lots invalides, base non écrasée. "
                f"Cause: {exc}"
            ),
        ) from exc

    logger.success("Stage persist: données sauvegardées en BDD.")
    return PersistenceResult(
        nb_charges=len(parsed.data_charges),
        nb_coproprietaires=len(parsed.data_coproprietaires),
    )


def update_alert_tracking(db_path: str) -> None:
    """Stage 7: best-effort alert tracking update."""
    logger.info("Stage post_persist: mise à jour de suivi_alertes.")
    try:
        dtb.sauvegarder_nombre_alertes(db_path)
        logger.success("Stage post_persist: suivi_alertes mis à jour.")
    except Exception as exc:
        logger.error("Stage post_persist: mise à jour suivi_alertes en échec: {}", exc)


def render_console_if_requested(parsed: ParsedPayload, show_console: bool) -> None:
    """Optional human-readable console rendering stage."""
    if not show_console:
        return
    tp.afficher_etat_coproprietaire(parsed.data_charges, parsed.date_suivi_copro)
    tlc.afficher_avec_rich(parsed.data_coproprietaires)


def serve_ui(options: PipelineRuntimeOptions) -> None:
    """Stage 8: launch Streamlit UI and manage process lifecycle."""
    if options.no_serve:
        logger.info("Stage serve_ui: désactivé (--no-serve).")
        return

    try:
        if usl.is_pyinstaller_bundle():
            logger.info("Stage serve_ui: lancement Streamlit in-process (PyInstaller).")
            usl.start_streamlit_inprocess(
                app_path="src/cptcopro/Affichage_Stream.py",
                port=options.serve_port,
                host=options.serve_host,
                open_browser=not options.streamlit_no_browser,
            )
            logger.info("Stage serve_ui: Streamlit terminé.")
            return

        logger.info("Stage serve_ui: lancement Streamlit en subprocess.")
        proc = usl.start_streamlit(
            app_path="src/cptcopro/Affichage_Stream.py",
            python_executable=options.serve_python,
            port=options.serve_port,
            host=options.serve_host,
            show_console=not options.streamlit_no_console,
            open_browser=not options.streamlit_no_browser,
            use_cmd_start=options.streamlit_use_cmd_start,
            log_file=options.streamlit_log_file,
        )
        logger.info("Stage serve_ui: Streamlit lancé (pid={}).", proc.pid)
        try:
            print("Application principale en cours... Ctrl-C pour interrompre.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Interruption reçue, fermeture en cours...")
        finally:
            usl.stop_streamlit(proc)
    except Exception as exc:
        raise ServingError("serve_ui", f"Impossible de lancer Streamlit: {exc}") from exc
