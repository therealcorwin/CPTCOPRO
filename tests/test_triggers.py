import sqlite3
from pathlib import Path

from cptcopro import Database as dbmod


def setup_db(path: Path):
    """Configure la base de données avec les tables et triggers."""
    dbmod.integrite_db(str(path))


def setup_coproprietaire(conn, code: str, type_apt: str = "3p"):
    """Ajoute un copropriétaire avec son type d'appartement pour les tests."""
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO coproprietaires (code_proprietaire, nom_proprietaire, type_apt) VALUES (?, ?, ?)",
        (code, f"Owner {code}", type_apt),
    )
    conn.commit()


def test_insert_creates_and_upserts(tmp_path):
    """Test que l'insertion d'une charge au-dessus du seuil crée une alerte."""
    db = tmp_path / "triggers_test.db"
    setup_db(db)
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        # Configurer le copropriétaire avec type 3p (seuil 2400€)
        setup_coproprietaire(conn, "C100", "3p")

        # insert first qualifying charge -> alert created (seuil 3p = 2400, 2500 > 2400)
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("C100", "Owner A", 2500.0, 0.0, "2026-01-01"),
        )
        id1 = cur.lastrowid
        conn.commit()
        cur.execute(
            "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("C100",),
        )
        row = cur.fetchone()
        assert row is not None and row[0] == id1

        # insert second qualifying charge with different date -> alert updated, still one row
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("C100", "Owner A", 2600.0, 0.0, "2026-01-02"),
        )
        id2 = cur.lastrowid
        conn.commit()
        # ensure exactly one alert exists for this proprietor
        cur.execute(
            "SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("C100",),
        )
        cnt = cur.fetchone()[0]
        assert cnt == 1

        # fetch the alert's origin id (most recent) and compare to id2
        cur.execute(
            "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = ? ORDER BY alerte_id DESC LIMIT 1",
            ("C100",),
        )
        id_origin_row = cur.fetchone()
        assert id_origin_row is not None and id_origin_row[0] == id2
    finally:
        conn.close()


def test_insert_low_clears_alert(tmp_path):
    """Test que l'insertion d'une charge sous le seuil supprime l'alerte existante."""
    db = tmp_path / "triggers_test2.db"
    setup_db(db)
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        # Configurer le copropriétaire avec type 3p (seuil 2400€)
        setup_coproprietaire(conn, "C200", "3p")

        # create alert (3000 > 2400)
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("C200", "Owner B", 3000.0, 0.0, "2026-01-01"),
        )
        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("C200",),
        )
        assert cur.fetchone()[0] == 1

        # insert a low debit as latest with different date -> should clear alert (1000 < 2400)
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("C200", "Owner B", 1000.0, 0.0, "2026-01-02"),
        )
        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("C200",),
        )
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_delete_rebuilds_from_previous_latest(tmp_path):
    """Test que la suppression d'une charge reconstruit l'alerte si la nouvelle dernière dépasse le seuil."""
    db = tmp_path / "triggers_test3.db"
    setup_db(db)
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        # Configurer le copropriétaire avec type 2p (seuil 2000€)
        setup_coproprietaire(conn, "C300", "2p")

        # insert two qualifying charges; latest is id2 (2100 et 2200 > 2000)
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("C300", "Owner C", 2100.0, 0.0, "2026-01-01"),
        )
        id1 = cur.lastrowid
        conn.commit()
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("C300", "Owner C", 2200.0, 0.0, "2026-01-02"),
        )
        id2 = cur.lastrowid
        conn.commit()
        # alert should point to id2
        cur.execute(
            "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("C300",),
        )
        assert cur.fetchone()[0] == id2

        # delete id2 (latest) -> trigger should rebuild alert from new latest (id1)
        cur.execute("DELETE FROM charge WHERE id = ?", (id2,))
        conn.commit()
        cur.execute(
            "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("C300",),
        )
        row = cur.fetchone()
        assert row is not None and row[0] == id1
    finally:
        conn.close()


def test_threshold_varies_by_type_apt(tmp_path):
    """Test que le seuil d'alerte varie selon le type d'appartement."""
    db = tmp_path / "triggers_test4.db"
    setup_db(db)
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        # Copropriétaire 2p (seuil 2000€) - 2100 devrait déclencher une alerte
        setup_coproprietaire(conn, "T2P", "2p")
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("T2P", "Owner 2P", 2100.0, 0.0, "2026-01-01"),
        )
        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("T2P",),
        )
        assert cur.fetchone()[0] == 1, (
            "2100€ devrait déclencher une alerte pour un 2p (seuil 2000€)"
        )

        # Copropriétaire 4p (seuil 2800€) - 2100 ne devrait PAS déclencher d'alerte
        setup_coproprietaire(conn, "T4P", "4p")
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("T4P", "Owner 4P", 2100.0, 0.0, "2026-01-01"),
        )
        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("T4P",),
        )
        assert cur.fetchone()[0] == 0, (
            "2100€ ne devrait pas déclencher d'alerte pour un 4p (seuil 2800€)"
        )

        # Copropriétaire 4p avec débit au-dessus du seuil - devrait déclencher
        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, ?)",
            ("T4P", "Owner 4P", 3000.0, 0.0, "2026-01-02"),
        )
        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("T4P",),
        )
        assert cur.fetchone()[0] == 1, (
            "3000€ devrait déclencher une alerte pour un 4p (seuil 2800€)"
        )
    finally:
        conn.close()


def test_default_threshold_for_unknown_type(tmp_path):
    """Test que le seuil par défaut est utilisé pour les types d'appartement inconnus."""
    db = tmp_path / "triggers_test5.db"
    setup_db(db)
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        # Copropriétaire sans type défini dans coproprietaires -> seuil default (2000€)
        # Ne pas ajouter de coproprietaire, le fallback default sera utilisé

        cur.execute(
            "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (?, ?, ?, ?, date('now'))",
            ("UNKNOWN", "Owner Unknown", 2100.0, 0.0),
        )
        conn.commit()

        # Avec le seuil default de 2000€, 2100€ devrait déclencher une alerte
        cur.execute(
            "SELECT COUNT(*) FROM alertes_debit_eleve WHERE code_proprietaire = ?",
            ("UNKNOWN",),
        )
        assert cur.fetchone()[0] == 1, (
            "2100€ devrait déclencher une alerte avec le seuil default (2000€)"
        )
    finally:
        conn.close()
