"""Tests pour les triggers MariaDB de detection des alertes de debit eleve."""

from cptcopro.Database.connection import get_db_connection


def setup_coproprietaire(cur, code: str, type_apt: str = "3p"):
    """Ajoute un copropriétaire avec son type d'appartement pour les tests."""
    cur.execute(
        """
        INSERT INTO coproprietaires (code_proprietaire, nom_proprietaire, type_apt, last_check)
        VALUES (%s, %s, %s, CURRENT_DATE)
        ON DUPLICATE KEY UPDATE type_apt = VALUES(type_apt)
        """,
        (code, f"Owner {code}", type_apt),
    )


def test_insert_creates_and_upserts():
    """Test que l'insertion d'une charge au-dessus du seuil cree une alerte."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            setup_coproprietaire(cur, "C100", "3p")

            # insert first qualifying charge -> alert created (seuil 3p = 2400, 2500 > 2400)
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C100", "Owner A", 2500.0, 0.0, "2026-01-01"),
            )
            id1 = cur.lastrowid

            cur.execute(
                "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C100",),
            )
            row = cur.fetchone()
            assert row is not None and row["id_origin"] == id1

            # insert second qualifying charge with different date -> alert updated, still one row
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C100", "Owner A", 2600.0, 0.0, "2026-01-02"),
            )
            id2 = cur.lastrowid

            cur.execute(
                "SELECT COUNT(*) AS cnt FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C100",),
            )
            assert cur.fetchone()["cnt"] == 1

            cur.execute(
                "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = %s ORDER BY alerte_id DESC LIMIT 1",
                ("C100",),
            )
            id_origin_row = cur.fetchone()
            assert id_origin_row is not None and id_origin_row["id_origin"] == id2


def test_insert_low_clears_alert():
    """Test que l'insertion d'une charge sous le seuil supprime l'alerte existante."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            setup_coproprietaire(cur, "C200", "3p")

            # create alert (3000 > 2400)
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C200", "Owner B", 3000.0, 0.0, "2026-01-01"),
            )
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C200",),
            )
            assert cur.fetchone()["cnt"] == 1

            # insert a low debit as latest with different date -> should clear alert (1000 < 2400)
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C200", "Owner B", 1000.0, 0.0, "2026-01-02"),
            )
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C200",),
            )
            assert cur.fetchone()["cnt"] == 0


def test_delete_rebuilds_from_previous_latest():
    """Test que la suppression d'une charge reconstruit l'alerte si la nouvelle derniere depasse le seuil."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            setup_coproprietaire(cur, "C300", "2p")

            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C300", "Owner C", 2100.0, 0.0, "2026-01-01"),
            )
            id1 = cur.lastrowid
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C300", "Owner C", 2200.0, 0.0, "2026-01-02"),
            )
            id2 = cur.lastrowid

            cur.execute(
                "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C300",),
            )
            assert cur.fetchone()["id_origin"] == id2

            # delete id2 (latest) -> trigger should rebuild alert from new latest (id1)
            cur.execute("DELETE FROM charge WHERE id = %s", (id2,))
            cur.execute(
                "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C300",),
            )
            row = cur.fetchone()
            assert row is not None and row["id_origin"] == id1


def test_threshold_varies_by_type_apt():
    """Test que le seuil d'alerte varie selon le type d'appartement."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 2p (seuil 2000€) - 2100 declenche une alerte
            setup_coproprietaire(cur, "T2P", "2p")
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("T2P", "Owner 2P", 2100.0, 0.0, "2026-01-01"),
            )
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("T2P",),
            )
            assert cur.fetchone()["cnt"] == 1

            # 4p (seuil 2800€) - 2100 ne declenche PAS d'alerte
            setup_coproprietaire(cur, "T4P", "4p")
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("T4P", "Owner 4P", 2100.0, 0.0, "2026-01-01"),
            )
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("T4P",),
            )
            assert cur.fetchone()["cnt"] == 0

            # 4p avec debit au-dessus du seuil -> declenche alerte
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("T4P", "Owner 4P", 3000.0, 0.0, "2026-01-02"),
            )
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("T4P",),
            )
            assert cur.fetchone()["cnt"] == 1


def test_default_threshold_for_unknown_type():
    """Test que le seuil par defaut est utilise pour les types d'appartement inconnus."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Fallback default = 2000
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, CURRENT_DATE)",
                ("UNKNOWN", "Owner Unknown", 2100.0, 0.0),
            )
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("UNKNOWN",),
            )
            assert cur.fetchone()["cnt"] == 1


def test_older_insert_does_not_clear_newer_alert():
    """Test qu'une charge plus ancienne inseree apres la plus recente ne supprime pas l'alerte active."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            setup_coproprietaire(cur, "C600", "3p")

            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C600", "Owner F", 3000.0, 0.0, "2026-01-02"),
            )
            id_latest = cur.lastrowid

            cur.execute(
                "SELECT id_origin FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C600",),
            )
            row = cur.fetchone()
            assert row is not None and row["id_origin"] == id_latest

            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C600", "Owner F", 1000.0, 0.0, "2026-01-01"),
            )

            cur.execute(
                "SELECT id_origin, debit FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C600",),
            )
            row = cur.fetchone()
            assert row is not None
            assert row["id_origin"] == id_latest
            assert float(row["debit"]) == 3000.0


def test_occurrence_not_incremented_on_same_data_rerun():
    """Le champ occurence ne doit pas augmenter si on rejoue la meme donnee (meme date)."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            setup_coproprietaire(cur, "C700", "3p")

            cur.execute(
                """
                INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date, last_check)
                VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
                ON DUPLICATE KEY UPDATE debit = VALUES(debit), credit = VALUES(credit)
                """,
                ("C700", "Owner G", 3000.0, 0.0, "2026-02-01"),
            )

            cur.execute(
                "SELECT occurence FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C700",),
            )
            assert cur.fetchone()["occurence"] == 1

            # Meme donnee metier (meme date)
            cur.execute(
                """
                INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date, last_check)
                VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
                ON DUPLICATE KEY UPDATE debit = VALUES(debit), credit = VALUES(credit)
                """,
                ("C700", "Owner G", 3000.0, 0.0, "2026-02-01"),
            )

            cur.execute(
                "SELECT occurence FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C700",),
            )
            assert cur.fetchone()["occurence"] == 1


def test_occurrence_incremented_only_with_newer_data():
    """Le champ occurence doit augmenter uniquement quand une date plus recente arrive."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            setup_coproprietaire(cur, "C800", "3p")

            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C800", "Owner H", 3000.0, 0.0, "2026-03-01"),
            )

            cur.execute(
                "SELECT occurence FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C800",),
            )
            assert cur.fetchone()["occurence"] == 1

            # Nouvelle donnee plus recente: increment attendu
            cur.execute(
                "INSERT INTO charge (code_proprietaire, nom_proprietaire, debit, credit, date) VALUES (%s, %s, %s, %s, %s)",
                ("C800", "Owner H", 3200.0, 0.0, "2026-03-02"),
            )

            cur.execute(
                "SELECT occurence FROM alertes_debit_eleve WHERE code_proprietaire = %s",
                ("C800",),
            )
            assert cur.fetchone()["occurence"] == 2
