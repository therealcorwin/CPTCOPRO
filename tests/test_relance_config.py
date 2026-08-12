"""Tests des fonctionnalites de relance (config, destinataires, brouillons)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cptcopro import Database as dbmod


def setup_db(path: Path) -> str:
    dbmod.integrite_db(str(path))
    return str(path)


def test_relance_tables_created(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_schema.db")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        for table_name in ["relance_config", "relance_destinataire", "relance_draft"]:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            assert cur.fetchone() is not None, f"Table {table_name} manquante"
    finally:
        conn.close()


def test_due_frequency_logic(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_due.db")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Copro + alerte active
        cur.execute(
            "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt) VALUES (?, ?, ?, ?)",
            ("Dupont", "D001", "1", "3p"),
        )
        cur.execute(
            """
            INSERT INTO alertes_debit_eleve (
                id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, date_origin,
                last_detection, first_detection, occurence
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_DATE, CURRENT_DATE, ?)
            """,
            (1, "Dupont", "D001", 3000.0, "3p", "2026-01-01", 1),
        )
        conn.commit()
    finally:
        conn.close()

    dbmod.update_relance_config(db_path, frequency_days=14)

    # Sans historique -> due
    rows = dbmod.list_relances_due(db_path)
    assert len(rows) == 1
    assert rows[0]["due"] == 1

    # Brouillon recent -> non due
    dbmod.save_relance_draft(
        db_path,
        code_proprietaire="D001",
        nom_proprietaire="Dupont",
        debit=3000.0,
        email_to="dupont@example.com",
        subject="Relance",
        body="Corps",
        llm_provider="mistral",
        llm_model="mistral-small-latest",
        status="draft_local",
    )
    rows_after = dbmod.list_relances_due(db_path)
    assert len(rows_after) == 1
    assert rows_after[0]["due"] == 0


def test_destinataire_upsert_and_fetch(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_destinataire.db")

    dbmod.upsert_relance_destinataire(db_path, "D777", "copro777@example.com", "Mme Test")
    dbmod.upsert_relance_destinataire(db_path, "D777", "copro777bis@example.com", "Mme Test")

    rows = dbmod.get_relance_destinataires(db_path)
    assert len(rows) == 1
    assert rows[0]["code_proprietaire"] == "D777"
    assert rows[0]["email_to"] == "copro777bis@example.com"
