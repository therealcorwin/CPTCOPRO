import sqlite3
from pathlib import Path

import pytest

from cptcopro.Database import integrite_db, enregistrer_coproprietaires


def read_all_coproprietaires(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT nom_proprietaire, code_proprietaire, num_apt, type_apt FROM coproprietaires ORDER BY code_proprietaire")
    rows = cur.fetchall()
    conn.close()
    return rows


def test_enregistrer_coproprietaires_happy_path(tmp_path: Path):
    db_file = tmp_path / "test_copro.db"
    db_path = str(db_file)

    # Ensure DB and tables are created
    res = integrite_db(db_path)
    assert res.get("coproprietaires", True) in (True, False)

    # enregistrer_coproprietaires accepte maintenant des tuples (nom, code, num_apt, type_apt)
    # enregistrer_coproprietaires accepte des dicts {proprietaire, code, num_apt, type_apt}
    rows = [
        {"proprietaire": "Alice Dupont", "code": "A001", "num_apt": "101", "type_apt": "Appartement"},
        {"proprietaire": "Bob Martin", "code": "B002", "num_apt": "102", "type_apt": "Local commercial"},
    ]

    inserted = enregistrer_coproprietaires(rows, db_path)
    # la fonction actuelle ne retourne rien (None). On vérifie donc l'état de la BDD ci-dessous.
    assert inserted is None

    db_rows = read_all_coproprietaires(db_path)
    assert len(db_rows) == 2
    assert db_rows[0][1] == "A001"
    assert db_rows[1][1] == "B002"


def test_enregistrer_coproprietaires_empty_rows(tmp_path: Path):
    db_file = tmp_path / "test_copro_empty.db"
    db_path = str(db_file)

    # Create DB and tables
    integrite_db(db_path)

    inserted = enregistrer_coproprietaires([], db_path)
    # la fonction actuelle retourne None lorsqu'elle ne fait rien
    assert inserted is None

    # Table should exist but be empty
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='coproprietaires';")
    exists = cur.fetchone()[0]
    assert exists == 1
    cur.execute("SELECT COUNT(*) FROM coproprietaires;")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 0


def test_enregistrer_coproprietaires_without_integrite_db_raises(tmp_path: Path):
    db_file = tmp_path / "test_copro_no_init.db"
    db_path = str(db_file)

    # Do NOT call integrite_db(db_path) - table won't exist
    with pytest.raises(sqlite3.OperationalError):
        # Should raise because table coproprietaires does not exist
        enregistrer_coproprietaires([{"proprietaire": "X", "code": "X001", "num_apt": "1", "type_apt": "Apt"}], db_path)
