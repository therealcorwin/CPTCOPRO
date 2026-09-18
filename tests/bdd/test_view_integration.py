from cptcopro.Database import integrite_db
from cptcopro.Database.connection import get_db_connection


def test_vw_charge_coproprietaires_exists_and_returns_columns():
    integrite_db()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt, last_check) "
                "VALUES (%s, %s, %s, %s, CURRENT_DATE) ON DUPLICATE KEY UPDATE num_apt=VALUES(num_apt), type_apt=VALUES(type_apt)",
                ("Dupont", "D001", "1", "3p"),
            )
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("D001", "Dupont", 100.0, 0.0, "2025-11-06"),
            )
            cur.execute(
                "SELECT code_proprietaire, nom_proprietaire, debit, credit, date, num_apt, type_apt, id "
                "FROM vw_charge_coproprietaires WHERE code_proprietaire = 'D001'"
            )
            row = cur.fetchone()

    assert row is not None
    assert row["code_proprietaire"] == "D001"
    assert row["nom_proprietaire"] == "Dupont"
    assert float(row["debit"]) == 100.0
    assert row["num_apt"] == "1"
    assert row["type_apt"] == "3p"
    assert row["id"] >= 1
