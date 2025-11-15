import streamlit as st
from pathlib import Path
import sqlite3
import pandas as pd
import loguru
import plotly.express as px

DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

@st.cache_data
def load_data(db_path):
    """Charge les données depuis la base de données et les met en cache."""
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query("SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires", conn)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"]).sort_values("date")
    return df

st.set_page_config(page_title="Analyse des débits des Copropriétaires", layout="wide")
st.title("Analyse des débits des Copropriétaires")

if __name__ == "__main__":
    loguru.logger.info("Démarrage de la page d'analyse des débits.")
    df = load_data(DB_PATH)

    # --- Filtres ---
    st.sidebar.header("Filtres")

    # Calculer les 10 propriétaires avec le plus grand débit total pour la sélection par défaut
    top_10_debit_owners = df.groupby('proprietaire')['debit'].sum().nlargest(10).index.tolist()
    all_owners_sorted = sorted(df["proprietaire"].unique())

    selected_proprietaires = st.sidebar.multiselect(
        "Sélectionner un ou plusieurs propriétaires",
        options=all_owners_sorted,
        default=top_10_debit_owners
    )

    date_range = st.sidebar.date_input(
        "Sélectionner une plage de dates",
        value=(df["date"].min(), df["date"].max()),
        min_value=df["date"].min(),
        max_value=df["date"].max(),
    )

    # Si start_date = end_date) Streamlit retourne un single date au lieu d'un tuple
    # Pour eviter une erreur on verifie le type
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
    # --- Filtrage du DataFrame ---
        filtered_df = df[
            df["proprietaire"].isin(selected_proprietaires) &
            (df["date"] >= start_date) & (df["date"] <= end_date)
        ]
    else:
        start_date = end_date = date_range
            # --- Filtrage du DataFrame ---
        filtered_df = df[
        df["proprietaire"].isin(selected_proprietaires) &
        (df["date"] == start_date) & (df["date"] == end_date)
    ]


    # --- Création et affichage du graphique ---
    fig = px.line(filtered_df, x="date", y="debit", color="proprietaire", title="Évolution des débits par propriétaire", markers=False)
    st.plotly_chart(fig, use_container_width=True)

    # --- Affichage des données brutes ---
    with st.expander("Afficher les données filtrées"):
        st.dataframe(filtered_df.sort_values(by=['date', 'proprietaire'], ascending=[False, True]))
