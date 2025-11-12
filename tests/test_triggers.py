import sqlite3
from pathlib import Path

from cptcopro import Data_To_BDD as dbmod


def setup_db(path: Path):
    dbmod.integrite_db(str(path))


def test_insert_creates_and_upserts(tmp_path):
    db = tmp_path / "triggers_test.db"
    setup_db(db)
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        # insert first qualifying charge -> alert created
        cur.execute("INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, date('now'))",
                    ("C100", "Owner A", 2500.0, 0.0))
        id1 = cur.lastrowid
        conn.commit()
        cur.execute("SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = ?", ("C100",))
        row = cur.fetchone()
        assert row is not None and row[0] == id1

        # insert second qualifying charge -> alert updated, still one row
        cur.execute("INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, date('now'))",
                    ("C100", "Owner A", 2600.0, 0.0))
        id2 = cur.lastrowid
        conn.commit()
        cur.execute("SELECT COUNT(*), id_origin FROM alertes_debit_eleve WHERE code_proprietaire = ?", ("C100",))
        cnt, id_origin = cur.fetchone()
        assert cnt == 1
        assert id_origin == id2
    finally:
        conn.close()


def test_insert_low_clears_alert(tmp_path):
    db = tmp_path / "triggers_test2.db"
    setup_db(db)
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        # create alert
        cur.execute("INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, date('now'))",
                    ("C200", "Owner B", 3000.0, 0.0))
        # id1 not used below; no need to assign
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?", ("C200",))
        assert cur.fetchone()[0] == 1

        # insert a low debit as latest -> should clear alert
        cur.execute("INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, date('now'))",
                    ("C200", "Owner B", 1000.0, 0.0))
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?", ("C200",))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_delete_rebuilds_from_previous_latest(tmp_path):
    db = tmp_path / "triggers_test3.db"
    setup_db(db)
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        # insert two qualifying charges; latest is id2
        cur.execute("INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, date('now'))",
                    ("C300", "Owner C", 2100.0, 0.0))
        id1 = cur.lastrowid
        conn.commit()
        cur.execute("INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, date('now'))",
                    ("C300", "Owner C", 2200.0, 0.0))
        id2 = cur.lastrowid
        conn.commit()
        # alert should point to id2
        cur.execute("SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = ?", ("C300",))
        assert cur.fetchone()[0] == id2

        # delete id2 (latest) -> trigger should rebuild alert from new latest (id1)
        cur.execute("DELETE FROM charge WHERE id = ?", (id2,))
        conn.commit()
        cur.execute("SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = ?", ("C300",))
        row = cur.fetchone()
        assert row is not None and row[0] == id1
    finally:
        conn.close()
