from cptcopro.pipeline import (
    CptcoproPipeline,
    ParsedPayload,
    PersistenceResult,
    PipelineRuntimeOptions,
)
from cptcopro.pipeline.errors import PersistenceError


def _build_options() -> PipelineRuntimeOptions:
    return PipelineRuntimeOptions(
        no_headless=True,
        db_path="dummy.sqlite",
        no_serve=True,
        show_console=False,
        serve_port=8501,
        serve_host="127.0.0.1",
        serve_python=None,
        streamlit_no_browser=True,
        streamlit_no_console=True,
        streamlit_use_cmd_start=False,
        streamlit_log_file=None,
    )


def test_orchestrator_runs_stages_in_order(monkeypatch):
    calls = []

    raw = object()
    parsed = ParsedPayload(
        date_suivi_copro="2026-08-05",
        data_charges=[],
        lots_lignes_brutes=[],
        data_coproprietaires=[],
        lots_anomalies=0,
    )
    persisted = PersistenceResult(nb_charges=0, nb_coproprietaires=0)

    def fake_collect(options):
        calls.append("collect")
        assert options.no_headless is True
        return raw

    def fake_parse(in_raw, options):
        calls.append("parse")
        assert in_raw is raw
        assert options.db_path == "dummy.sqlite"
        return parsed

    def fake_render(in_parsed, show_console):
        calls.append("render")
        assert in_parsed is parsed
        assert show_console is False

    def fake_persist(in_parsed, db_path):
        calls.append("persist")
        assert in_parsed is parsed
        assert db_path == "dummy.sqlite"
        return persisted

    def fake_update(db_path):
        calls.append("update")
        assert db_path == "dummy.sqlite"

    def fake_serve(options):
        calls.append("serve")
        assert options.no_serve is True

    monkeypatch.setattr("cptcopro.pipeline.orchestrator.collect_raw_html", fake_collect)
    monkeypatch.setattr("cptcopro.pipeline.orchestrator.parse_domain_data", fake_parse)
    monkeypatch.setattr("cptcopro.pipeline.orchestrator.render_console_if_requested", fake_render)
    monkeypatch.setattr("cptcopro.pipeline.orchestrator.persist_domain_data", fake_persist)
    monkeypatch.setattr("cptcopro.pipeline.orchestrator.update_alert_tracking", fake_update)
    monkeypatch.setattr("cptcopro.pipeline.orchestrator.serve_ui", fake_serve)

    report = CptcoproPipeline().run(_build_options())

    assert calls == ["collect", "parse", "render", "persist", "update", "serve"]
    assert report.parsed is parsed
    assert report.persisted is persisted


def test_orchestrator_propagates_stage_error(monkeypatch):
    def fake_collect(_options):
        return object()

    def fake_parse(_raw, _options):
        return object()

    def fake_render(_parsed, _show_console):
        return None

    def fake_persist(_parsed, _db_path):
        raise PersistenceError("persist", "forced failure")

    monkeypatch.setattr("cptcopro.pipeline.orchestrator.collect_raw_html", fake_collect)
    monkeypatch.setattr("cptcopro.pipeline.orchestrator.parse_domain_data", fake_parse)
    monkeypatch.setattr("cptcopro.pipeline.orchestrator.render_console_if_requested", fake_render)
    monkeypatch.setattr("cptcopro.pipeline.orchestrator.persist_domain_data", fake_persist)

    try:
        CptcoproPipeline().run(_build_options())
        assert False, "Expected PersistenceError"
    except PersistenceError as exc:
        assert exc.stage == "persist"
