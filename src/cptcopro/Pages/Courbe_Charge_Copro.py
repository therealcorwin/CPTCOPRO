import streamlit as st
from pathlib import Path
import sqlite3
import pandas as pd
import loguru
import plotly.express as px

# Import du module de chemins portables
try:
    from cptcopro.utils.paths import get_db_path
    DB_PATH = get_db_path()
except ImportError:
    # Fallback pour le mode développement
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

loguru.logger.info("Démarrage de la page d'analyse des débits.")
df = load_data(DB_PATH)
# --- Filtres ---
st.sidebar.header("Filtres")
# Calculer les 10 propriétaires avec le plus grand débit à la dernière date
derniere_date = df["date"].max()
top_10_debit_owners = df[df["date"] == derniere_date].nlargest(10, 'debit')['proprietaire'].tolist()
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
# Si start_date = end_date, Streamlit retourne un single date au lieu d'un tuple# Pour eviter une erreur on verifie le type
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

fig = px.line(filtered_df, x="date", y="debit", color="proprietaire", title="Évolution des débits par propriétaire", markers=False)
st.plotly_chart(fig, width="stretch")
# --- Affichage des données brutes ---
with st.expander("Afficher les données filtrées"):
    st.dataframe(filtered_df.sort_values(by=['date', 'proprietaire'], ascending=[False, True]))