import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

def recup_alertes(DB_PATH: Path) -> pd.DataFrame:
    query = "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, debit as Debit, first_detection AS FirstDetection, last_detection AS LastDetection, occurence AS Occurence FROM alertes_debit_eleve"
    conn = sqlite3.connect(str(DB_PATH))
    try:
        recup_alerte = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    return recup_alerte

if __name__ == "__main__":
    st.set_page_config(page_title="Alertes Débit Élevé", layout="wide")
    st.title("Alertes Débit Élevé des Copropriétaires")

    alertes_df = recup_alertes(DB_PATH)

    st.markdown(f"### Nombre total d'alertes : {len(alertes_df)}")

    if not alertes_df.empty:
        st.markdown("#### Détail des alertes")
        st.dataframe(alertes_df[["Proprietaire", "Code", "Debit", "FirstDetection", "LastDetection"]])

        st.markdown("#### Répartition des alertes par copropriétaire")
        # Utiliser directement les colonnes du DataFrame pour le graphique
        fig = px.bar(alertes_df, x='Proprietaire', y='Occurence', title='Nombre d\'occurrences par copropriétaire')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("Aucune alerte de débit élevé trouvée.")