"""Tests unitaires pour le module utils/privacy.py.

Ce module teste les fonctions d'anonymisation et de masquage
des données sensibles dans les DataFrames.
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


class TestAnonymiser:
    """Tests pour la fonction anonymiser."""

    def test_anonymiser_mode_masque(self):
        """Test du mode masque (défaut)."""
        from cptcopro.utils.privacy import anonymiser

        result = anonymiser("Jean Dupont", "masque")
        assert result == "●●●●●●"

    def test_anonymiser_mode_initiales(self):
        """Test du mode initiales."""
        from cptcopro.utils.privacy import anonymiser

        result = anonymiser("Jean Dupont", "initiales")
        assert result == "J. D."

    def test_anonymiser_mode_hash(self):
        """Test du mode hash."""
        from cptcopro.utils.privacy import anonymiser

        result = anonymiser("Jean Dupont", "hash")
        assert len(result) == 8
        # Le hash doit être reproductible
        result2 = anonymiser("Jean Dupont", "hash")
        assert result == result2

    def test_anonymiser_valeur_none(self):
        """Test avec valeur None."""
        from cptcopro.utils.privacy import anonymiser

        result = anonymiser(None, "masque")
        assert result is None

    def test_anonymiser_valeur_vide(self):
        """Test avec chaîne vide."""
        from cptcopro.utils.privacy import anonymiser

        result = anonymiser("", "masque")
        assert result == ""

    def test_anonymiser_valeur_nan(self):
        """Test avec valeur NaN pandas."""
        from cptcopro.utils.privacy import anonymiser
        import numpy as np

        result = anonymiser(pd.NA, "masque")
        assert pd.isna(result)

        result = anonymiser(float("nan"), "masque")
        assert pd.isna(result)


class TestAppliquerConfidentialite:
    """Tests pour la fonction appliquer_confidentialite."""

    def test_confidentialite_desactivee(self):
        """Test quand le mode confidentiel est désactivé."""
        from cptcopro.utils.privacy import appliquer_confidentialite

        df = pd.DataFrame(
            {
                "proprietaire": ["Jean Dupont", "Marie Martin"],
                "code": ["001", "002"],
                "debit": [100, 200],
            }
        )

        # Mock session_state avec privacy désactivée
        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=False):
            result = appliquer_confidentialite(df)

        # Le DataFrame doit être inchangé
        assert result["proprietaire"].iloc[0] == "Jean Dupont"
        assert result["code"].iloc[0] == "001"

    def test_confidentialite_activee(self):
        """Test quand le mode confidentiel est activé."""
        from cptcopro.utils.privacy import appliquer_confidentialite

        df = pd.DataFrame(
            {
                "proprietaire": ["Jean Dupont", "Marie Martin"],
                "code": ["001", "002"],
                "num_apt": ["A12", "B34"],
                "debit": [100, 200],
            }
        )

        # Mock session_state avec privacy activée
        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = appliquer_confidentialite(df)

        # Les colonnes sensibles doivent être masquées
        assert result["proprietaire"].iloc[0] == "●●●●●●"
        assert result["code"].iloc[0] == "●●●●●●"
        assert result["num_apt"].iloc[0] == "●●●●●●"
        # Les colonnes non sensibles doivent rester inchangées
        assert result["debit"].iloc[0] == 100

    def test_confidentialite_df_vide(self):
        """Test avec DataFrame vide."""
        from cptcopro.utils.privacy import appliquer_confidentialite

        df = pd.DataFrame()

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = appliquer_confidentialite(df)

        assert result.empty

    def test_confidentialite_colonnes_personnalisees(self):
        """Test avec colonnes personnalisées à masquer."""
        from cptcopro.utils.privacy import appliquer_confidentialite

        df = pd.DataFrame(
            {"nom": ["Jean Dupont"], "email": ["jean@example.com"], "debit": [100]}
        )

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = appliquer_confidentialite(df, colonnes=["nom", "email"])

        assert result["nom"].iloc[0] == "●●●●●●"
        assert result["email"].iloc[0] == "●●●●●●"
        assert result["debit"].iloc[0] == 100

    def test_confidentialite_mode_initiales(self):
        """Test avec mode initiales."""
        from cptcopro.utils.privacy import appliquer_confidentialite

        df = pd.DataFrame(
            {"proprietaire": ["Jean Dupont", "Marie Martin"], "debit": [100, 200]}
        )

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = appliquer_confidentialite(df, mode="initiales")

        assert result["proprietaire"].iloc[0] == "J. D."
        assert result["proprietaire"].iloc[1] == "M. M."


class TestMasquerListe:
    """Tests pour la fonction masquer_liste."""

    def test_masquer_liste_desactive(self):
        """Test quand la confidentialité est désactivée."""
        from cptcopro.utils.privacy import masquer_liste

        valeurs = ["Jean Dupont", "Marie Martin"]

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=False):
            result = masquer_liste(valeurs)

        assert result == valeurs

    def test_masquer_liste_active(self):
        """Test quand la confidentialité est activée."""
        from cptcopro.utils.privacy import masquer_liste

        valeurs = ["Jean Dupont", "Marie Martin"]

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = masquer_liste(valeurs)

        assert result == ["●●●●●●", "●●●●●●"]


class TestCreerMappingAnonymise:
    """Tests pour la fonction creer_mapping_anonymise."""

    def test_mapping_desactive(self):
        """Test quand la confidentialité est désactivée."""
        from cptcopro.utils.privacy import creer_mapping_anonymise

        valeurs = ["Jean Dupont", "Marie Martin"]

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=False):
            mapping = creer_mapping_anonymise(valeurs)

        assert mapping == {"Jean Dupont": "Jean Dupont", "Marie Martin": "Marie Martin"}

    def test_mapping_mode_initiales(self):
        """Test du mapping avec mode initiales."""
        from cptcopro.utils.privacy import creer_mapping_anonymise

        valeurs = ["Jean Dupont", "Marie Martin"]

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            mapping = creer_mapping_anonymise(valeurs, mode="initiales")

        assert "J. D." in mapping
        assert mapping["J. D."] == "Jean Dupont"
        assert "M. M." in mapping
        assert mapping["M. M."] == "Marie Martin"

    def test_mapping_mode_masque_avec_index(self):
        """Test du mapping mode masque avec index pour éviter collisions."""
        from cptcopro.utils.privacy import creer_mapping_anonymise

        valeurs = ["Jean Dupont", "Marie Martin"]

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            mapping = creer_mapping_anonymise(valeurs, mode="masque")

        # Chaque valeur masquée doit avoir un index unique
        assert "●●●●●● (1)" in mapping
        assert "●●●●●● (2)" in mapping
        assert mapping["●●●●●● (1)"] == "Jean Dupont"
        assert mapping["●●●●●● (2)"] == "Marie Martin"


class TestIsPrivacyEnabled:
    """Tests pour la fonction is_privacy_enabled."""

    def test_privacy_non_definie(self):
        """Test quand la clé n'est pas dans session_state."""
        from cptcopro.utils.privacy import is_privacy_enabled

        mock_session = {}
        with patch("cptcopro.utils.privacy.st.session_state", mock_session):
            result = is_privacy_enabled()

        assert result is False

    def test_privacy_definie_false(self):
        """Test quand privacy est explicitement False."""
        from cptcopro.utils.privacy import is_privacy_enabled, SESSION_KEY_PRIVACY

        mock_session = {SESSION_KEY_PRIVACY: False}
        with patch("cptcopro.utils.privacy.st.session_state", mock_session):
            result = is_privacy_enabled()

        assert result is False

    def test_privacy_definie_true(self):
        """Test quand privacy est True."""
        from cptcopro.utils.privacy import is_privacy_enabled, SESSION_KEY_PRIVACY

        mock_session = {SESSION_KEY_PRIVACY: True}
        with patch("cptcopro.utils.privacy.st.session_state", mock_session):
            result = is_privacy_enabled()

        assert result is True


