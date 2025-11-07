import sqlite3
from pathlib import Path
from cptcopro.Data_To_BDD import integrite_db


def test_vw_charge_coproprietaires_exists_and_returns_columns(tmp_path: Path):
    db_file = tmp_path / "test_view.db"
    db_path = str(db_file)

    # create DB and ensure schema (integrite_db creates the view)
    integrite_db(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Insert a coproprietaire
    cur.execute(
        "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt) VALUES (?, ?, ?, ?)",
        ("Dupont", "D001", "1", "3p"),
    )
    # Insert a charge pointing to that code
    cur.execute(
        "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
        ("D001", "Dupont", 100.0, 0.0, "2025-11-06"),
    )
    conn.commit()

    # Query the view
    cur.execute("SELECT code_proprietaire, nom_proprietaire, debit, credit, date, num_apt, type_apt FROM vw_charge_coproprietaires")
    rows = cur.fetchall()
    conn.close()

    assert len(rows) >= 1
    # verify expected columns/values for the last inserted row
    last = rows[-1]
    # SELECT: code_proprietaire(0), nom_proprietaire(1), debit(2), credit(3), date(4), num_apt(5), type_apt(6)
    assert last[0] == "D001"
    assert last[1] == "Dupont"
    assert last[5] == "1"
    assert last[6] == "3p"
