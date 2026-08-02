import sqlite3
from pathlib import Path

from cptcopro.Database import integrite_db, enregistrer_donnees_sqlite
from cptcopro.Database.Charges_To_BDD import _normaliser_lignes_charge


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
        ("C001", "OWNER_ALPHA", 100.0, 0.0, "2025-10-28"),
        ("C002", "OWNER_BETA", 50.0, 0.0, "2025-10-28"),
    ]
    data = headers + rows

    enregistrer_donnees_sqlite(data, db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT code_proprietaire, nom_proprietaire FROM charge WHERE date = ? ORDER BY code_proprietaire",
            ("2025-10-28",),
        )
        inserted = cur.fetchall()
    finally:
        conn.close()

    assert inserted == [("C001", "OWNER_ALPHA"), ("C002", "OWNER_BETA")]


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


def test_enregistrer_donnees_sqlite_no_longer_drops_first_three_rows(tmp_path: Path):
    db_file = tmp_path / "test_no_drop_first_three.db"
    db_path = str(db_file)
    integrite_db(db_path)

    # Données réelles sans en-têtes: historiquement, les 3 premières étaient perdues.
    rows = [
        ("C101", "OWNER_001", 2500.0, 0.0, "2026-08-02"),
        ("C102", "OWNER_002", 2600.0, 0.0, "2026-08-02"),
        ("C103", "OWNER_003", 2700.0, 0.0, "2026-08-02"),
        ("C104", "OWNER_004", 1200.0, 0.0, "2026-08-02"),
    ]

    enregistrer_donnees_sqlite(rows, db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT code_proprietaire FROM charge WHERE date = ? ORDER BY code_proprietaire",
            ("2026-08-02",),
        )
        inserted_codes = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    assert inserted_codes == ["C101", "C102", "C103", "C104"]


def test_normaliser_lignes_charge_ignores_non_rows_and_keeps_valid_rows() -> None:
    data = [
        "header_1",
        "header_2",
        "header_3",
        ("C201", "NOM 1", 123.0, 0.0, "2026-08-02"),
        ["C202", "NOM 2", 456.0, 10.0, "2026-08-02", "extra"],
        ("too", "short"),
    ]

    normalized = _normaliser_lignes_charge(data)

    assert normalized == [
        ("C201", "NOM 1", 123.0, 0.0, "2026-08-02"),
        ("C202", "NOM 2", 456.0, 10.0, "2026-08-02"),
    ]


def test_enregistrer_donnees_sqlite_mixed_headers_and_rows(tmp_path: Path):
    db_file = tmp_path / "test_mixed_headers_rows.db"
    db_path = str(db_file)
    integrite_db(db_path)

    data = [
        "h1",
        "h2",
        "h3",
        ("C301", "ALPHA", 2001.0, 0.0, "2026-08-03"),
        ("C302", "BETA", 1999.0, 0.0, "2026-08-03"),
        "footer_ignored",
    ]

    enregistrer_donnees_sqlite(data, db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT code_proprietaire, nom_proprietaire FROM charge WHERE date = ? ORDER BY code_proprietaire",
            ("2026-08-03",),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    assert rows == [("C301", "ALPHA"), ("C302", "BETA")]


def test_alertes_first_run_contains_expected_owners_with_mixed_input(tmp_path: Path):
    """Régression: au premier run, les 3 premiers copropriétaires ne doivent plus disparaître."""
    db_file = tmp_path / "test_alertes_first_run.db"
    db_path = str(db_file)
    integrite_db(db_path)

    charges_data = [
        "header_1",
        "header_2",
        "header_3",
        ("C401", "OWNER_101", 5000.0, 0.0, "2026-08-02"),
        ("C402", "OWNER_102", 5100.0, 0.0, "2026-08-02"),
        ("C403", "OWNER_103", 5200.0, 0.0, "2026-08-02"),
        ("C404", "OWNER_104", 900.0, 0.0, "2026-08-02"),
    ]
    copro_data = [
        {
            "nom_proprietaire": "OWNER_101",
            "code_proprietaire": "C401",
            "num_apt": "1",
            "type_apt": "3p",
        },
        {
            "nom_proprietaire": "OWNER_102",
            "code_proprietaire": "C402",
            "num_apt": "2",
            "type_apt": "3p",
        },
        {
            "nom_proprietaire": "OWNER_103",
            "code_proprietaire": "C403",
            "num_apt": "3",
            "type_apt": "4p",
        },
        {
            "nom_proprietaire": "OWNER_104",
            "code_proprietaire": "C404",
            "num_apt": "4",
            "type_apt": "2p",
        },
    ]

    # Même ordre que main.py: charges puis coproprietaires
    enregistrer_donnees_sqlite(charges_data, db_path)
    from cptcopro.Database import enregistrer_coproprietaires

    enregistrer_coproprietaires(copro_data, db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT nom_proprietaire FROM alertes_debit_eleve")
        noms_alertes = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    assert "OWNER_101" in noms_alertes
    assert "OWNER_102" in noms_alertes
    assert "OWNER_103" in noms_alertes


def test_alertes_set_is_stable_between_first_and_second_run(tmp_path: Path):
    """Régression: mêmes données sur 2 runs => même ensemble d'alertes."""
    db_file = tmp_path / "test_alertes_stable_runs.db"
    db_path = str(db_file)
    integrite_db(db_path)

    charges_data = [
        "header_1",
        "header_2",
        "header_3",
        ("C501", "OWNER_201", 5000.0, 0.0, "2026-08-02"),
        ("C502", "OWNER_202", 5100.0, 0.0, "2026-08-02"),
        ("C503", "OWNER_203", 5200.0, 0.0, "2026-08-02"),
        ("C504", "OWNER_204", 900.0, 0.0, "2026-08-02"),
    ]
    copro_data = [
        {
            "nom_proprietaire": "OWNER_201",
            "code_proprietaire": "C501",
            "num_apt": "1",
            "type_apt": "3p",
        },
        {
            "nom_proprietaire": "OWNER_202",
            "code_proprietaire": "C502",
            "num_apt": "2",
            "type_apt": "3p",
        },
        {
            "nom_proprietaire": "OWNER_203",
            "code_proprietaire": "C503",
            "num_apt": "3",
            "type_apt": "4p",
        },
        {
            "nom_proprietaire": "OWNER_204",
            "code_proprietaire": "C504",
            "num_apt": "4",
            "type_apt": "2p",
        },
    ]

    from cptcopro.Database import enregistrer_coproprietaires

    # Run 1
    enregistrer_donnees_sqlite(charges_data, db_path)
    enregistrer_coproprietaires(copro_data, db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT code_proprietaire FROM alertes_debit_eleve ORDER BY code_proprietaire")
        alertes_run1 = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    # Run 2 (mêmes données)
    enregistrer_donnees_sqlite(charges_data, db_path)
    enregistrer_coproprietaires(copro_data, db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT code_proprietaire FROM alertes_debit_eleve ORDER BY code_proprietaire")
        alertes_run2 = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    assert alertes_run1 == alertes_run2
    assert alertes_run2 == ["C501", "C502", "C503"]
