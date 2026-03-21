"""Module utilitaire pour la gestion de la confidentialité des données dans Streamlit.

Ce module fournit des fonctions pour masquer/anonymiser les données sensibles
des copropriétaires (nom, code, numéro d'appartement) dans l'interface Streamlit.

Usage:
    from cptcopro.utils.privacy import init_privacy_toggle, appliquer_confidentialite

    # Dans chaque page Streamlit, initialiser le toggle
    init_privacy_toggle()

    # Avant d'afficher un DataFrame
    df_affiche = appliquer_confidentialite(df)
    st.dataframe(df_affiche)
"""

import hashlib
import unicodedata
import streamlit as st
import pandas as pd
from typing import Literal

# Liste des colonnes sensibles à masquer (noms normalisés en lowercase sans accent)
COLONNES_SENSIBLES_NORMALIZED = [
    "proprietaire",
    "nom_proprietaire",
    "code",
    "code_proprietaire",
    "num_apt",
    "numero",
]


def _normalize(s: str) -> str:
    """Normalise une chaîne pour comparaison (minuscules, sans accents)."""
    # NFD décompose les accents, puis on filtre les caractères de combinaison
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# Clé de session pour l'état du toggle
SESSION_KEY_PRIVACY = "masquer_donnees_sensibles"


def init_privacy_toggle() -> bool:
    """Initialise et affiche le toggle de confidentialité sur la page.

    Crée une checkbox permettant à l'utilisateur d'activer
    ou désactiver le masquage des données sensibles. L'état est persisté
    dans `st.session_state`.

    Returns:
        bool: True si le mode confidentiel est activé, False sinon.

    Example:
        >>> init_privacy_toggle()
        >>> if st.session_state.masquer_donnees_sensibles:
        ...     st.info("Mode confidentiel activé")
    """
    # Utiliser key= pour que Streamlit gère automatiquement le session_state
    checked = st.checkbox(
        "🔒 Masquer données sensibles",
        key=SESSION_KEY_PRIVACY,
        help="Masque les noms, codes et numéros d'appartement des copropriétaires",
    )

    if checked:
        st.info(
            "✅ Mode confidentiel activé - Les données sensibles sont masquées sur toutes les pages"
        )

    return checked


def is_privacy_enabled() -> bool:
    """Vérifie si le mode confidentiel est activé.

    Returns:
        bool: True si le mode confidentiel est activé.
    """
    return st.session_state.get(SESSION_KEY_PRIVACY, False)


def anonymiser(valeur, mode: Literal["masque", "initiales", "hash"] = "masque") -> str:
    """Anonymise une valeur selon le mode choisi.

    Args:
        valeur: La valeur à anonymiser.
        mode: Le mode d'anonymisation :
            - "masque": Remplace par des points (●●●●●●)
            - "initiales": Garde uniquement les initiales (J. D.)
            - "hash": Génère un hash court (8 caractères)

    Returns:
        str: La valeur anonymisée.

    Example:
        >>> anonymiser("Jean Dupont", "initiales")
        "J. D."
        >>> anonymiser("Jean Dupont", "masque")
        "●●●●●●"
    """
    if pd.isna(valeur) or valeur is None:
        return valeur

    valeur_str = str(valeur)
    if not valeur_str.strip():
        return valeur

    if mode == "masque":
        return "●●●●●●"
    elif mode == "initiales":
        parts = valeur_str.split()
        if parts:
            return " ".join(p[0].upper() + "." for p in parts if p)
        return "●"
    elif mode == "hash":
        return hashlib.md5(valeur_str.encode()).hexdigest()[:8]
    return valeur_str


def appliquer_confidentialite(
    df: pd.DataFrame,
    colonnes: list[str] | None = None,
    mode: Literal["masque", "initiales", "hash"] = "masque",
) -> pd.DataFrame:
    """Applique le masquage des données sensibles si le mode confidentiel est activé.

    Cette fonction vérifie l'état du toggle de confidentialité et masque
    les colonnes sensibles si nécessaire.

    Args:
        df: Le DataFrame à traiter.
        colonnes: Liste des colonnes à masquer. Si None, utilise COLONNES_SENSIBLES.
        mode: Le mode d'anonymisation à utiliser.

    Returns:
        pd.DataFrame: Une copie du DataFrame avec les données masquées,
                      ou le DataFrame original si le mode confidentiel est désactivé.

    Example:
        >>> df = pd.DataFrame({"proprietaire": ["Jean Dupont"], "debit": [100]})
        >>> df_masque = appliquer_confidentialite(df)
        >>> # Si mode confidentiel activé: proprietaire = "●●●●●●"
    """
    if not is_privacy_enabled():
        return df

    if df.empty:
        return df

    colonnes_a_masquer = (
        colonnes if colonnes is not None else COLONNES_SENSIBLES_NORMALIZED
    )
    df_copie = df.copy()

    # Comparer en normalisant les noms de colonnes (insensible à la casse et aux accents)
    for col in df_copie.columns:
        col_normalized = _normalize(col)
        if col_normalized in colonnes_a_masquer:
            df_copie[col] = df_copie[col].apply(lambda x: anonymiser(x, mode))

    return df_copie


