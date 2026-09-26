"""Tests pour le CLI et l'orchestration principale (main.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pymysql
import pytest

from cptcopro.Database.connection import DatabaseConnectionError, _diagnose_db_error
from cptcopro.main import _handle_pcloud_sync, _parse_cli_args, main


def test_parse_cli_args_defaults():
    """Vérifie les arguments CLI par défaut."""
    with patch.object(sys, "argv", ["main.py"]):
        args = _parse_cli_args()
        assert args.no_headless is False
        assert args.no_serve is False
        assert args.serve_port == 8501
        assert args.serve_host == "127.0.0.1"
        assert args.show_console is False
        assert args.no_backup is False
        assert args.deco_pcloud is False
        assert args.auto_relance_drafts is False
        assert args.relance_imap is False


def test_parse_cli_args_custom_flags():
    """Vérifie la prise en compte des drapeaux personnalisés."""
    custom_argv = [
        "main.py",
        "--no-headless",
        "--no-serve",
        "--serve-port",
        "9000",
        "--serve-host",
        "0.0.0.0",
        "--show-console",
        "--no-backup",
        "--deco-pcloud",
        "--auto-relance-drafts",
        "--relance-imap",
    ]
    with patch.object(sys, "argv", custom_argv):
        args = _parse_cli_args()
        assert args.no_headless is True
        assert args.no_serve is True
        assert args.serve_port == 9000
        assert args.serve_host == "0.0.0.0"
        assert args.show_console is True
        assert args.no_backup is True
        assert args.deco_pcloud is True
        assert args.auto_relance_drafts is True
        assert args.relance_imap is True


def test_handle_pcloud_sync_no_backup():
    """Vérifie que --no-backup ignore l'upload pCloud même si un backup existe."""
    with patch("cptcopro.Database.Backup_DB_Pcloud.tester_token_et_connecter_pcloud") as mock_conn:
        _handle_pcloud_sync("fake_backup.sql", no_backup=True, deco_pcloud=False)
        mock_conn.assert_not_called()


def test_handle_pcloud_sync_with_backup_and_deco():
    """Vérifie l'envoi vers pCloud et la déconnexion optionnelle."""
    mock_client = MagicMock()
    with (
        patch(
            "cptcopro.Database.Backup_DB_Pcloud.tester_token_et_connecter_pcloud",
            return_value=mock_client,
        ) as mock_conn,
        patch("cptcopro.Database.Backup_DB_Pcloud.sauvegarder_bdd_pcloud") as mock_save,
        patch("cptcopro.Database.Backup_DB_Pcloud.deconnecter_pcloud") as mock_deco,
    ):
        _handle_pcloud_sync("fake_dump.sql", no_backup=False, deco_pcloud=True)

        mock_conn.assert_called_once()
        mock_save.assert_called_once_with(mock_client, Path("fake_dump.sql"))
        mock_deco.assert_called_once()


def test_handle_pcloud_sync_without_backup_file():
    """Vérifie qu'aucun upload n'est fait si backup_path est None."""
    with patch("cptcopro.Database.Backup_DB_Pcloud.tester_token_et_connecter_pcloud") as mock_conn:
        _handle_pcloud_sync(None, no_backup=False, deco_pcloud=False)
        mock_conn.assert_not_called()


def test_parse_cli_args_unknown_option_exits():
    """Vérifie qu'un argument inconnu provoque une sortie d'erreur du parser."""
    with patch.object(sys, "argv", ["main.py", "--option-inconnue-xyz"]):
        with pytest.raises(SystemExit):
            _parse_cli_args()


def test_main_exits_on_db_connection_failure():
    """Vérifie que main() capture DatabaseConnectionError, logue un message critique et sort avec code 1."""
    with patch("cptcopro.main._parse_cli_args") as mock_args, \
         patch("cptcopro.Database.verif_connexion_db", side_effect=DatabaseConnectionError("Base de donnees MariaDB inaccessible : Le serveur MariaDB est injoignable sur 127.0.0.1:3306")), \
         patch("cptcopro.main.logger") as mock_logger:
        mock_args.return_value = MagicMock(no_headless=False)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        mock_logger.critical.assert_called_once()
        assert "Base de donnees MariaDB inaccessible" in mock_logger.critical.call_args[0][0]


def test_diagnose_db_error_operational_2003():
    """Vérifie le diagnostic pour l'erreur 2003 (serveur injoignable)."""
    cfg = {"host": "192.168.1.50", "port": "3307", "user": "test_user", "database": "copro"}
    exc = pymysql.err.OperationalError(2003, "Can't connect to MySQL server")
    diag = _diagnose_db_error(exc, cfg)
    assert "injoignable sur 192.168.1.50:3307" in diag
    assert "service arrêté" in diag


def test_diagnose_db_error_access_denied():
    """Vérifie le diagnostic pour l'erreur 1045 (authentification refusée)."""
    cfg = {"host": "127.0.0.1", "port": "3306", "user": "bad_user", "database": "copro"}
    exc = pymysql.err.OperationalError(1045, "Access denied for user 'bad_user'")
    diag = _diagnose_db_error(exc, cfg)
    assert "Authentification refusée pour l'utilisateur 'bad_user'" in diag


def test_diagnose_db_error_unknown_database():
    """Vérifie le diagnostic pour l'erreur 1049 (base inconnue)."""
    cfg = {"host": "127.0.0.1", "port": "3306", "user": "root", "database": "nonexistent_db"}
    exc = pymysql.err.OperationalError(1049, "Unknown database 'nonexistent_db'")
    diag = _diagnose_db_error(exc, cfg)
    assert "La base de données 'nonexistent_db' n'existe pas" in diag


def test_diagnose_db_error_timeout():
    """Vérifie le diagnostic pour une erreur de timeout."""
    cfg = {"host": "127.0.0.1", "port": "3306", "user": "root", "database": "copro"}
    exc = TimeoutError("Connection timed out")
    diag = _diagnose_db_error(exc, cfg)
    assert "Délai d'attente dépassé" in diag
