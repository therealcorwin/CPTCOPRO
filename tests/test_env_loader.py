"""Tests pour le module utils/env_loader.py."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cptcopro.utils.env_loader import (
    get_app_base_path,
    get_env_file_path,
    load_env_file,
    check_env_file_exists,
    validate_required_env_vars,
    load_and_validate_env,
    get_credentials,
)


class TestGetAppBasePath:
    """Tests pour get_app_base_path()."""
    
    def test_returns_path_in_dev_mode(self):
        """En mode dev, retourne le répertoire racine du projet."""
        base_path = get_app_base_path()
        assert isinstance(base_path, Path)
        # En mode dev, devrait remonter depuis src/cptcopro/utils jusqu'à la racine
        # La racine devrait contenir pyproject.toml
        assert (base_path / "pyproject.toml").exists() or base_path.name == "CPTCOPRO"
    
    def test_returns_exe_dir_in_frozen_mode(self, tmp_path):
        """En mode PyInstaller (frozen), retourne le répertoire de l'exe."""
        import importlib
        import cptcopro.utils.env_loader as env_loader
        
        fake_exe = tmp_path / "dist" / "my_app.exe"
        fake_exe.parent.mkdir(parents=True)
        
        try:
            with patch('sys.frozen', True, create=True):
                with patch('sys.executable', str(fake_exe)):
                    # Reload the module to pick up the patched sys attributes
                    importlib.reload(env_loader)
                    result = env_loader.get_app_base_path()
                    assert result == tmp_path / "dist"
        finally:
            # Restore original module state so other tests are unaffected
            importlib.reload(env_loader)

class TestGetEnvFilePath:
    """Tests pour get_env_file_path()."""
    
    def test_returns_path(self):
        """Retourne un Path vers .env."""
        env_path = get_env_file_path()
        assert isinstance(env_path, Path)
        assert env_path.name == ".env"


class TestCheckEnvFileExists:
    """Tests pour check_env_file_exists()."""
    
    def test_returns_bool(self):
        """Retourne un booléen."""
        result = check_env_file_exists()
        assert isinstance(result, bool)


class TestValidateRequiredEnvVars:
    """Tests pour validate_required_env_vars()."""
    
    def test_all_vars_present(self):
        """Retourne (True, []) si toutes les variables sont présentes."""
        with patch.dict(os.environ, {"VAR1": "val1", "VAR2": "val2"}):
            success, missing = validate_required_env_vars(["VAR1", "VAR2"])
            assert success is True
            assert missing == []
    
    def test_some_vars_missing(self):
        """Retourne (False, [missing]) si des variables manquent."""
        with patch.dict(os.environ, {"VAR1": "val1"}, clear=True):
            success, missing = validate_required_env_vars(["VAR1", "VAR2", "VAR3"])
            assert success is False
            assert "VAR2" in missing
            assert "VAR3" in missing
            assert "VAR1" not in missing
    
    def test_all_vars_missing(self):
        """Retourne (False, all_vars) si toutes les variables manquent."""
        with patch.dict(os.environ, {}, clear=True):
            success, missing = validate_required_env_vars(["VAR1", "VAR2"])
            assert success is False
            assert set(missing) == {"VAR1", "VAR2"}
    
    def test_empty_list(self):
        """Liste vide retourne (True, [])."""
        success, missing = validate_required_env_vars([])
        assert success is True
        assert missing == []
    
    def test_empty_value_counts_as_missing(self):
        """Une variable avec valeur vide est considérée comme manquante."""
        with patch.dict(os.environ, {"VAR1": "", "VAR2": "value"}, clear=True):
            success, missing = validate_required_env_vars(["VAR1", "VAR2"])
            assert success is False
            assert "VAR1" in missing


class TestLoadEnvFile:
    """Tests pour load_env_file()."""
    
    def test_returns_true_when_file_exists(self, tmp_path):
        """Retourne True si le fichier .env existe et est chargé."""
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\n")
        
        with patch('cptcopro.utils.env_loader.get_env_file_path', return_value=env_file):
            result = load_env_file()
            assert result is True
            assert os.environ.get("TEST_VAR") == "test_value"
        
        # Clean up the environment variable
        os.environ.pop("TEST_VAR", None)

    def test_returns_false_when_file_not_exists(self, tmp_path):
        """Retourne False si le fichier .env n'existe pas."""
        missing_file = tmp_path / ".env"
        
        with patch('cptcopro.utils.env_loader.get_env_file_path', return_value=missing_file):
            result = load_env_file()
            assert result is False


