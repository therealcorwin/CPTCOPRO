import streamlit as st
import sqlite3
import loguru
from pathlib import Path
import pandas as pd

pd.set_option('display.max_rows', None)
DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

def affiche_copro(DB_PATH) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    requete = "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, type_apt AS Type, num_apt AS Numero,last_check AS Date FROM coproprietaires"
    liste_coproprietaires = pd.read_sql_query(requete, conn)
    conn.close()
    return liste_coproprietaires


if __name__ == "__main__":
    loguru.logger.info("Starting Streamlit app for coproprietaires display")
    df = affiche_copro(DB_PATH)
    st.title("Liste des copropriétaires")

    gauche,centre, droite = st.columns(3)

    with gauche:
        proprietaires = st.multiselect(
            "Filtrer par copropriétaire",
            options=df["Proprietaire"].unique(),
            default=df["Proprietaire"].unique(),
        )
    with centre:
        code = st.multiselect(
            "Filtrer par code",
            options=df["Code"].unique(),
            default=df["Code"].unique(),
        )
    with droite:
        type_apt = st.multiselect(
            "Filtrer par type d'appartement",
            options=df["Type"].unique(),
            default=df["Type"].unique(),
        )

    # Pour afficher le dataframe complet dans Streamlit avec une hauteur dynamique,
    # On calcule le nombre de lignes du dataframe (+ 1 pour l'en-tête) * nbre pixels en hauteurs par ligne.
    #height = (len(df) + 1) * 35
    #st.dataframe(df, height=height, use_container_width=True)
    st.table(df.query("Proprietaire == @proprietaires & Code == @code & Type == @type_apt"))