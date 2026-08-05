"""High-level orchestrator for the CPTCOPRO end-to-end pipeline."""

from __future__ import annotations

from loguru import logger

from .models import PipelineReport, PipelineRuntimeOptions
from .stages import (
    collect_raw_html,
    parse_domain_data,
    persist_domain_data,
    render_console_if_requested,
    serve_ui,
    update_alert_tracking,
)

logger = logger.bind(type_log="PIPELINE")


class CptcoproPipeline:
    """Orchestrates full collect/parse/validate/persist/serve lifecycle."""

    def run(self, options: PipelineRuntimeOptions) -> PipelineReport:
        raw = collect_raw_html(options)
        parsed = parse_domain_data(raw, options)
        render_console_if_requested(parsed, options.show_console)
        persisted = persist_domain_data(parsed, options.db_path)
        update_alert_tracking(options.db_path)
        serve_ui(options)

        report = PipelineReport(parsed=parsed, persisted=persisted)
        logger.info(
            "Pipeline terminé: charges={}, copro={}, anomalies_lots={}",
            report.persisted.nb_charges,
            report.persisted.nb_coproprietaires,
            report.parsed.lots_anomalies,
        )
        return report
