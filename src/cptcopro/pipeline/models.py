"""Typed payloads and runtime options for the CPTCOPRO pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PipelineRuntimeOptions:
    """Runtime flags passed from CLI to the orchestration pipeline."""

    no_headless: bool
    db_path: str
    no_serve: bool
    show_console: bool
    serve_port: int
    serve_host: str
    serve_python: str | None
    streamlit_no_browser: bool
    streamlit_no_console: bool
    streamlit_use_cmd_start: bool
    streamlit_log_file: str | None


@dataclass(slots=True)
class RawHtmlPayload:
    """Raw HTML content collected from remote extranet."""

    html_charges: str
    html_lots: str


@dataclass(slots=True)
class ParsedPayload:
    """Domain data parsed from raw HTML."""

    date_suivi_copro: str
    data_charges: list
    lots_lignes_brutes: list[tuple[str, str]]
    data_coproprietaires: list[dict]
    lots_anomalies: int


@dataclass(slots=True)
class PersistenceResult:
    """Summary of persisted rows in SQLite."""

    nb_charges: int
    nb_coproprietaires: int


@dataclass(slots=True)
class PipelineReport:
    """End-to-end report used for final logging and diagnostics."""

    parsed: ParsedPayload
    persisted: PersistenceResult
