import streamlit as st
import sqlite3
import pandas as pd
import loguru
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

with sqlite3.connect(DB_PATH) as conn:
    df = pd.read_sql_query("SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires", conn)

st.set_page_config(page_title="Suivi de charge détaillé", layout="wide")
st.title("Suivi de charge détaillé des copropriétaires")

st.divider()


gauche,centre, droite = st.columns(3)
with gauche:
    proprietaires = st.multiselect(
    "Filtrer par copropriétaire",
    options=df["proprietaire"].unique(),
    default=df["proprietaire"].unique(),
)
with centre:
    code= st.multiselect(
    "Filtrer par code",
    options=df["code"].unique(),
    default=df["code"].unique(),
)
with droite:
    type_apt= st.multiselect(
    "Filtrer par type d'appartement",
    options=df["type_apt"].unique(),
    default=df["type_apt"].unique(),
)
    
date_range = st.date_input(
    "Sélectionner une plage de dates",
    value=[df["date"].min(), df["date"].max()]
)

if __name__ == "__main__":
    loguru.logger.info("Starting Streamlit app for coproprietaires display")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["date"] = df["date"].dt.date  # Convertir en date sans heure
    df["date"].sort_values(ascending=False)
    st.dataframe(df.query("proprietaire == @proprietaires & code == @code & type_apt == @type_apt & date >= @date_range[0] & date <= @date_range[1]"))