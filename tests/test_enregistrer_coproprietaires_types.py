import sqlite3
from pathlib import Path

from cptcopro.Data_To_BDD import integrite_db, enregistrer_coproprietaires


def read_codes(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT code_proprietaire FROM coproprietaires ORDER BY code_proprietaire")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def test_enregistrer_coproprietaires_accepts_dicts(tmp_path: Path):
    db_file = tmp_path / "test_copro_dicts.db"
    db_path = str(db_file)

    integrite_db(db_path)

    rows = [
        {"proprietaire": "Alice", "code": "A1", "num_apt": "10", "type_apt": "App"},
        {"proprietaire": "Bob", "code": "B2", "num_apt": "11", "type_apt": "Local"},
    ]

    # Should not raise and should populate the table
    res = enregistrer_coproprietaires(rows, db_path)
    # implementation may return None; we just check DB state
    codes = read_codes(db_path)
    assert "A1" in codes and "B2" in codes


def test_enregistrer_coproprietaires_mixed_tuple_dict_behavior(tmp_path: Path):
    db_file = tmp_path / "test_copro_mixed.db"
    db_path = str(db_file)

    integrite_db(db_path)

    rows = [
        {"proprietaire": "Claire", "code": "C3", "num_apt": "12", "type_apt": "App"},
        ("David", "D4", "13", "Local"),
    ]

    # Behaviour depends on implementation: either function accepts tuples and inserts both,
    # or it raises AttributeError when encountering tuple. Accept both outcomes.
    try:
        enregistrer_coproprietaires(rows, db_path)
    except AttributeError:
        # In current implementation an AttributeError indicates tuples aren't supported;
        # the function should not have inserted any rows because the error occurs before DB write.
        codes = read_codes(db_path)
        assert codes == []
    else:
        codes = read_codes(db_path)
        assert "C3" in codes and "D4" in codes