def masquer_liste(
    valeurs: list,
    mode: Literal["masque", "initiales", "hash"] = "masque",
) -> list:
    """Masque une liste de valeurs si le mode confidentiel est activé.

    Utile pour masquer les options d'un selectbox ou multiselect.

    Args:
        valeurs: Liste de valeurs à masquer.
        mode: Le mode d'anonymisation.

    Returns:
        list: Liste masquée ou originale selon l'état du toggle.

    Example:
        >>> options = masquer_liste(["Jean Dupont", "Marie Martin"])
        >>> st.selectbox("Choisir", options)
    """
    if not is_privacy_enabled():
        return valeurs

    return [anonymiser(v, mode) for v in valeurs]


def creer_mapping_anonymise(
    valeurs: list,
    mode: Literal["masque", "initiales", "hash"] = "initiales",
) -> dict:
    """Crée un mapping entre valeurs originales et anonymisées.

    Utile pour les selectbox où on doit pouvoir retrouver la valeur originale.

    Args:
        valeurs: Liste de valeurs originales.
        mode: Le mode d'anonymisation.

    Returns:
        dict: Mapping {valeur_anonymisee: valeur_originale}
    """
    if not is_privacy_enabled():
        return {v: v for v in valeurs}

    # Pour éviter les collisions avec le mode masque, on ajoute un index
    mapping = {}
    for i, v in enumerate(valeurs):
        if mode == "masque":
            # Ajouter un suffixe numérique pour distinguer les valeurs masquées
            anon = f"●●●●●● ({i + 1})"
        else:
            anon = anonymiser(v, mode)
            # Gérer les collisions potentielles
            if anon in mapping:
                anon = f"{anon} ({i + 1})"
        mapping[anon] = v

    return mapping


def preparer_df_pour_graphe(
    df: pd.DataFrame,
    colonne_identifiant: str = "proprietaire",
    colonnes_sensibles: list[str] | None = None,
) -> pd.DataFrame:
    """Prépare un DataFrame pour l'affichage dans un graphe avec anonymisation.

    Contrairement à `appliquer_confidentialite`, cette fonction génère des
    identifiants uniques et distincts pour chaque valeur, ce qui permet
    d'avoir des légendes lisibles dans les graphes Plotly.

    Args:
        df: Le DataFrame source.
        colonne_identifiant: Colonne principale utilisée pour la légende du graphe.
        colonnes_sensibles: Colonnes additionnelles à anonymiser.

    Returns:
        pd.DataFrame: Copie du DataFrame avec identifiants anonymisés mais distincts.

    Example:
        >>> df = pd.DataFrame({"proprietaire": ["Jean", "Marie"], "debit": [100, 200]})
        >>> df_graphe = preparer_df_pour_graphe(df, "proprietaire")
        >>> # Si mode confidentiel: proprietaire = ["Copro 1", "Copro 2"]
        >>> fig = px.line(df_graphe, x="date", y="debit", color="proprietaire")
    """
    if not is_privacy_enabled():
        return df

    if df.empty:
        return df

    df_copie = df.copy()

    # Créer un mapping unique pour la colonne d'identifiant principale
    if colonne_identifiant in df_copie.columns:
        valeurs_uniques = df_copie[colonne_identifiant].unique()
        mapping = {v: f"Copro {i + 1}" for i, v in enumerate(valeurs_uniques)}
        df_copie[colonne_identifiant] = df_copie[colonne_identifiant].map(mapping)

    # Anonymiser les autres colonnes sensibles
    cols_a_masquer = colonnes_sensibles or []
    for col in cols_a_masquer:
        if col in df_copie.columns and col != colonne_identifiant:
            df_copie[col] = df_copie[col].apply(lambda x: anonymiser(x, "masque"))

    return df_copie
