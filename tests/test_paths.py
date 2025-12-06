"""Tests pour le module utils/paths.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

from cptcopro.utils.paths import (
    is_pyinstaller_bundle,
    get_app_dir,
    get_bundle_dir,
    get_data_dir,
    get_db_path,
    get_log_path,
    get_backup_dir,
    get_env_file_path,
    get_streamlit_config_dir,
)


class TestIsPyinstallerBundle:
    """Tests pour is_pyinstaller_bundle()."""
    
    def test_returns_false_in_normal_mode(self):
        """En mode normal (dev), doit retourner False."""
        # En mode test, on n'est pas dans un bundle PyInstaller
        assert is_pyinstaller_bundle() is False
    
    def test_returns_true_when_frozen(self):
        """Quand sys.frozen et sys._MEIPASS existent, doit retourner True."""
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, '_MEIPASS', 'C:\\temp\\meipass', create=True):
                assert is_pyinstaller_bundle() is True
    
    def test_returns_false_when_frozen_but_no_meipass(self):
        """Quand sys.frozen existe mais pas _MEIPASS, doit retourner False."""
        with patch.object(sys, 'frozen', True, create=True):
            # Supprimer _MEIPASS s'il existe
            if hasattr(sys, '_MEIPASS'):
                delattr(sys, '_MEIPASS')
            assert is_pyinstaller_bundle() is False


class TestGetAppDir:
    """Tests pour get_app_dir()."""
    
    def test_returns_path_in_dev_mode(self):
        """En mode dev, retourne le répertoire src/cptcopro."""
        app_dir = get_app_dir()
        assert isinstance(app_dir, Path)
        assert app_dir.exists()
        # Devrait être le répertoire src/cptcopro
        assert app_dir.name == "cptcopro"
    
    def test_returns_exe_dir_in_pyinstaller_mode(self, tmp_path):
        """En mode PyInstaller, retourne le répertoire de l'exe."""
        fake_exe = tmp_path / "my_app.exe"
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, '_MEIPASS', str(tmp_path / "_meipass"), create=True):
                with patch.object(sys, 'executable', str(fake_exe)):
                    app_dir = get_app_dir()
                    assert app_dir == tmp_path


class TestGetBundleDir:
    """Tests pour get_bundle_dir()."""
    
    def test_returns_path_in_dev_mode(self):
        """En mode dev, retourne src/cptcopro."""
        bundle_dir = get_bundle_dir()
        assert isinstance(bundle_dir, Path)
        assert bundle_dir.name == "cptcopro"
    
    def test_returns_meipass_in_pyinstaller_mode(self, tmp_path):
        """En mode PyInstaller, retourne _MEIPASS/cptcopro."""
        meipass = tmp_path / "_meipass"
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, '_MEIPASS', str(meipass), create=True):
                bundle_dir = get_bundle_dir()
                assert bundle_dir == meipass / "cptcopro"


class TestGetDataDir:
    """Tests pour get_data_dir()."""
    
    def test_returns_existing_directory(self):
        """Retourne un répertoire qui existe."""
        data_dir = get_data_dir()
        assert isinstance(data_dir, Path)
        assert data_dir.exists()
        assert data_dir.is_dir()


