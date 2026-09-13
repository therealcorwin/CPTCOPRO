"""Tests pour la configuration des alertes (table config_alerte) sur MariaDB."""

from cptcopro import Database as dbmod
from cptcopro.Database.connection import get_db_connection, get_db_cursor


def test_config_alerte_table_created():
    """Test que la table config_alerte existe et contient les bonnes colonnes."""
    dbmod.integrite_db()

    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'config_alerte'
            """
        )
        columns = {row["COLUMN_NAME"] for row in cur.fetchall()}
        expected = {"type_apt", "charge_moyenne", "taux", "threshold", "last_update"}
        assert expected.issubset(columns), f"Colonnes manquantes: {expected - columns}"


def test_default_thresholds_initialized():
    """Test que les seuils par defaut sont initialises."""
    dbmod.integrite_db()

    with get_db_cursor() as cur:
        cur.execute("SELECT type_apt, threshold FROM config_alerte ORDER BY type_apt")
        rows = cur.fetchall()
        config = {row["type_apt"]: float(row["threshold"]) for row in rows}

        assert "2p" in config, "Configuration pour 2p manquante"
        assert "3p" in config, "Configuration pour 3p manquante"
        assert "4p" in config, "Configuration pour 4p manquante"
        assert "5p" in config, "Configuration pour 5p manquante"
        assert "default" in config, "Configuration default manquante"

        assert config["2p"] == 2000.0
        assert config["3p"] == 2400.0
        assert config["4p"] == 2800.0
        assert config["5p"] == 3200.0
        assert config["default"] == 2000.0


def test_get_config_alertes():
    """Test de la fonction get_config_alertes."""
    dbmod.integrite_db()
    config = dbmod.get_config_alertes()

    assert isinstance(config, list), "get_config_alertes devrait retourner une liste"
    assert len(config) >= 5, f"Au moins 5 entrees attendues, obtenu {len(config)}"

    for item in config:
        assert "type_apt" in item
        assert "charge_moyenne" in item
        assert "taux" in item
        assert "threshold" in item


def test_update_config_alerte():
    """Test de la fonction update_config_alerte."""
    dbmod.integrite_db()
    success = dbmod.update_config_alerte("3p", charge_moyenne=2500.0, taux=1.5)
    assert success, "update_config_alerte devrait retourner True"

    config_after = dbmod.get_config_alertes()
    updated_3p = next(c for c in config_after if c["type_apt"] == "3p")

    assert float(updated_3p["charge_moyenne"]) == 2500.0
    assert float(updated_3p["taux"]) == 1.5
    assert float(updated_3p["threshold"]) == 3750.0


def test_update_config_alerte_explicit_threshold():
    """Test que le threshold peut etre defini explicitement sans recalcul."""
    dbmod.integrite_db()
    success = dbmod.update_config_alerte("4p", threshold=5000.0)
    assert success, "update_config_alerte devrait retourner True"

    config = dbmod.get_config_alertes()
    updated_4p = next(c for c in config if c["type_apt"] == "4p")
    assert float(updated_4p["threshold"]) == 5000.0


def test_get_threshold_for_type():
    """Test de la fonction get_threshold_for_type."""
    dbmod.integrite_db()
    assert dbmod.get_threshold_for_type("2p") == 2000.0
    assert dbmod.get_threshold_for_type("3p") == 2400.0
    assert dbmod.get_threshold_for_type("4p") == 2800.0
    assert dbmod.get_threshold_for_type("5p") == 3200.0
    assert dbmod.get_threshold_for_type("inconnu") == 2000.0


def test_init_config_alerte_if_missing():
    """Test de init_config_alerte_if_missing."""
    dbmod.integrite_db()
    result = dbmod.init_config_alerte_if_missing()
    assert not result, "Devrait retourner False car deja initialise"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM config_alerte")

    result = dbmod.init_config_alerte_if_missing()
    assert result, "Devrait retourner True car initialise"

    config = dbmod.get_config_alertes()
    assert len(config) >= 5, "Au moins 5 entrees apres init"


def test_update_nonexistent_type():
    """Test que update_config_alerte gere les types inexistants."""
    dbmod.integrite_db()
    result = dbmod.update_config_alerte("type_inexistant", threshold=1000.0)
    assert not result, "Devrait retourner False pour un type inexistant"
