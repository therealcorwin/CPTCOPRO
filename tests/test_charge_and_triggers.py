import sqlite3
from pathlib import Path

from cptcopro.Database import integrite_db, enregistrer_donnees_sqlite


def fetch_all(table: str, db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    conn.close()
    return rows


def test_enregistrer_donnees_sqlite_happy_path(tmp_path: Path):
    db_file = tmp_path / "test_charge.db"
    db_path = str(db_file)

    # Ensure DB and tables exist
    integrite_db(db_path)

    # Prepare data: function expects data[3:] to be the rows, so include 3 headers
    headers = ["h1", "h2", "h3"]
    # enregistrer_donnees_sqlite s'attend à des tuples (code, proprietaire, debit, credit, date)
    rows = [
        ("Jean", "C001", 100.0, 0.0, "2025-10-28"),
        ("Marie","C002", 50.0, 0.0, "2025-10-28"),
    ]
    data = headers + rows

    enregistrer_donnees_sqlite(data, db_path)

    db_rows = fetch_all("charge", db_path)
    # We expect two rows in the charge table
    assert len(db_rows) >= 2
    codes = [r[1] for r in db_rows[-2:]]  # code is the second column
    assert "C001" in codes and "C002" in codes


def test_trigger_alerte_debit_eleve(tmp_path: Path):
    db_file = tmp_path / "test_trigger.db"
    db_path = str(db_file)

    # Create DB and tables
    integrite_db(db_path)

    # Insert a charge with a debit > 2000 to fire the trigger
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date, last_check) VALUES (?, ?, ?, ?, ?, ?)",
        ("T001", "Danger", 2500.0, 0.0, "2025-10-28", "2025-10-28"),
    )
    conn.commit()
    conn.close()

    alerts = fetch_all("alertes_debit_eleve", db_path)
    # The trigger should have inserted at least one alert
    assert len(alerts) >= 1
    # Ensure the inserted alert references the origin charge id
    assert any(a[3] == 2500.0 or a[4] == 2500.0 or 2500.0 in a for a in alerts)
