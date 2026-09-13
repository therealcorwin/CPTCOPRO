"""Tests pour l'enregistrement des coproprietaires sur MariaDB."""

import pymysql
import pytest

from cptcopro.Database import enregistrer_coproprietaires, integrite_db
from cptcopro.Database.connection import get_db_connection, get_db_cursor
from cptcopro.Database.Coproprietaires_To_BDD import CollecteCoproprietairesInvalideError


def read_all_coproprietaires() -> list[tuple[str, str, str, str]]:
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT nom_proprietaire, code_proprietaire, num_apt, type_apt "
            "FROM coproprietaires ORDER BY code_proprietaire"
        )
        return [
            (r["nom_proprietaire"], r["code_proprietaire"], r["num_apt"], r["type_apt"])
            for r in cur.fetchall()
        ]


def test_enregistrer_coproprietaires_happy_path() -> None:
    integrite_db()

    rows = [
        {
            "proprietaire": "Alice Dupont",
            "code": "A001",
            "num_apt": "101",
            "type_apt": "Appartement",
        },
        {
            "proprietaire": "Bob Martin",
            "code": "B002",
            "num_apt": "102",
            "type_apt": "Local commercial",
        },
    ]

    inserted = enregistrer_coproprietaires(rows)
    assert inserted is None

    db_rows = read_all_coproprietaires()
    assert len(db_rows) == 2
    assert db_rows[0][1] == "A001"
    assert db_rows[1][1] == "B002"


def test_enregistrer_coproprietaires_empty_rows() -> None:
    integrite_db()

    inserted = enregistrer_coproprietaires([])
    assert inserted is None

    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM coproprietaires")
        count = cur.fetchone()["cnt"]
    assert count == 0


def test_enregistrer_coproprietaires_without_integrite_db_raises() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            cur.execute("DROP TABLE IF EXISTS coproprietaires")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    with pytest.raises(pymysql.Error):
        enregistrer_coproprietaires(
            [{"proprietaire": "X", "code": "X001", "num_apt": "1", "type_apt": "Apt"}]
        )

    integrite_db()


def test_enregistrer_coproprietaires_refuse_lot_invalide_and_preserve_existing_data() -> None:
    integrite_db()

    baseline = [
        {"proprietaire": "Alice Dupont", "code": "A001", "num_apt": "101", "type_apt": "3p"},
        {"proprietaire": "Bob Martin", "code": "B002", "num_apt": "102", "type_apt": "4p"},
    ]
    enregistrer_coproprietaires(baseline)
    before_rows = read_all_coproprietaires()

    invalid_payload = [
        {"proprietaire": "Alice Dupont", "code": "A001", "num_apt": "101", "type_apt": "3p"},
        {"proprietaire": "Bob Martin", "code": "B002", "num_apt": "", "type_apt": "4p"},
    ]

    with pytest.raises(CollecteCoproprietairesInvalideError):
        enregistrer_coproprietaires(invalid_payload)

    after_rows = read_all_coproprietaires()
    assert after_rows == before_rows


def test_enregistrer_coproprietaires_refuse_changed_lot_set() -> None:
    integrite_db()

    baseline = [
        {"proprietaire": "Alice Dupont", "code": "A001", "num_apt": "101", "type_apt": "3p"},
        {"proprietaire": "Bob Martin", "code": "B002", "num_apt": "102", "type_apt": "4p"},
    ]
    enregistrer_coproprietaires(baseline)
    before_rows = read_all_coproprietaires()

    changed_lot_payload = [
        {"proprietaire": "Alice Nouveau", "code": "A001", "num_apt": "101", "type_apt": "3p"},
        {"proprietaire": "Bob Nouveau", "code": "B002", "num_apt": "999", "type_apt": "4p"},
    ]

    with pytest.raises(CollecteCoproprietairesInvalideError):
        enregistrer_coproprietaires(changed_lot_payload)

    after_rows = read_all_coproprietaires()
    assert after_rows == before_rows
