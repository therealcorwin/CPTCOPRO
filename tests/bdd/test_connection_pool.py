"""Tests pour le pool de connexions MariaDB (connection.py)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pymysql
import pytest

from cptcopro.Database.connection import (
    execute_with_retry,
    get_db_connection,
    get_db_cursor,
    verif_connexion_db,
)


def test_verif_connexion_db_success():
    """Vérifie que le test de connectivité réussit sur le serveur MariaDB actif."""
    verif_connexion_db()


def test_verif_connexion_db_failure():
    """Vérifie que verif_connexion_db lève RuntimeError si la connexion échoue."""
    with patch("cptcopro.Database.connection.get_db_cursor", side_effect=Exception("Timeout")):
        with pytest.raises(RuntimeError, match="Base de donnees MariaDB inaccessible"):
            verif_connexion_db()


def test_dict_cursor_structure():
    """Vérifie que get_db_cursor retourne des dictionnaires clé/valeur."""
    with get_db_cursor() as cur:
        cur.execute("SELECT 1 AS num, 'test_val' AS label")
        row = cur.fetchone()
        assert row is not None
        assert row["num"] == 1
        assert row["label"] == "test_val"


def test_connection_commit_on_success():
    """Vérifie que le context manager get_db_connection committe à la sortie."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt, last_check) "
                "VALUES (%s, %s, %s, %s, CURRENT_DATE)",
                ("Dupont Commit", "C_COMMIT", "1", "3p"),
            )

    # Nouvelle connexion pour vérifier la persistance
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM coproprietaires WHERE code_proprietaire = 'C_COMMIT'")
        row = cur.fetchone()
        assert row is not None
        assert row["nom_proprietaire"] == "Dupont Commit"


def test_connection_rollback_on_exception():
    """Vérifie que le context manager effectue un rollback sur exception."""
    with pytest.raises(ValueError, match="Erreur intentionnelle"):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt, last_check) "
                    "VALUES (%s, %s, %s, %s, CURRENT_DATE)",
                    ("Dupont Rollback", "C_ROLLBACK", "2", "3p"),
                )
            raise ValueError("Erreur intentionnelle")

    # Nouvelle connexion pour vérifier que la ligne n'a pas été insérée
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM coproprietaires WHERE code_proprietaire = 'C_ROLLBACK'")
        row = cur.fetchone()
        assert row is None


def test_deadlock_retry():
    """Vérifie que l'erreur 1213 déclenche un retry automatique."""
    call_attempts = 0

    def attempt_action(conn):
        nonlocal call_attempts
        call_attempts += 1
        if call_attempts == 1:
            raise pymysql.err.OperationalError(1213, "Deadlock found when trying to get lock")
        return "success"

    res = execute_with_retry(attempt_action, max_retries=3, backoff_base=0.001)

    assert res == "success"
    assert call_attempts == 2


def test_concurrent_pool_access():
    """Vérifie que plusieurs threads peuvent emprunter et libérer des connexions du pool en parallèle."""

    def worker(worker_id: int) -> int:
        with get_db_cursor() as cur:
            cur.execute("SELECT %s AS id", (worker_id,))
            res = cur.fetchone()
            return int(res["id"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(16)]
        results = [f.result() for f in futures]

    assert results == list(range(16))
