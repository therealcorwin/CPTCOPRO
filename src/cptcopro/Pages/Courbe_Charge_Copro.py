import streamlit as st
from pathlib import Path
import sqlite3
import pandas as pd
import loguru
import plotly.express as px

# Import du module de chemins portables
try:
    from cptcopro.utils.paths import get_db_path
    from cptcopro.utils.privacy import (
        appliquer_confidentialite,
        preparer_df_pour_graphe,
    )

    DB_PATH = get_db_path()
except ImportError:
    # Fallback pour le mode développement
    DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"
    from cptcopro.utils.privacy import (
        appliquer_confidentialite,
        preparer_df_pour_graphe,
    )


def _get_db_cache_key(db_path: Path) -> int:
    try:
        return db_path.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=300, show_spinner=False)
def load_data(db_path: Path, db_cache_key: int):
    """Charge les données depuis la base de données et les met en cache."""
    del db_cache_key
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires",
            conn,
        )
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"]).sort_values("date")
    return df


st.title("Analyse des débits des Copropriétaires")

loguru.logger.info("Démarrage de la page d'analyse des débits.")
db_cache_key = _get_db_cache_key(DB_PATH)
df = load_data(DB_PATH, db_cache_key)

# --- Filtres ---
st.sidebar.header("Filtres")
# Calculer les 10 propriétaires avec le plus grand débit à la dernière date
derniere_date = df["date"].max()
top_10_debit_owners = (
    df[df["date"] == derniere_date].nlargest(10, "debit")["proprietaire"].tolist()
)
all_owners_sorted = sorted(df["proprietaire"].unique())
selected_proprietaires = st.sidebar.multiselect(
    "Sélectionner un ou plusieurs propriétaires",
    options=all_owners_sorted,
    default=top_10_debit_owners,
    key="courbe_charge_proprietaires",
)
date_range = st.sidebar.date_input(
    "Sélectionner une plage de dates",
    value=(df["date"].min(), df["date"].max()),
    min_value=df["date"].min(),
    max_value=df["date"].max(),
    key="courbe_charge_dates",
)
# Si start_date = end_date, Streamlit retourne un single date au lieu d'un tuple# Pour eviter une erreur on verifie le type
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
    # --- Filtrage du DataFrame ---
    filtered_df = df[
        df["proprietaire"].isin(selected_proprietaires)
        & (df["date"] >= start_date)
        & (df["date"] <= end_date)
    ]
else:
    start_date = end_date = date_range
    # --- Filtrage du DataFrame ---
    filtered_df = df[
        df["proprietaire"].isin(selected_proprietaires)
        & (df["date"] == start_date)
        & (df["date"] == end_date)
    ]

if filtered_df.empty:
    st.warning("Aucune donnée pour les filtres sélectionnés.")
else:
    fig = px.line(
        preparer_df_pour_graphe(filtered_df, "proprietaire"),
        x="date",
        y="debit",
        color="proprietaire",
        title="Évolution des débits par propriétaire",
        markers=False,
    )
    st.plotly_chart(fig, width="stretch")
# --- Affichage des données brutes ---
with st.expander("Afficher les données filtrées"):
    st.dataframe(
        appliquer_confidentialite(
            filtered_df.sort_values(
                by=["date", "proprietaire"], ascending=[False, True]
            )
        )
    )
