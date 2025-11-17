import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

def recup_alertes(db_path: Path) -> pd.DataFrame:
    query = "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, debit as Debit, first_detection AS FirstDetection, last_detection AS LastDetection, occurence AS Occurence FROM alertes_debit_eleve"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            recup_alerte = pd.read_sql_query(query, conn)
        finally:
            conn.close()
        return recup_alerte
    except sqlite3.Error as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur inattendue : {e}")
        return pd.DataFrame()


def recup_debits_proprietaires_alertes(db_path: Path, codes: list) -> pd.DataFrame:
    """Récupère les débits par date pour la liste de codes de propriétaires fournie.
    Renvoie un DataFrame avec les colonnes ['Code', 'Proprietaire', 'date', 'debit'].
    """
    if not codes:
        return pd.DataFrame(columns=["Code", "Proprietaire", "date", "debit"])
    placeholders = ",".join(["?" for _ in codes])
    query = (
        "SELECT code_proprietaire AS Code, nom_proprietaire AS Proprietaire, date, debit "
        "FROM vw_charge_coproprietaires "
        f"WHERE code_proprietaire IN ({placeholders}) "
        "ORDER BY date ASC"
    )
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            df = pd.read_sql_query(query, conn, params=codes)
        finally:
            conn.close()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
        return df
    except sqlite3.Error as e:
        st.warning(f"Impossible de récupérer les débits : {e}")
        return pd.DataFrame()
    except Exception as e:
        st.warning(f"Erreur inattendue lors de la récupération des débits : {e}")
        return pd.DataFrame()

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

    # --- Nouveau : graphique des débits par date pour les propriétaires ayant une alerte ---
    codes_alertes = alertes_df["Code"].dropna().unique().tolist()
    debits_df = recup_debits_proprietaires_alertes(DB_PATH, codes_alertes)
    if not debits_df.empty:
        # Agréger le débit par date et par propriétaire
        try:
            agg = (
                debits_df.groupby(["date", "Proprietaire"], dropna=False)
                ["debit"].sum()
                .reset_index()
                .sort_values(["date", "Proprietaire"])
            )
            if not agg.empty:
                fig2 = px.line(agg, x="date", y="debit", color="Proprietaire",
                               title="Débit (somme) par date pour propriétaires alertés")
                fig2.update_layout(xaxis_title="Date", yaxis_title="Débit (€)")
                st.markdown("#### Débit par date pour propriétaires alertés")
                st.plotly_chart(fig2, use_container_width=True)
        except Exception as e:
            st.warning(f"Impossible de générer le graphique des débits : {e}")
else:
    st.markdown("Aucune alerte de débit élevé trouvée.")
