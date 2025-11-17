import streamlit as st
import loguru
import sqlite3
from pathlib import Path
import pandas as pd
import plotly.express as px

DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

def chargement_somme_debit_global(DB_PATH: Path) -> pd.DataFrame:
    query = "SELECT sum(debit) AS 'debit global', date FROM vw_charge_coproprietaires GROUP BY date"
    conn = sqlite3.connect(str(DB_PATH))
    try:
        debit_global = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    #Convertir la colonne date en datetime
    if "date" in debit_global.columns:
        debit_global["date"] = pd.to_datetime(debit_global["date"], errors="coerce")
    #Convertir la colonne debit global en numérique, en remplaçant les erreurs par NaN puis en remplissant les NaN par 0
    if "debit global" in debit_global.columns:
        debit_global["debit global"] = pd.to_numeric(debit_global["debit global"], errors="coerce").fillna(0)
    # supprimer les lignes sans date valide et trier par date
    debit_global = debit_global.dropna(subset=["date"]).sort_values("date")
    return debit_global

def recup_nbre_alertes(DB_PATH: Path) -> int:
    query = "SELECT COUNT(*) AS 'nombre d alertes' FROM alertes_debit_eleve"
    conn = sqlite3.connect(str(DB_PATH))
    try:
        nbre_alertes_df = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    if nbre_alertes_df.empty:
        return 0
    nbre_alertes = int(nbre_alertes_df["nombre d alertes"].item())
    if nbre_alertes == 0:
        return 0
    return nbre_alertes



loguru.logger.info("Starting Streamlit app for coproprietaires display")
Charge_globale = chargement_somme_debit_global(DB_PATH)
nbre_alertes = recup_nbre_alertes(DB_PATH)


if Charge_globale.empty:
    st.error("Aucune donnée disponible à afficher.")
    st.stop()

gauche,centre, droite = st.columns(3)

with st.container():
    with gauche:
        st.subheader(" Date :")
        st.subheader(Charge_globale["date"].iat[-1].strftime("%d/%m/%Y"), divider=True)
    with centre:
        st.subheader(" Débit global :")
        st.subheader(f'{Charge_globale["debit global"].iat[-1]:.2f}', divider=True)
    with droite:
        st.subheader(" Nombre d'alertes :")
        st.subheader(nbre_alertes, divider=True)

st.markdown("Evolution des débits globaux de l'ensemble des copropriétaires")
chart = px.line(Charge_globale, x="date", y="debit global", title="Evolution des débits globaux", markers=True)
st.plotly_chart(chart, use_container_width=True)
with st.expander("Table des données" ):
    st.dataframe(Charge_globale)