import sqlite3
from pathlib import Path


from cptcopro.Dedoublonnage import analyse_doublons, suppression_doublons


def create_test_db(path: str):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE charge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom_proprietaire TEXT,
            code_proprietaire TEXT,
            debit REAL,
            credit REAL,
            date TEXT,
            last_check TEXT
        )
        """
    )
    conn.commit()
    return conn


def insert_rows(conn, rows):
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO charge (nom_proprietaire, code_proprietaire, debit, credit, date, last_check) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def test_dedoublonnage_basic(tmp_path: Path):
    db = tmp_path / "test.sqlite"
    conn = create_test_db(str(db))

    # Insert rows: for owner A and date D we'll insert 3 rows with different last_check
    rows = [
        ("Owner A", "A1", 10.0, 0.0, "2025-01-01", "2025-01-01"),
        ("Owner A", "A1", 10.0, 0.0, "2025-01-01", "2025-01-02"),
        ("Owner A", "A1", 10.0, 0.0, "2025-01-01", "2025-01-03"),
        # Another owner with single row
        ("Owner B", "B1", 5.0, 0.0, "2025-02-01", "2025-02-01"),
    ]
    insert_rows(conn, rows)

    # Check dedup detection
    ids_to_delete = analyse_doublons(str(db))
    # We expect 2 ids to delete (keep the most recent last_check for Owner A)
    assert len(ids_to_delete) == 2

    # Apply deletion and verify remaining rows (suppression_doublons doesn't return a count)
    suppression_doublons(str(db), ids_to_delete)

    cur = conn.cursor()
    cur.execute("SELECT nom_proprietaire, last_check FROM charge")
    remaining_rows = cur.fetchall()

    # Expected remaining rows: Owner A with the most recent last_check, Owner B original
    expected = {("Owner A", "2025-01-03"), ("Owner B", "2025-02-01")}
    assert set(remaining_rows) == expected

    # Ensure older Owner A timestamps are absent by asserting Owner A has the newest timestamp
    for owner, last_check in remaining_rows:
        if owner == "Owner A":
            assert last_check == "2025-01-03"

    conn.close()