class TestGetDbPath:
    """Tests pour get_db_path()."""
    
    def test_default_db_name(self):
        """Utilise le nom par défaut si non spécifié."""
        with patch.dict(os.environ, {}, clear=True):
            db_path = get_db_path()
            assert db_path.name == "test.sqlite"
            assert "BDD" in str(db_path)
    
    def test_custom_db_name(self):
        """Accepte un nom de DB personnalisé."""
        with patch.dict(os.environ, {}, clear=True):
            db_path = get_db_path("ma_base.sqlite")
            assert db_path.name == "ma_base.sqlite"
    
    def test_env_var_override_new_name(self, tmp_path):
        """La variable CPTCOPRO_DB_PATH override le chemin par défaut."""
        custom_path = tmp_path / "custom" / "db.sqlite"
        with patch.dict(os.environ, {"CPTCOPRO_DB_PATH": str(custom_path)}):
            db_path = get_db_path()
            assert db_path == custom_path.resolve()
            # Le répertoire parent doit être créé
            assert custom_path.parent.exists()
    
    def test_env_var_override_old_name(self, tmp_path):
        """La variable CTPCOPRO_DB_PATH (ancienne) fonctionne aussi."""
        custom_path = tmp_path / "legacy" / "db.sqlite"
        with patch.dict(os.environ, {"CTPCOPRO_DB_PATH": str(custom_path)}, clear=True):
            db_path = get_db_path()
            assert db_path == custom_path.resolve()    
    def test_new_env_var_takes_precedence(self, tmp_path):
        """CPTCOPRO_DB_PATH a priorité sur CTPCOPRO_DB_PATH."""
        new_path = tmp_path / "new" / "db.sqlite"
        old_path = tmp_path / "old" / "db.sqlite"
        with patch.dict(os.environ, {
            "CPTCOPRO_DB_PATH": str(new_path),
            "CTPCOPRO_DB_PATH": str(old_path)
        }):
            db_path = get_db_path()
            assert db_path == new_path.resolve()
    
    def test_creates_parent_directory(self, tmp_path):
        """Crée le répertoire parent si nécessaire."""
        custom_path = tmp_path / "niveau1" / "niveau2" / "db.sqlite"
        assert not custom_path.parent.exists()
        
        with patch.dict(os.environ, {"CPTCOPRO_DB_PATH": str(custom_path)}):
            get_db_path()
            assert custom_path.parent.exists()


class TestGetLogPath:
    """Tests pour get_log_path()."""
    
    def test_default_log_name(self):
        """Utilise le nom par défaut si non spécifié."""
        with patch.dict(os.environ, {}, clear=True):
            log_path = get_log_path()
            assert log_path.name == "ctpcopro.log"
            assert "logs" in str(log_path)
    
    def test_custom_log_name(self):
        """Accepte un nom de log personnalisé."""
        with patch.dict(os.environ, {}, clear=True):
            log_path = get_log_path("custom.log")
            assert log_path.name == "custom.log"
    
    def test_env_var_override(self, tmp_path):
        """La variable CPTCOPRO_LOG_FILE override le chemin."""
        custom_path = tmp_path / "logs" / "app.log"
        with patch.dict(os.environ, {"CPTCOPRO_LOG_FILE": str(custom_path)}):
            log_path = get_log_path()
            assert log_path == custom_path.resolve()
            assert custom_path.parent.exists()


class TestGetBackupDir:
    """Tests pour get_backup_dir()."""
    
    def test_returns_backup_directory(self):
        """Retourne un répertoire Backup."""
        backup_dir = get_backup_dir()
        assert isinstance(backup_dir, Path)
        assert backup_dir.name == "Backup"
        assert backup_dir.exists()


class TestGetEnvFilePath:
    """Tests pour get_env_file_path()."""
    
    def test_returns_none_if_no_env_file(self, tmp_path, monkeypatch):
        """Retourne None si aucun .env n'est trouvé."""
        # Changer vers un répertoire sans .env
        monkeypatch.chdir(tmp_path)
        
        # Mock pour éviter de chercher dans les vrais répertoires
        with patch('cptcopro.utils.paths.get_app_dir', return_value=tmp_path / "app"):
            with patch('cptcopro.utils.paths.get_bundle_dir', return_value=tmp_path / "bundle"):
                result = get_env_file_path()
                assert result is None
    
    def test_finds_env_in_app_dir(self, tmp_path, monkeypatch):
        """Trouve .env dans le répertoire app."""
        env_file = tmp_path / ".env"
        env_file.write_text("TEST=value")
        
        with patch('cptcopro.utils.paths.get_app_dir', return_value=tmp_path):
            result = get_env_file_path()
            assert result == env_file


class TestGetStreamlitConfigDir:
    """Tests pour get_streamlit_config_dir()."""
    
    def test_returns_none_if_no_config(self, tmp_path):
        """Retourne None si aucun .streamlit n'est trouvé."""
        with patch('cptcopro.utils.paths.get_app_dir', return_value=tmp_path / "app"):
            with patch('cptcopro.utils.paths.get_bundle_dir', return_value=tmp_path / "bundle"):
                result = get_streamlit_config_dir()
                assert result is None
    
    def test_finds_config_in_app_dir(self, tmp_path):
        """Trouve .streamlit dans le répertoire app."""
        config_dir = tmp_path / ".streamlit"
        config_dir.mkdir()
        
        with patch('cptcopro.utils.paths.get_app_dir', return_value=tmp_path):
            result = get_streamlit_config_dir()
            assert result == config_dir
