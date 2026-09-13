"""Tests des types d'arguments acceptes par enregistrer_coproprietaires sur MariaDB."""

from cptcopro.Database import enregistrer_coproprietaires, integrite_db
from cptcopro.Database.connection import get_db_cursor


def read_codes():
    with get_db_cursor() as cur:
        cur.execute("SELECT code_proprietaire FROM coproprietaires ORDER BY code_proprietaire")
        return [r["code_proprietaire"] for r in cur.fetchall()]


def test_enregistrer_coproprietaires_accepts_dicts():
    integrite_db()

    rows = [
        {"proprietaire": "Alice", "code": "A1", "num_apt": "10", "type_apt": "App"},
        {"proprietaire": "Bob", "code": "B2", "num_apt": "11", "type_apt": "Local"},
    ]

    enregistrer_coproprietaires(rows)
    codes = read_codes()
    assert "A1" in codes and "B2" in codes


def test_enregistrer_coproprietaires_mixed_tuple_dict_behavior():
    integrite_db()

    rows = [
        {"proprietaire": "Claire", "code": "C3", "num_apt": "12", "type_apt": "App"},
        ("David", "D4", "13", "Local"),
    ]

    try:
        enregistrer_coproprietaires(rows)
    except AttributeError:
        codes = read_codes()
        assert codes == []
    else:
        codes = read_codes()
        assert "C3" in codes and "D4" in codes
