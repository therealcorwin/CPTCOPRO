"""Tests pour l'enregistrement et la normalisation des charges dans MariaDB (Charges_To_BDD.py)."""

from cptcopro.Database import enregistrer_charges, enregistrer_coproprietaires, integrite_db
from cptcopro.Database.Charges_To_BDD import _normaliser_lignes_charge
from cptcopro.Database.connection import get_db_cursor


def test_enregistrer_charges_happy_path():
    integrite_db()

    headers = ["h1", "h2", "h3"]
    rows = [
        ("C001", "OWNER_ALPHA", 100.0, 0.0, "2025-10-28"),
        ("C002", "OWNER_BETA", 50.0, 0.0, "2025-10-28"),
    ]
    data = headers + rows

    enregistrer_charges(data)

    with get_db_cursor() as cur:
        cur.execute(
            "SELECT code_proprietaire, nom_proprietaire FROM charge WHERE date = %s ORDER BY code_proprietaire",
            ("2025-10-28",),
        )
        inserted = [(r["code_proprietaire"], r["nom_proprietaire"]) for r in cur.fetchall()]

    assert inserted == [("C001", "OWNER_ALPHA"), ("C002", "OWNER_BETA")]


def test_enregistrer_charges_no_longer_drops_first_three_rows():
    integrite_db()

    rows = [
        ("C101", "OWNER_001", 2500.0, 0.0, "2026-08-02"),
        ("C102", "OWNER_002", 2600.0, 0.0, "2026-08-02"),
        ("C103", "OWNER_003", 2700.0, 0.0, "2026-08-02"),
        ("C104", "OWNER_004", 1200.0, 0.0, "2026-08-02"),
    ]

    enregistrer_charges(rows)

    with get_db_cursor() as cur:
        cur.execute(
            "SELECT code_proprietaire FROM charge WHERE date = %s ORDER BY code_proprietaire",
            ("2026-08-02",),
        )
        inserted_codes = [r["code_proprietaire"] for r in cur.fetchall()]

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


def test_enregistrer_charges_mixed_headers_and_rows():
    integrite_db()

    data = [
        "h1",
        "h2",
        "h3",
        ("C301", "ALPHA", 2001.0, 0.0, "2026-08-03"),
        ("C302", "BETA", 1999.0, 0.0, "2026-08-03"),
        "footer_ignored",
    ]

    enregistrer_charges(data)

    with get_db_cursor() as cur:
        cur.execute(
            "SELECT code_proprietaire, nom_proprietaire FROM charge WHERE date = %s ORDER BY code_proprietaire",
            ("2026-08-03",),
        )
        rows = [(r["code_proprietaire"], r["nom_proprietaire"]) for r in cur.fetchall()]

    assert rows == [("C301", "ALPHA"), ("C302", "BETA")]


def test_alertes_first_run_contains_expected_owners_with_mixed_input():
    integrite_db()

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

    enregistrer_charges(charges_data)
    enregistrer_coproprietaires(copro_data)

    with get_db_cursor() as cur:
        cur.execute("SELECT nom_proprietaire FROM alertes_debit_eleve")
        noms_alertes = {row["nom_proprietaire"] for row in cur.fetchall()}

    assert "OWNER_101" in noms_alertes
    assert "OWNER_102" in noms_alertes
    assert "OWNER_103" in noms_alertes


def test_alertes_set_is_stable_between_first_and_second_run():
    integrite_db()

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

    enregistrer_charges(charges_data)
    enregistrer_coproprietaires(copro_data)

    with get_db_cursor() as cur:
        cur.execute("SELECT code_proprietaire FROM alertes_debit_eleve ORDER BY code_proprietaire")
        alertes_run1 = [row["code_proprietaire"] for row in cur.fetchall()]

    # Run 2
    enregistrer_charges(charges_data)
    enregistrer_coproprietaires(copro_data)

    with get_db_cursor() as cur:
        cur.execute("SELECT code_proprietaire FROM alertes_debit_eleve ORDER BY code_proprietaire")
        alertes_run2 = [row["code_proprietaire"] for row in cur.fetchall()]

    assert alertes_run1 == alertes_run2
    assert alertes_run2 == ["C501", "C502", "C503"]