class TestLoadAndValidateEnv:
    """Tests pour load_and_validate_env()."""
    
    def test_raises_file_not_found_when_no_env(self, tmp_path):
        """Lève FileNotFoundError si .env n'existe pas."""
        missing_file = tmp_path / ".env"
        
        with patch('cptcopro.utils.env_loader.get_env_file_path', return_value=missing_file):
            with pytest.raises(FileNotFoundError) as exc_info:
                load_and_validate_env()
            assert "introuvable" in str(exc_info.value)
    
    def test_raises_value_error_when_vars_missing(self, tmp_path):
        """Lève ValueError si des variables requises manquent.
        
        Ce test vérifie que load_and_validate_env() charge le fichier .env
        et détecte les variables manquantes.
        """
        env_file = tmp_path / ".env"
        # Le fichier ne contient qu'une variable, il en manque deux
        env_file.write_text("login_site_copro=partial_user\n")
        
        # Nettoyer les variables pour s'assurer du comportement réel
        vars_to_clean = ["login_site_copro", "password_site_copro", "url_site_copro"]
        original_values = {var: os.environ.get(var) for var in vars_to_clean}
        
        try:
            for var in vars_to_clean:
                os.environ.pop(var, None)
            
            with patch('cptcopro.utils.env_loader.get_env_file_path', return_value=env_file):
                with pytest.raises(ValueError) as exc_info:
                    load_and_validate_env()
                assert "manquantes" in str(exc_info.value)
                # Vérifier que les variables manquantes sont mentionnées
                assert "password_site_copro" in str(exc_info.value) or "url_site_copro" in str(exc_info.value)
        finally:
            # Restaurer les valeurs originales
            for var, value in original_values.items():
                if value is not None:
                    os.environ[var] = value
                else:
                    os.environ.pop(var, None)
    
    def test_returns_env_dict_when_valid(self, tmp_path):
        """Retourne un dict avec les variables si tout est valide.
        
        Ce test vérifie que load_and_validate_env() charge réellement
        le fichier .env et injecte les variables dans os.environ.
        """
        env_file = tmp_path / ".env"
        env_file.write_text(
            "login_site_copro=file_user\n"
            "password_site_copro=file_pass\n"
            "url_site_copro=http://file.example.com\n"
        )
        
        # Nettoyer les variables existantes pour s'assurer qu'elles viennent du fichier
        vars_to_clean = ["login_site_copro", "password_site_copro", "url_site_copro"]
        original_values = {var: os.environ.get(var) for var in vars_to_clean}
        
        try:
            # Supprimer les variables si elles existent
            for var in vars_to_clean:
                os.environ.pop(var, None)
            
            with patch('cptcopro.utils.env_loader.get_env_file_path', return_value=env_file):
                result = load_and_validate_env()
                
                # Vérifier que les valeurs viennent bien du fichier .env
                assert result["login_site_copro"] == "file_user"
                assert result["password_site_copro"] == "file_pass"
                assert result["url_site_copro"] == "http://file.example.com"
                
                # Vérifier également que os.environ a été mis à jour
                assert os.environ["login_site_copro"] == "file_user"
        finally:
            # Restaurer les valeurs originales
            for var, value in original_values.items():
                if value is not None:
                    os.environ[var] = value
                else:
                    os.environ.pop(var, None)
    
    def test_accepts_custom_required_vars(self, tmp_path):
        """Accepte une liste personnalisée de variables requises.
        
        Ce test vérifie que load_and_validate_env() charge le fichier .env
        et valide une liste personnalisée de variables.
        """
        env_file = tmp_path / ".env"
        env_file.write_text("CUSTOM_VAR=custom_file_value\n")
        
        # Nettoyer la variable si elle existe
        original_value = os.environ.get("CUSTOM_VAR")
        
        try:
            os.environ.pop("CUSTOM_VAR", None)
            
            with patch('cptcopro.utils.env_loader.get_env_file_path', return_value=env_file):
                result = load_and_validate_env(required_vars=["CUSTOM_VAR"])
                
                # Vérifier que la valeur vient du fichier .env
                assert result == {"CUSTOM_VAR": "custom_file_value"}
                assert os.environ["CUSTOM_VAR"] == "custom_file_value"
        finally:
            # Restaurer la valeur originale
            if original_value is not None:
                os.environ["CUSTOM_VAR"] = original_value
            else:
                os.environ.pop("CUSTOM_VAR", None)


class TestGetCredentials:
    """Tests pour get_credentials()."""
    
    def test_returns_tuple_when_valid(self, tmp_path):
        """Retourne un tuple (login, password, url) quand valide.
        
        Ce test vérifie que get_credentials() charge réellement le fichier .env.
        """
        env_file = tmp_path / ".env"
        env_file.write_text(
            "login_site_copro=creds_user\n"
            "password_site_copro=creds_pass\n"
            "url_site_copro=https://creds.site.com\n"
        )
        
        # Nettoyer les variables existantes pour s'assurer qu'elles viennent du fichier
        vars_to_clean = ["login_site_copro", "password_site_copro", "url_site_copro"]
        original_values = {var: os.environ.get(var) for var in vars_to_clean}
        
        try:
            # Supprimer les variables si elles existent
            for var in vars_to_clean:
                os.environ.pop(var, None)
            
            with patch('cptcopro.utils.env_loader.get_env_file_path', return_value=env_file):
                login, password, url = get_credentials()
                
                # Vérifier que les valeurs viennent bien du fichier .env
                assert login == "creds_user"
                assert password == "creds_pass"
                assert url == "https://creds.site.com"
        finally:
            # Restaurer les valeurs originales
            for var, value in original_values.items():
                if value is not None:
                    os.environ[var] = value
                else:
                    os.environ.pop(var, None)
    
    def test_raises_when_env_missing(self, tmp_path):
        """Lève une exception si .env manque."""
        missing_file = tmp_path / ".env"
        
        with patch('cptcopro.utils.env_loader.get_env_file_path', return_value=missing_file):
            with pytest.raises(FileNotFoundError):
                get_credentials()
