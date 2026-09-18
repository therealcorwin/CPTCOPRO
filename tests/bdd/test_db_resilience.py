"""Tests de résilience de la base de données : base vide, éléments manquants et auto-réparation.

Ces tests valident explicitement le comportement en cas de :
1. Base vide (aucune table présente) : verif_presence_db() et creer_base_db().
2. Élément manquant (table, trigger, vue, colonne) : integrite_db() et auto-réparation.
3. Restauration conditionnelle : _restore_db_from_pcloud_if_missing().
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cptcopro.Database.connection import get_db_connection, get_db_cursor
from cptcopro.Database.Creation_BDD import (
    creer_base_db,
    integrite_db,
    verif_presence_db,
)
from cptcopro.main import _restore_db_from_pcloud_if_missing

ALL_TABLES = [
    "relance_draft",
    "relance_template",
    "relance_destinataire",
    "relance_config",
    "suivi_alertes",
    "alertes_debit_eleve",
    "charge",
    "coproprietaires",
    "config_alerte",
]


def _drop_everything() -> None:
    """Supprime toutes les tables, vues et triggers de la base de test."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            cur.execute("DROP VIEW IF EXISTS vw_charge_coproprietaires")
            cur.execute("DROP TRIGGER IF EXISTS alerte_debit_eleve_insert")
            cur.execute("DROP TRIGGER IF EXISTS alerte_debit_eleve_insert_clear")
            cur.execute("DROP TRIGGER IF EXISTS alerte_debit_eleve_delete")
            for table in ALL_TABLES:
                cur.execute(f"DROP TABLE IF EXISTS `{table}`")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")


def test_verif_presence_db_returns_false_when_empty_and_true_when_created():
    """Vérifie que verif_presence_db() détecte l'absence et la présence de la table 'charge'."""
    _drop_everything()
    assert verif_presence_db() is False

    creer_base_db()
    assert verif_presence_db() is True


def test_creer_base_db_from_scratch_initializes_all_structures():
    """Vérifie que creer_base_db() crée l'intégralité des 9 tables, de la vue et des 3 triggers à partir de rien."""
    _drop_everything()
    assert verif_presence_db() is False

    creer_base_db()

    with get_db_cursor() as cur:
        # Vérifier les 9 tables (y compris charge avec system versioning)
        cur.execute(
            """
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE IN ('BASE TABLE', 'SYSTEM VERSIONED')
            """
        )
        found_tables = {row["TABLE_NAME"] for row in cur.fetchall()}
        for expected_table in ALL_TABLES:
            assert expected_table in found_tables, f"Table manquante : {expected_table}"

        # Vérifier la vue
        cur.execute(
            """
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS
            WHERE TABLE_SCHEMA = DATABASE()
            """
        )
        found_views = {row["TABLE_NAME"] for row in cur.fetchall()}
        assert "vw_charge_coproprietaires" in found_views

        # Vérifier les 3 triggers
        cur.execute(
            """
            SELECT TRIGGER_NAME FROM INFORMATION_SCHEMA.TRIGGERS
            WHERE TRIGGER_SCHEMA = DATABASE()
            """
        )
        found_triggers = {row["TRIGGER_NAME"] for row in cur.fetchall()}
        assert "alerte_debit_eleve_insert" in found_triggers
        assert "alerte_debit_eleve_insert_clear" in found_triggers
        assert "alerte_debit_eleve_delete" in found_triggers


def test_integrite_db_recreates_missing_table():
    """Vérifie que si une table est supprimée, integrite_db() la recrée et la liste dans 'created'."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            cur.execute("DROP TABLE IF EXISTS coproprietaires")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    # integrite_db doit détecter et recréer la table
    result = integrite_db()
    assert "coproprietaires" in result["created"]
    assert result["coproprietaires"] is False  # était absente avant l'appel

    # Vérifier que la table existe à nouveau
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'coproprietaires'"
        )
        assert cur.fetchone() is not None


def test_integrite_db_recreates_missing_trigger():
    """Vérifie que si un trigger est supprimé, integrite_db() le recrée automatiquement."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS alerte_debit_eleve_insert")

    result = integrite_db()
    assert "alerte_debit_eleve_triggers" in result["created"]
    assert result["alerte_debit_eleve"] is False  # le trigger était absent

    # Vérifier que le trigger existe à nouveau
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM INFORMATION_SCHEMA.TRIGGERS
            WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = 'alerte_debit_eleve_insert'
            """
        )
        assert cur.fetchone() is not None


def test_integrite_db_recreates_missing_view():
    """Vérifie que si la vue est supprimée, integrite_db() la recrée et elle est requêtable."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP VIEW IF EXISTS vw_charge_coproprietaires")

    integrite_db()

    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM vw_charge_coproprietaires")
        row = cur.fetchone()
        assert row is not None
        assert "cnt" in row


def test_integrite_db_adds_missing_column():
    """Vérifie que si la colonne date_origin manque dans alertes_debit_eleve, elle est ajoutée."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'alertes_debit_eleve' AND COLUMN_NAME = 'date_origin'"
            )
            if cur.fetchone():
                cur.execute("ALTER TABLE alertes_debit_eleve DROP COLUMN date_origin")

    result = integrite_db()
    assert "alertes_debit_eleve.date_origin" in result["created"]

    with get_db_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'alertes_debit_eleve' AND COLUMN_NAME = 'date_origin'"
        )
        assert cur.fetchone() is not None


def test_restore_db_from_pcloud_if_missing_skips_when_present():
    """Vérifie que si la base est déjà présente, _restore_db_from_pcloud_if_missing() ne fait rien et retourne False."""
    creer_base_db()
    with patch("cptcopro.Database.Backup_DB_Pcloud.tester_token_et_connecter_pcloud") as mock_conn:
        restored = _restore_db_from_pcloud_if_missing()
        assert restored is False
        mock_conn.assert_not_called()


def test_restore_db_from_pcloud_if_missing_creates_base_when_no_pcloud_backup():
    """Vérifie que si la base est absente et sans backup pCloud, elle est initialisée à neuf via creer_base_db()."""
    _drop_everything()
    assert verif_presence_db() is False

    with (
        patch(
            "cptcopro.Database.Backup_DB_Pcloud.tester_token_et_connecter_pcloud",
            return_value=MagicMock(),
        ),
        patch(
            "cptcopro.Database.Backup_DB_Pcloud.telecharger_dernier_backup_pcloud",
            side_effect=RuntimeError("Aucun fichier de backup trouvé sur pCloud"),
        ),
    ):
        restored = _restore_db_from_pcloud_if_missing()
        assert restored is False

    # La base a été créée à neuf par creer_base_db()
    assert verif_presence_db() is True
