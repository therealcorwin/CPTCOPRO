"""Tests pour le module Backup_DB.py."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from cptcopro.Database.Backup_DB import backup_db


class TestBackupDb:
    """Tests pour la fonction backup_db()."""
    
    @pytest.fixture
    def sample_db(self, tmp_path) -> Path:
        """Crée une base de données SQLite de test."""
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test (name) VALUES ('test_data')")
        conn.commit()
        conn.close()
        return db_path
    
    @pytest.fixture
    def backup_dir(self, tmp_path) -> Path:
        """Retourne un répertoire de backup temporaire."""
        return tmp_path / "BACKUP"
    
    def test_creates_backup_file(self, sample_db, backup_dir):
        """Crée un fichier de backup avec le bon format de nom."""
        with patch('cptcopro.Database.Backup_DB.get_backup_dir', return_value=backup_dir):
            with patch('cptcopro.Database.Backup_DB._USE_PORTABLE_PATHS', True):
                backup_db(str(sample_db))
        
        # Vérifier que le backup existe
        assert backup_dir.exists()
        backup_files = list(backup_dir.glob("backup_*.sqlite"))
        assert len(backup_files) == 1
        
        # Vérifier le format du nom
        backup_name = backup_files[0].name
        assert backup_name.startswith("backup_test.sqlite-")
    
    def test_backup_contains_same_data(self, sample_db, backup_dir):
        """Le backup contient les mêmes données que l'original."""
        with patch('cptcopro.Database.Backup_DB.get_backup_dir', return_value=backup_dir):
            with patch('cptcopro.Database.Backup_DB._USE_PORTABLE_PATHS', True):
                backup_db(str(sample_db))
        
        backup_files = list(backup_dir.glob("backup_*.sqlite"))
        backup_path = backup_files[0]
        
        # Vérifier les données dans le backup
        conn = sqlite3.connect(backup_path)
        cursor = conn.execute("SELECT name FROM test")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        assert rows[0][0] == "test_data"
    
    def test_creates_backup_dir_if_not_exists(self, sample_db, backup_dir):
        """Crée le répertoire BACKUP s'il n'existe pas."""
        assert not backup_dir.exists()
        
        with patch('cptcopro.Database.Backup_DB.get_backup_dir', return_value=backup_dir):
            with patch('cptcopro.Database.Backup_DB._USE_PORTABLE_PATHS', True):
                backup_db(str(sample_db))
        
        assert backup_dir.exists()
    
    def test_handles_nonexistent_db(self, tmp_path, backup_dir):
        """Gère gracieusement une base de données inexistante."""
        nonexistent_db = tmp_path / "nonexistent.sqlite"
        
        with patch('cptcopro.Database.Backup_DB.get_backup_dir', return_value=backup_dir):
            with patch('cptcopro.Database.Backup_DB._USE_PORTABLE_PATHS', True):
                # Ne doit pas lever d'exception
                backup_db(str(nonexistent_db))
        
        # Aucun backup ne doit être créé
        if backup_dir.exists():
            backup_files = list(backup_dir.glob("backup_*.sqlite"))
            assert len(backup_files) == 0
    
    def test_handles_permission_error_on_backup_dir(self, sample_db, tmp_path):
        """Gère gracieusement une erreur de permission sur le répertoire."""
        # Simuler une erreur lors de la création du répertoire
        with patch('cptcopro.Database.Backup_DB._USE_PORTABLE_PATHS', False):
            with patch('os.makedirs', side_effect=PermissionError("Access denied")):
                with patch('os.path.exists', return_value=False):
                    # Ne doit pas lever d'exception non gérée
                    backup_db(str(sample_db))
    
    def test_multiple_backups_have_different_names(self, sample_db, backup_dir):
        """Plusieurs backups ont des noms différents (timestamp)."""
        with patch('cptcopro.Database.Backup_DB.get_backup_dir', return_value=backup_dir):
            with patch('cptcopro.Database.Backup_DB._USE_PORTABLE_PATHS', True):
                # Premier backup
                backup_db(str(sample_db))
                
                # Attendre un peu pour avoir un timestamp différent
                import time
                time.sleep(1.1)
                
                # Deuxième backup
                backup_db(str(sample_db))
        
        backup_files = list(backup_dir.glob("backup_*.sqlite"))
        assert len(backup_files) == 2
        
        # Les noms doivent être différents
        names = [f.name for f in backup_files]
        assert names[0] != names[1]
    
    def test_backup_timestamp_format(self, sample_db, backup_dir):
        """Le timestamp dans le nom du backup est au bon format."""
        with patch('cptcopro.Database.Backup_DB.get_backup_dir', return_value=backup_dir):
            with patch('cptcopro.Database.Backup_DB._USE_PORTABLE_PATHS', True):
                backup_db(str(sample_db))
        
        backup_files = list(backup_dir.glob("backup_*.sqlite"))
        backup_name = backup_files[0].name
        
        # Format attendu: backup_test.sqlite-DD-MM-YY-HH-MM-SS.sqlite
        # Extraire le timestamp
        parts = backup_name.replace("backup_test.sqlite-", "").replace(".sqlite", "")
        
        # Devrait être parsable comme date
        try:
            datetime.strptime(parts, "%d-%m-%y-%H-%M-%S")
        except ValueError:
            pytest.fail(f"Format de timestamp invalide: {parts}")
    
    def test_fallback_to_module_dir_when_no_portable_paths(self, sample_db, tmp_path):
        """Utilise le répertoire du module si paths.py n'est pas disponible."""
        # Ce test vérifie le comportement quand _USE_PORTABLE_PATHS est False
        # En mode fallback, backup_db utilise os.path.dirname(__file__) + "BACKUP"
        
        # Patch uniquement _USE_PORTABLE_PATHS et le chemin __file__ du module
        import cptcopro.Database.Backup_DB as backup_module
        original_file = backup_module.__file__
        
        try:
            # Simuler que le module est dans tmp_path
            backup_module.__file__ = str(tmp_path / "Backup_DB.py")
            
            with patch.object(backup_module, '_USE_PORTABLE_PATHS', False):
                backup_db(str(sample_db))
            
            # Vérifier que le répertoire BACKUP a été créé dans tmp_path
            expected_backup_dir = tmp_path / "BACKUP"
            assert expected_backup_dir.exists(), f"Le répertoire BACKUP devrait exister dans {tmp_path}"
            
            # Vérifier que le chemin contient bien le répertoire tmp_path
            assert str(tmp_path) in str(expected_backup_dir), \
                f"Le chemin de backup devrait contenir {tmp_path}"
            
            # Trouver le fichier de backup créé
            backup_files = list(expected_backup_dir.glob("backup_*.sqlite"))
            assert len(backup_files) == 1, \
                f"Un seul fichier backup devrait exister, trouvé: {backup_files}"
            
            backup_file = backup_files[0]
            
            # Vérifier que le fichier backup contient les données de sample_db
            conn = sqlite3.connect(backup_file)
            cursor = conn.execute("SELECT name FROM test")
            rows = cursor.fetchall()
            conn.close()
            
            assert len(rows) == 1, "Le backup devrait contenir une ligne"
            assert rows[0][0] == "test_data", \
                f"Le backup devrait contenir 'test_data', trouvé: {rows[0][0]}"
        finally:
            # Restaurer __file__ original
            backup_module.__file__ = original_file


