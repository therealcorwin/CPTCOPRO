import streamlit as st
import sqlite3
import pandas as pd
import loguru
from pathlib import Path
import datetime as dt

DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"


@st.cache_data
def load_charges(db_path: Path) -> pd.DataFrame:
    """Charger la vue `vw_charge_coproprietaires` depuis SQLite et normaliser la colonne date."""
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires",
            conn,
        )
    # Normaliser la date et convertir en date (sans heure)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    return df


st.set_page_config(page_title="Suivi de charge détaillé", layout="wide")
st.title("Suivi de charge détaillé des copropriétaires")
df = load_charges(DB_PATH)
st.divider()
gauche, centre, droite = st.columns(3)
with gauche:
    proprietaires = st.multiselect(
        "Filtrer par copropriétaire", options=df["proprietaire"].unique(), default=df["proprietaire"].unique()
    )
with centre:
    code = st.multiselect("Filtrer par code", options=df["code"].unique(), default=df["code"].unique())
with droite:
    type_apt = st.multiselect(
        "Filtrer par type d'appartement", options=df["type_apt"].unique(), default=df["type_apt"].unique()
    )
date_min = df["date"].min()
date_max = df["date"].max()
date_range = st.date_input("Sélectionner une plage de dates", value=[date_min, date_max])
loguru.logger.info("Starting Streamlit app for coproprietaires display")

# Normaliser la valeur retournée par `st.date_input` de manière robuste.
# Car dans streamlit, si la date de début et de fin sont identiques, cela fait une erreur.
# `date_input` peut renvoyer :
# - une `date` unique,
# - une liste/tuple `[start_date, end_date]`,
# - ou dans certains cas des objets imbriqués (tuple/list contenant des dates).


def _to_date(val):
    """Convertit `val` en `datetime.date` si possible, en dé-nested les listes/tuples."""
    if val is None:
        return None
    # Dé-nest si list/tuple
    if isinstance(val, (list, tuple)) and len(val) > 0:
        return _to_date(val[0])
    # pandas Timestamp -> date (use the already-imported `pd` and avoid broad excepts)
    if hasattr(pd, "Timestamp") and isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, dt.datetime):
        return val.date()
    if isinstance(val, dt.date):
        return val
    return None

if isinstance(date_range, (list, tuple)):
    if len(date_range) >= 2:
        start_date = _to_date(date_range[0])
        end_date = _to_date(date_range[1])
    elif len(date_range) == 1:
        start_date = end_date = _to_date(date_range[0])
    else:
        start_date, end_date = date_min, date_max
else:
    start_date = end_date = _to_date(date_range)

# fallback si l'un des deux est None
if start_date is None:
    start_date = date_min
if end_date is None:
    end_date = date_max
# Construire un masque explicite avec .isin() pour gérer les multiselects
mask = (
    df["proprietaire"].isin(proprietaires)
    & df["code"].isin(code)
    & df["type_apt"].isin(type_apt)
    & (df["date"] >= start_date)
    & (df["date"] <= end_date)
)
filtered_df = df.loc[mask].copy()
filtered_df = filtered_df.sort_values(["date", "proprietaire"], ascending=[False, True])  # tri par défaut
st.dataframe(filtered_df)