class TestPreparerDfPourGraphe:
    """Tests pour la fonction preparer_df_pour_graphe."""

    def test_graphe_confidentialite_desactivee(self):
        """Test quand le mode confidentiel est désactivé."""
        from cptcopro.utils.privacy import preparer_df_pour_graphe

        df = pd.DataFrame(
            {"proprietaire": ["Jean Dupont", "Marie Martin"], "debit": [100, 200]}
        )

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=False):
            result = preparer_df_pour_graphe(df, "proprietaire")

        # Le DataFrame doit être inchangé
        assert result["proprietaire"].iloc[0] == "Jean Dupont"
        assert result["proprietaire"].iloc[1] == "Marie Martin"

    def test_graphe_confidentialite_activee(self):
        """Test quand le mode confidentiel est activé."""
        from cptcopro.utils.privacy import preparer_df_pour_graphe

        df = pd.DataFrame(
            {"proprietaire": ["Jean Dupont", "Marie Martin"], "debit": [100, 200]}
        )

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = preparer_df_pour_graphe(df, "proprietaire")

        # Les noms doivent être remplacés par "Copro X"
        assert result["proprietaire"].iloc[0] == "Copro 1"
        assert result["proprietaire"].iloc[1] == "Copro 2"
        # Le débit doit rester inchangé
        assert result["debit"].iloc[0] == 100

    def test_graphe_identifiants_uniques(self):
        """Test que les identifiants sont uniques même avec doublons."""
        from cptcopro.utils.privacy import preparer_df_pour_graphe

        df = pd.DataFrame(
            {
                "proprietaire": ["Jean Dupont", "Jean Dupont", "Marie Martin"],
                "date": ["2024-01", "2024-02", "2024-01"],
                "debit": [100, 150, 200],
            }
        )

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = preparer_df_pour_graphe(df, "proprietaire")

        # Les deux Jean Dupont doivent avoir le même identifiant
        assert result["proprietaire"].iloc[0] == "Copro 1"
        assert result["proprietaire"].iloc[1] == "Copro 1"
        assert result["proprietaire"].iloc[2] == "Copro 2"

    def test_graphe_df_vide(self):
        """Test avec DataFrame vide."""
        from cptcopro.utils.privacy import preparer_df_pour_graphe

        df = pd.DataFrame()

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = preparer_df_pour_graphe(df, "proprietaire")

        assert result.empty

    def test_graphe_colonne_manquante(self):
        """Test avec colonne d'identifiant manquante."""
        from cptcopro.utils.privacy import preparer_df_pour_graphe

        df = pd.DataFrame({"nom": ["Jean Dupont"], "debit": [100]})

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = preparer_df_pour_graphe(df, "proprietaire")

        # La colonne nom doit rester inchangée car "proprietaire" n'existe pas
        assert result["nom"].iloc[0] == "Jean Dupont"

    def test_graphe_avec_colonnes_sensibles_additionnelles(self):
        """Test avec colonnes sensibles additionnelles."""
        from cptcopro.utils.privacy import preparer_df_pour_graphe

        df = pd.DataFrame(
            {"proprietaire": ["Jean Dupont"], "code": ["ABC123"], "debit": [100]}
        )

        with patch("cptcopro.utils.privacy.is_privacy_enabled", return_value=True):
            result = preparer_df_pour_graphe(
                df, "proprietaire", colonnes_sensibles=["code"]
            )

        assert result["proprietaire"].iloc[0] == "Copro 1"
        assert result["code"].iloc[0] == "●●●●●●"
        assert result["debit"].iloc[0] == 100
