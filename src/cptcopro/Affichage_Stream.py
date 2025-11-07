import streamlit as st
import loguru
import sqlite3
import os
import pandas as pd


DB_PATH = os.path.join(os.path.dirname(__file__), "BDD", "test.sqlite")

with sqlite3.connect(DB_PATH) as conn:
    df = pd.read_sql_query("SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires", conn)

st.set_page_config(page_title="Copropriété Branchard", layout="wide") 
st.title("Tableau de bord de la copropriété")

st.divider()
st.sidebar.title("Paramètres de l'application")
proprietaires = st.sidebar.multiselect(
    "Filtrer par copropriétaire",
    options=df["proprietaire"].unique(),
    default=df["proprietaire"].unique(),
)
code= st.sidebar.multiselect(
    "Filtrer par code",
    options=df["code"].unique(),
    default=df["code"].unique(),
)
type_apt= st.sidebar.multiselect(
    "Filtrer par type d'appartement",
    options=df["type_apt"].unique(),
    default=df["type_apt"].unique(),
)

def affiche_copro(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires")
    rows = cur.fetchall()
    st.subheader("Liste des copropriétaires")
    for row in rows:
        st.write(row)
    conn.close()

with sqlite3.connect(DB_PATH) as conn:
    df = pd.read_sql_query("SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires", conn)


if __name__ == "__main__":
    loguru.logger.info("Starting Streamlit app for coproprietaires display")
    #affiche_copro(DB_PATH)
    st.dataframe(df)