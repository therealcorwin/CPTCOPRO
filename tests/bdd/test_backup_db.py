"""Tests pour le module Backup_DB.py (Dump logique MariaDB)."""

from __future__ import annotations

import gzip
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from cptcopro.Database.Backup_DB import (
    _format_sql_value,
    backup_db,
    generate_insert_statements,
)
from cptcopro.Database.connection import get_db_connection


class TestBackupDbHelpers:
    """Tests unitaires pour les fonctions utilitaires de Backup_DB."""

    def test_format_sql_value_types(self):
        assert _format_sql_value(None) == "NULL"
        assert _format_sql_value(True) == "1"
        assert _format_sql_value(False) == "0"
        assert _format_sql_value(42) == "42"
        assert _format_sql_value(3.14) == "3.14"
        assert _format_sql_value(Decimal("123.45")) == "123.45"
        assert _format_sql_value(date(2026, 9, 11)) == "'2026-09-11'"
        assert _format_sql_value("l'appartement") == "'l\\'appartement'"
        assert _format_sql_value(b"abc") == "X'616263'"

    def test_generate_insert_statements_empty(self):
        result = generate_insert_statements("coproprietaires", [])
        assert "-- Table coproprietaires: 0 lignes" in result

    def test_generate_insert_statements_with_data(self):
        rows = [
            {"id": 1, "nom": "Dupont", "debit": Decimal("100.50")},
            {"id": 2, "nom": "Martin", "debit": Decimal("200.00")},
        ]
        result = generate_insert_statements("test_table", rows)
        assert "INSERT INTO `test_table` (`id`, `nom`, `debit`) VALUES" in result
        assert "(1, 'Dupont', 100.50)" in result
        assert "(2, 'Martin', 200.00)" in result
        assert "ON DUPLICATE KEY UPDATE" in result
        assert "`id` = VALUES(`id`)" in result


class TestBackupDbExecution:
    """Tests d'integration et d'execution pour backup_db()."""

    @pytest.fixture
    def backup_dir(self, tmp_path) -> Path:
        """Repertoire temporaire pour les sauvegardes."""
        b_dir = tmp_path / "BACKUP"
        b_dir.mkdir(parents=True, exist_ok=True)
        return b_dir

    def test_creates_backup_file(self, backup_dir: Path):
        """Genere un fichier .sql.gz avec le bon pattern de nom."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt, last_check) "
                    "VALUES (%s, %s, %s, %s, CURRENT_DATE) ON DUPLICATE KEY UPDATE nom_proprietaire=VALUES(nom_proprietaire)",
                    ("Test Backup", "TB01", "1", "3p"),
                )

        with patch("cptcopro.Database.Backup_DB.get_backup_dir", return_value=backup_dir):
            result = backup_db()

        assert result is not None
        backup_path = Path(result)
        assert backup_path.exists()
        assert backup_path.name.startswith("backup_cptcopro-")
        assert backup_path.name.endswith(".sql.gz")

        # Verifier le contenu decompresse
        with gzip.open(backup_path, "rt", encoding="utf-8") as gz:
            content = gz.read()

        assert "SET FOREIGN_KEY_CHECKS = 0;" in content
        assert "SET FOREIGN_KEY_CHECKS = 1;" in content
        assert "coproprietaires" in content
        assert "TB01" in content

    def test_multiple_backups_have_different_names(self, backup_dir: Path):
        """Plusieurs sauvegardes espacees d'une seconde ont des noms distincts."""
        with patch("cptcopro.Database.Backup_DB.get_backup_dir", return_value=backup_dir):
            res1 = backup_db()
            time.sleep(1.1)
            res2 = backup_db()

        assert res1 is not None and res2 is not None
        assert res1 != res2
        gz_files = list(backup_dir.glob("*.sql.gz"))
        assert len(gz_files) == 2

    def test_dump_and_restore_roundtrip(self, backup_dir: Path):
        """Verifie qu'un dump produit par backup_db peut etre restaure fidelement."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt, last_check) "
                    "VALUES (%s, %s, %s, %s, CURRENT_DATE) ON DUPLICATE KEY UPDATE nom_proprietaire=VALUES(nom_proprietaire)",
                    ("Restore Roundtrip", "RR01", "99", "5p"),
                )

        with patch("cptcopro.Database.Backup_DB.get_backup_dir", return_value=backup_dir):
            dump_file = backup_db()

        assert dump_file is not None
        backup_path = Path(dump_file)

        # Supprimer la ligne de la BDD
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM coproprietaires WHERE code_proprietaire = 'RR01'")
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM coproprietaires WHERE code_proprietaire = 'RR01'"
                )
                assert cur.fetchone()["cnt"] == 0

        # Restaurer le dump
        with gzip.open(backup_path, "rt", encoding="utf-8") as gz:
            sql_content = gz.read()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for stmt in sql_content.split(";"):
                    stmt_lines = [
                        line for line in stmt.splitlines() if not line.strip().startswith("--")
                    ]
                    stmt_clean = "\n".join(stmt_lines).strip()
                    if stmt_clean:
                        cur.execute(stmt_clean)

        # Verifier la restauration
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nom_proprietaire, type_apt FROM coproprietaires WHERE code_proprietaire = 'RR01'"
                )
                row = cur.fetchone()
                assert row is not None
                assert row["nom_proprietaire"] == "Restore Roundtrip"
                assert row["type_apt"] == "5p"

        # Nettoyage
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM coproprietaires WHERE code_proprietaire = 'RR01'")

    def test_handles_connection_error_gracefully(self, backup_dir: Path):
        """Gere proprement une erreur inattendue et retourne None."""
        with patch("cptcopro.Database.Backup_DB.get_backup_dir", return_value=backup_dir):
            with patch(
                "cptcopro.Database.Backup_DB.get_db_connection",
                side_effect=Exception("Database error"),
            ):
                res = backup_db()
                assert res is None
