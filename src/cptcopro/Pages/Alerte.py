import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path
from streamlit_extras.metric_cards import style_metric_cards

# Import du module de chemins portables
try:
    from cptcopro.utils.paths import get_db_path
    DB_PATH = get_db_path()
except ImportError:
    # Fallback pour le mode développement
    DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

@st.cache_data()
def recup_alertes(db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    query = "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, debit as Debit, first_detection AS FirstDetection, last_detection AS LastDetection, occurence AS Occurence FROM alertes_debit_eleve"
    query2 = "select SUM(debit) as TotalDebit FROM alertes_debit_eleve"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            recup_alerte = pd.read_sql_query(query, conn)
            recup_total_debit = pd.read_sql_query(query2, conn)
        finally:
            conn.close()
        return recup_alerte, recup_total_debit
    except sqlite3.Error as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur inattendue : {e}")
        return pd.DataFrame(), pd.DataFrame()


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
        st.error(f"Impossible de récupérer les débits : {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur inattendue lors de la récupération des débits : {e}")
        return pd.DataFrame()

def recup_suivi_alertes(db_path: Path) -> pd.DataFrame:
    query = " SELECT date_releve, nombre_alertes, total_debit FROM suivi_alertes ORDER BY date_releve DESC"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            suivi_df = pd.read_sql_query(query, conn)
        finally:
            conn.close()
        return suivi_df
    except sqlite3.Error as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur inattendue : {e}")
        return pd.DataFrame()

st.set_page_config(page_title="Alertes Débit Élevé", layout="wide")
st.title("Alertes Débit Élevé des Copropriétaires") 

alertes_df, sommealertes_df = recup_alertes(DB_PATH)
suivi_alerte = recup_suivi_alertes(DB_PATH)

date_releve = suivi_alerte["date_releve"].iat[0] if not suivi_alerte.empty else "N/A"
date_dernier_releve = suivi_alerte["date_releve"].iat[1] if len(suivi_alerte) >=2 else "N/A"

nombre_alerte = suivi_alerte["nombre_alertes"].iat[0] if not suivi_alerte.empty else 0
dernier_nombre_alerte = suivi_alerte["nombre_alertes"].iat[1] if len(suivi_alerte) >=2 else 0
delta_nombre_alerte = nombre_alerte - dernier_nombre_alerte

somme_alerte = suivi_alerte["total_debit"].iat[0] if not suivi_alerte.empty else 0
dernier_somme_alerte = suivi_alerte["total_debit"].iat[1] if len(suivi_alerte) >=2 else 0
delta_somme_alerte = somme_alerte - dernier_somme_alerte


gauche,centre, droite = st.columns(3)

with st.container():
    with gauche:
        st.space("small")
        st.metric("Date du dernier relevé", value=date_releve, delta=date_dernier_releve, delta_color="off")
        style_metric_cards(background_color= "#292D34")
    with centre:
        st.space("small")
        st.metric("Nombre d'alertes", value=nombre_alerte, delta=delta_nombre_alerte, delta_color="inverse")
        style_metric_cards(background_color= "#292D34")    
    with droite:
        st.space("small")
        st.metric("Nombre d'alertes", value=somme_alerte, delta=delta_somme_alerte, delta_color="inverse")
        style_metric_cards(background_color= "#292D34") 

if not alertes_df.empty:    
    st.markdown("#### Détail des alertes")
    st.dataframe(alertes_df[["Proprietaire", "Code", "Debit", "FirstDetection", "LastDetection"]].sort_values(by="Debit", ascending=False))
    # Utiliser directement les colonnes du DataFrame pour le graphique
    fig = px.bar(alertes_df, x='Proprietaire', y='Occurence', title='Nombre d\'occurrences par copropriétaire')
    st.plotly_chart(fig, width="stretch")

    # graphique des débits par date pour les propriétaires ayant une alerte ---
    codes_alertes = alertes_df["Code"].dropna().unique().tolist()
    debits_df = recup_debits_proprietaires_alertes(DB_PATH, codes_alertes)
    if not debits_df.empty:
        # Agréger le débit par date et par propriétaire
        try:
            agg = (
                debits_df.groupby(["date", "Proprietaire"])
                ["debit"].sum()
                .reset_index()
                .sort_values(["date", "Proprietaire"])
            )
            if not agg.empty:
                fig2 = px.line(agg, x="date", y="debit", color="Proprietaire",
                        title="Débit des copropriétaires en alerte")
                fig2.update_layout(xaxis_title="Date", yaxis_title="Débit (€)")
                st.plotly_chart(fig2, width="stretch")
        except Exception as e:
            st.warning(f"Impossible de générer le graphique des débits : {e}")
else:
    st.markdown("Aucune alerte de débit élevé trouvée.")
