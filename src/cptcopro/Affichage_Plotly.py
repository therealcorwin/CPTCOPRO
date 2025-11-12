"""
Affichage Plotly des débits par date depuis la vue `vw_charge_coproprietaires`.

Usage:
  poetry run streamlit run src/cptcopro/Affichage_Plotly.py

Le script :
 - récupère le chemin de la DB depuis la variable d'environnement CTPCOPRO_DB_PATH
   (sinon il tente `src/cptcopro/BDD/test.sqlite`)
 - exécute la requête : SELECT sum(debit) AS debit_sum, date FROM vw_charge_coproprietaires GROUP BY date
 - construit un graphique Plotly (line) date vs debit_sum et l'affiche avec Streamlit
"""

from pathlib import Path
import os
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
from loguru import logger

logger.remove()
logger = logger.bind(type_log="AFFICHAGE_PLOTLY")


def get_db_path() -> Path:
    env = os.environ.get("CTPCOPRO_DB_PATH")
    if env:
        return Path(env)
    # fallback to repository BDD/test.sqlite (used in tests) if present
    candidate = Path(__file__).resolve().parent / "BDD" / "test.sqlite"
    if candidate.exists():
        return candidate
    # last resort, coproprietaires.sqlite
    return Path(__file__).resolve().parent / "BDD" / "coproprietaires.sqlite"


def load_aggregated_data(db_path: Path) -> pd.DataFrame:
    query = "SELECT sum(debit) AS debit_sum, date FROM vw_charge_coproprietaires GROUP BY date"
    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "debit_sum" in df.columns:
        df["debit_sum"] = pd.to_numeric(df["debit_sum"], errors="coerce").fillna(0)
    # drop rows without a valid date
    df = df.dropna(subset=["date"]).sort_values("date")
    return df


def main():
    st.set_page_config(page_title="Débits par date", layout="wide")
    st.title("Evolution des débits par date")

    db_path = get_db_path()
    st.sidebar.markdown(f"**DB path:** {db_path}")

    if not db_path.exists():
        st.error(f"Fichier DB introuvable: {db_path}")
        logger.error("DB not found: {}", db_path)
        return

    try:
        df = load_aggregated_data(db_path)
    except Exception as e:
        st.error(f"Erreur lors de la lecture des données: {e}")
        logger.error("Erreur lecture DB: {e}")
        return

    if df.empty:
        st.info("Aucune donnée disponible dans la vue 'vw_charge_coproprietaires'.")
        return

    fig = px.line(df, x="date", y="debit_sum", title="Total des débits par date", markers=True)
    fig.update_layout(xaxis_title="Date", yaxis_title="Débit (somme)")

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Table des données" ):
        st.dataframe(df)


if __name__ == "__main__":
    main()