class TestBackupDbIntegration:
    """Tests d'intégration pour backup_db() avec le vrai système de fichiers."""
    
    def test_real_backup_workflow(self, tmp_path):
        """Test complet du workflow de backup."""
        # Créer une vraie base de données
        db_path = tmp_path / "production.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE coproprietaires (
                id INTEGER PRIMARY KEY,
                code TEXT,
                nom TEXT,
                debit REAL,
                credit REAL
            )
        """)
        conn.execute(
            "INSERT INTO coproprietaires (code, nom, debit, credit) VALUES (?, ?, ?, ?)",
            ("001", "Dupont", 100.0, 50.0)
        )
        conn.commit()
        conn.close()
        
        # Créer le backup
        backup_dir = tmp_path / "BACKUP"
        with patch('cptcopro.Database.Backup_DB.get_backup_dir', return_value=backup_dir):
            with patch('cptcopro.Database.Backup_DB._USE_PORTABLE_PATHS', True):
                backup_db(str(db_path))
        
        # Vérifier l'intégrité du backup
        backup_files = list(backup_dir.glob("backup_*.sqlite"))
        assert len(backup_files) == 1
        
        backup_conn = sqlite3.connect(backup_files[0])
        cursor = backup_conn.execute("SELECT code, nom, debit, credit FROM coproprietaires")
        row = cursor.fetchone()
        backup_conn.close()
        
        assert row == ("001", "Dupont", 100.0, 50.0)
