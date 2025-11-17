import streamlit as st
import sqlite3
import pandas as pd
from loguru import logger
from pathlib import Path
import plotly.express as px
from typing import List

DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

@st.cache_data
def load_all_charges_data(db_path: Path) -> pd.DataFrame:
    """Charge toutes les données de charges depuis la vue vw_charge_coproprietaires."""
    sql = "SELECT nom_proprietaire, code_proprietaire, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires"
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(sql, conn)
    # Renommer pour la cohérence avec le reste du code
    df = df.rename(columns={"nom_proprietaire": "proprietaire", "code_proprietaire": "code"})
    # Convertir la date une seule fois
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"])


st.set_page_config(page_title="Recherche Info Copropriétaires", layout="wide")
st.title("Recherche Info Copropriétaires")

st.divider()
charges_df = load_all_charges_data(DB_PATH)
proprietaires_df = charges_df[["proprietaire", "code"]].drop_duplicates().reset_index(drop=True)

st.subheader("Recherche informations sur les copropriétaires")
proprietaire_input = st.text_input("Entrez le nom du copropriétaire à rechercher :").strip()

proprietaires_selection: List[str] = []
if proprietaire_input:
    # Filtrer la liste de noms de copropriétaires
    options = [p for p in proprietaires_df["proprietaire"].values if proprietaire_input.lower() in p.lower()]

    if options:
        st.markdown(f"### Résultats pour '{proprietaire_input}':")
        # Afficher les informations uniques pour les propriétaires trouvés
        info_df = charges_df[charges_df["proprietaire"].isin(options)]
        info_df = info_df[["proprietaire", "code", "num_apt", "type_apt"]].drop_duplicates().reset_index(drop=True)
        st.dataframe(info_df)

        # Permettre de sélectionner un ou plusieurs propriétaires parmi les résultats
        proprietaires_selection = st.multiselect(
            "Sélectionnez un ou plusieurs copropriétaires à tracer",
            options=options,
            default=options,
        )
    else:
        st.warning(f"Aucun copropriétaire trouvé avec le nom '{proprietaire_input}'.")
else:
    st.info("Veuillez entrer un nom de copropriétaire pour rechercher.")

st.divider()
st.subheader("Suivi des charges pour le(s) copropriétaire(s) sélectionné(s)")
if proprietaires_selection:
    # Filtrer le DataFrame principal au lieu de faire un appel BDD
    charges_df = charges_df[charges_df["proprietaire"].isin(proprietaires_selection)]

    if charges_df.empty:
        st.warning("Aucune charge trouvée pour le(s) copropriétaire(s) sélectionné(s).")
    else:
        # Agréger par date et par propriétaire (somme des debits)
        charges_df_sorted = charges_df.sort_values(["proprietaire", "date"], ascending=[True, False])
        agg = charges_df_sorted.groupby([charges_df_sorted["date"].dt.date, "proprietaire"]).agg({"debit": "sum"}).reset_index()
        logger.info(agg)
        # Tracer l'évolution du débit par date (une courbe par propriétaire)
        fig = px.line(agg, x="date", y="debit", color="proprietaire", markers=True)
        fig.update_layout(title="Évolution du débit par date", xaxis_title="Date", yaxis_title="Débit")
        st.plotly_chart(fig, use_container_width=True)

        # Afficher le tableau agrégé
        st.markdown("**Tableau agrégé par date et propriétaire**")
        st.dataframe(agg.sort_values(by=["date", "proprietaire"], ascending=[True, False]))

else:
    st.info("Aucun propriétaire sélectionné pour le tracé.")
