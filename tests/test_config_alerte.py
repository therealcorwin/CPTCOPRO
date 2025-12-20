"""Tests pour la configuration des alertes (table config_alerte)."""
import sqlite3
from pathlib import Path

from cptcopro import Database as dbmod


def setup_db(path: Path):
    """Configure la base de données avec les tables et triggers."""
    dbmod.integrite_db(str(path))


def test_config_alerte_table_created(tmp_path):
    """Test que la table config_alerte est créée avec integrite_db."""
    db = tmp_path / "config_test.db"
    setup_db(db)
    
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config_alerte'")
        assert cur.fetchone() is not None, "Table config_alerte devrait exister"
        
        # Vérifier les colonnes
        cur.execute("PRAGMA table_info(config_alerte)")
        columns = {row[1] for row in cur.fetchall()}
        expected = {'type_apt', 'charge_moyenne', 'taux', 'threshold', 'last_update'}
        assert expected.issubset(columns), f"Colonnes manquantes: {expected - columns}"
    finally:
        conn.close()


def test_default_thresholds_initialized(tmp_path):
    """Test que les seuils par défaut sont initialisés."""
    db = tmp_path / "config_test2.db"
    setup_db(db)
    
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    try:
        cur.execute("SELECT type_apt, threshold FROM config_alerte ORDER BY type_apt")
        rows = cur.fetchall()
        config = {row[0]: row[1] for row in rows}
        
        # Vérifier les types attendus
        assert '2p' in config, "Configuration pour 2p manquante"
        assert '3p' in config, "Configuration pour 3p manquante"
        assert '4p' in config, "Configuration pour 4p manquante"
        assert '5p' in config, "Configuration pour 5p manquante"
        assert 'default' in config, "Configuration default manquante"
        
        # Vérifier les valeurs attendues
        assert config['2p'] == 2000.0, f"Seuil 2p devrait être 2000, obtenu {config['2p']}"
        assert config['3p'] == 2400.0, f"Seuil 3p devrait être 2400, obtenu {config['3p']}"
        assert config['4p'] == 2800.0, f"Seuil 4p devrait être 2800, obtenu {config['4p']}"
        assert config['5p'] == 3200.0, f"Seuil 5p devrait être 3200, obtenu {config['5p']}"
        assert config['default'] == 2000.0, f"Seuil default devrait être 2000, obtenu {config['default']}"
    finally:
        conn.close()


def test_get_config_alertes(tmp_path):
    """Test de la fonction get_config_alertes."""
    db = tmp_path / "config_test3.db"
    setup_db(db)
    
    config = dbmod.get_config_alertes(str(db))
    
    assert isinstance(config, list), "get_config_alertes devrait retourner une liste"
    assert len(config) >= 5, f"Au moins 5 entrées attendues, obtenu {len(config)}"
    
    # Vérifier la structure
    for item in config:
        assert 'type_apt' in item
        assert 'charge_moyenne' in item
        assert 'taux' in item
        assert 'threshold' in item


def test_update_config_alerte(tmp_path):
    """Test de la fonction update_config_alerte."""
    db = tmp_path / "config_test4.db"
    setup_db(db)
    
    # Mettre à jour
    success = dbmod.update_config_alerte(str(db), '3p', charge_moyenne=2500.0, taux=1.5)
    assert success, "update_config_alerte devrait retourner True"
    
    # Vérifier la mise à jour
    config_after = dbmod.get_config_alertes(str(db))
    updated_3p = next(c for c in config_after if c['type_apt'] == '3p')
    
    assert updated_3p['charge_moyenne'] == 2500.0, "charge_moyenne devrait être mise à jour"
    assert updated_3p['taux'] == 1.5, "taux devrait être mis à jour"
    assert updated_3p['threshold'] == 3750.0, "threshold devrait être recalculé (2500 * 1.5 = 3750)"


def test_update_config_alerte_explicit_threshold(tmp_path):
    """Test que le threshold peut être défini explicitement sans recalcul."""
    db = tmp_path / "config_test5.db"
    setup_db(db)
    
    # Mettre à jour avec un threshold explicite
    success = dbmod.update_config_alerte(str(db), '4p', threshold=5000.0)
    assert success, "update_config_alerte devrait retourner True"
    
    # Vérifier que le threshold est celui défini explicitement
    config = dbmod.get_config_alertes(str(db))
    updated_4p = next(c for c in config if c['type_apt'] == '4p')
    
    assert updated_4p['threshold'] == 5000.0, "threshold devrait être 5000 (valeur explicite)"


def test_get_threshold_for_type(tmp_path):
    """Test de la fonction get_threshold_for_type."""
    db = tmp_path / "config_test6.db"
    setup_db(db)
    
    # Tester les types connus
    assert dbmod.get_threshold_for_type(str(db), '2p') == 2000.0
    assert dbmod.get_threshold_for_type(str(db), '3p') == 2400.0
    assert dbmod.get_threshold_for_type(str(db), '4p') == 2800.0
    assert dbmod.get_threshold_for_type(str(db), '5p') == 3200.0
    
    # Tester un type inconnu -> devrait retourner le default
    assert dbmod.get_threshold_for_type(str(db), 'inconnu') == 2000.0


def test_init_config_alerte_if_missing(tmp_path):
    """Test de init_config_alerte_if_missing."""
    db = tmp_path / "config_test7.db"
    setup_db(db)
    
    # La table devrait déjà être initialisée par integrite_db
    result = dbmod.init_config_alerte_if_missing(str(db))
    assert not result, "Devrait retourner False car déjà initialisé"
    
    # Vider la table et réessayer
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.execute("DELETE FROM config_alerte")
    conn.commit()
    conn.close()
    
    result = dbmod.init_config_alerte_if_missing(str(db))
    assert result, "Devrait retourner True car initialisé"
    
    # Vérifier que les données sont là
    config = dbmod.get_config_alertes(str(db))
    assert len(config) >= 5, "Au moins 5 entrées après init"


def test_update_nonexistent_type(tmp_path):
    """Test que update_config_alerte gère les types inexistants."""
    db = tmp_path / "config_test8.db"
    setup_db(db)
    
    result = dbmod.update_config_alerte(str(db), 'type_inexistant', threshold=1000.0)
    assert not result, "Devrait retourner False pour un type inexistant"
