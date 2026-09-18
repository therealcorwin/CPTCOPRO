"""Verifie que .env.example documente bien toutes les variables requises au demarrage."""

from __future__ import annotations

from pathlib import Path

from cptcopro.utils.env_loader import REQUIRED_STARTUP_ENV_VARS

ENV_EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "src" / "cptcopro" / ".env.example"


def _parse_env_example_keys() -> set[str]:
    keys = set()
    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_env_example_documents_all_required_startup_vars():
    """Une variable requise au demarrage mais absente de .env.example serait une
    regression silencieuse (l'utilisateur ne saurait pas qu'il faut la definir)."""
    documented = _parse_env_example_keys()
    missing = set(REQUIRED_STARTUP_ENV_VARS) - documented
    assert not missing, f"Variables requises absentes de .env.example: {sorted(missing)}"

