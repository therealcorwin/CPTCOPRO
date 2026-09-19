"""Tests de syntaxe et de compilation des pages Streamlit unifiées."""

from __future__ import annotations

import ast

from cptcopro.utils.paths import get_project_root_dir


def test_eight_pages_exist_and_compile():
    """Vérifie que les 8 pages Streamlit sont présentes et compilent sans SyntaxError."""
    pages_dir = get_project_root_dir() / "src" / "cptcopro" / "Pages"
    page_files = sorted(pages_dir.glob("*.py"))

    assert len(page_files) == 8, f"8 pages attendues, trouvé {len(page_files)}"

    for pf in page_files:
        code = pf.read_text(encoding="utf-8")
        # Validation AST
        tree = ast.parse(code, filename=str(pf))
        assert tree is not None
        # Validation compilation bytecode
        compiled = compile(code, str(pf), "exec")
        assert compiled is not None


def test_affichage_stream_compiles():
    """Vérifie que le point d'entrée Affichage_Stream.py compile sans SyntaxError."""
    app_file = get_project_root_dir() / "src" / "cptcopro" / "Affichage_Stream.py"
    assert app_file.exists()
    code = app_file.read_text(encoding="utf-8")
    tree = ast.parse(code, filename=str(app_file))
    assert tree is not None
    compiled = compile(code, str(app_file), "exec")
    assert compiled is not None


def test_verifier_statut_token_hotmail_signature():
    """Vérifie que verifier_statut_token_hotmail retourne bien un tuple (bool, str)."""
    from cptcopro.utils.hotmail_oauth import verifier_statut_token_hotmail

    res = verifier_statut_token_hotmail()
    assert isinstance(res, tuple)
    assert len(res) == 2
    assert isinstance(res[0], bool)
    assert isinstance(res[1], str)


def test_relance_due_date_formatting():
    """Vérifie que les colonnes de dates de relances sont bien formatées au format français (JJ/MM/AAAA)."""
    import datetime

    import pandas as pd

    def _format_date_col(val: object) -> str:
        if val is None or pd.isna(val) or val == "":
            return "-"
        if hasattr(val, "strftime"):
            return val.strftime("%d/%m/%Y")
        try:
            dt = pd.to_datetime(val)
            if pd.isna(dt):
                return "-"
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return str(val)

    # Test avec objet datetime.date
    d = datetime.date(2026, 9, 18)
    assert _format_date_col(d) == "18/09/2026"
    assert "1789689600000" not in _format_date_col(d)

    # Test avec None / vide
    assert _format_date_col(None) == "-"
    assert _format_date_col("") == "-"


def test_drafts_selection_and_masking():
    """Vérifie que le filtrage booléen des sélections de brouillons est immunisé contre les NA/None."""
    import pandas as pd

    df = pd.DataFrame({
        "S": [True, None, False, True],
        "ID": [101, 102, 103, 104],
        "nom": ["A", "B", "C", "D"],
    })

    # Test avec (df["S"] == True)
    mask = df["S"] == True  # noqa: E712
    selected = df[mask]
    assert len(selected) == 2
    assert selected["ID"].tolist() == [101, 104]

    # Test synchronisation sélection globale
    selected_ids = {101, 102, 103, 104}
    df["selected"] = df["ID"].astype(int).isin(selected_ids)
    assert df["selected"].all()


def test_relance_template_argument_aliases():
    """Vérifie que create_relance_template et update_relance_template acceptent les arguments canoniques et leurs alias."""
    import inspect

    from cptcopro.Database.Relance_Templates import (
        create_relance_template,
        update_relance_template,
    )

    create_params = inspect.signature(create_relance_template).parameters
    assert "subject_template" in create_params
    assert "subject" in create_params
    assert "body_template" in create_params
    assert "body" in create_params
    assert "tone_instruction" in create_params
    assert "prompt_instructions" in create_params

    update_params = inspect.signature(update_relance_template).parameters
    assert "subject_template" in update_params
    assert "subject" in update_params
    assert "body_template" in update_params
    assert "body" in update_params
    assert "tone_instruction" in update_params
    assert "prompt_instructions" in update_params


def test_tester_connexion_mistral_rate_limit_429(monkeypatch):
    """Vérifie que le statut HTTP 429 (Rate Limit) renvoie un message explicite en français."""
    import io
    import urllib.error
    import urllib.request

    from cptcopro.utils.relance_mailer import tester_connexion_mistral

    def mock_urlopen(req, timeout=15):
        fp = io.BytesIO(b'{"object":"error","message":"Rate limit exceeded","code":"1300"}')
        raise urllib.error.HTTPError(
            url="https://api.mistral.ai/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=fp,
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    ok, msg = tester_connexion_mistral(api_key="fake_key_429")
    assert ok is False
    assert "Limite de requêtes atteinte" in msg
    assert "HTTP 429" in msg
    assert "Rate limit exceeded" in msg






