"""
Module de visualisation des données des copropriétaires avec Streamlit.

Ce script crée une application web pour afficher :
- L'évolution globale des débits et crédits de tous les copropriétaires.
- Les courbes de débit et crédit pour chaque copropriétaire sélectionné.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Chemin vers la base de données
DB_PATH = Path(__file__).parent / "coproprietaires.sqlite"


@st.cache_data
def charger_donnees(db_path: Path) -> pd.DataFrame:
    """
    Charge les données depuis la base de données SQLite.

    Args:
        db_path (Path): Chemin vers la base de données.

    Returns:
        pd.DataFrame: Un DataFrame contenant les données des copropriétaires.
    """
    if not db_path.exists():
        st.error(f"La base de données '{db_path}' est introuvable.")
        return pd.DataFrame()

    try:
        with sqlite3.connect(db_path) as conn:
            query = "SELECT code_proprietaire, nom_proprietaire, debit, credit, date FROM coproprietaires ORDER BY date ASC"
            df = pd.read_sql_query(query, conn)
    except sqlite3.Error as e:
        st.error(f"Erreur lors de la connexion à la base de données : {e}")
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"])
    return df


def main() -> None:
    """
    Fonction principale de l'application Streamlit.
    """
    st.set_page_config(layout="wide", page_title="Analyse des Soldes Copropriétaires")
    st.title("📈 Analyse des soldes des copropriétaires")

    df = charger_donnees(DB_PATH)

    if df.empty:
        st.warning("Aucune donnée à afficher.")
        return

    # --- Section des graphiques globaux ---
    st.header("Vue d'ensemble : Débits et Crédits Globaux")

    # Agréger les données par date
    df_global = df.groupby("date")[["debit", "credit"]].sum().reset_index()

    col1, col2 = st.columns(2)

    with col1:
        fig_debit_global = px.line(
            df_global,
            x="date",
            y="debit",
            title="Évolution du Débit Total",
            labels={"date": "Date", "debit": "Montant du Débit (€)"},
        )
        st.plotly_chart(fig_debit_global, use_container_width=True)

    with col2:
        fig_credit_global = px.line(
            df_global,
            x="date",
            y="credit",
            title="Évolution du Crédit Total",
            labels={"date": "Date", "credit": "Montant du Crédit (€)"},
        )
        st.plotly_chart(fig_credit_global, use_container_width=True)

    # --- Section des graphiques par copropriétaire ---
    st.header("Analyse par Copropriétaire")

    liste_coproprietaires = sorted(df["nom_proprietaire"].unique())
    selection_copros = st.multiselect(
        "Sélectionnez un ou plusieurs copropriétaires :",
        options=liste_coproprietaires,
    )

    if selection_copros:
        df_filtre = df[df["nom_proprietaire"].isin(selection_copros)]
        fig_individuel = px.line(
            df_filtre,
            x="date",
            y=["debit", "credit"],
            color="nom_proprietaire",
            title="Évolution des Débits et Crédits par Copropriétaire",
            labels={
                "value": "Montant (€)",
                "date": "Date",
                "variable": "Type de Mouvement",
            },
        )
        st.plotly_chart(fig_individuel, use_container_width=True)


if __name__ == "__main__":
    main()
