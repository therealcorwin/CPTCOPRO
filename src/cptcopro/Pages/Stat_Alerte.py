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
    query = "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, debit as Debit, type_alerte AS TypeApt, first_detection AS FirstDetection, last_detection AS LastDetection, occurence AS Occurence FROM alertes_debit_eleve"
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

def recup_suivi_alertes(db_path: Path) -> pd.DataFrame:
    query = """
        SELECT date_releve, nombre_alertes, total_debit,
               nb_2p, nb_3p, nb_4p, nb_5p, nb_na,
               debit_2p, debit_3p, debit_4p, debit_5p, debit_na
        FROM suivi_alertes 
        ORDER BY date_releve DESC
    """
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

# Récupérer les valeurs du dernier relevé (avec gestion des colonnes manquantes)
def get_val(col, default=0):
    if col in suivi_alerte.columns and not suivi_alerte.empty:
        val = suivi_alerte[col].iat[0]
        return val if pd.notna(val) else default
    return default

def get_delta(col):
    if col in suivi_alerte.columns and len(suivi_alerte) >= 2:
        curr = suivi_alerte[col].iat[0] or 0
        prev = suivi_alerte[col].iat[1] or 0
        return curr - prev
    return 0

suivi_alerte = recup_suivi_alertes(DB_PATH)
alertes_df, total_debit_df = recup_alertes(DB_PATH)

# Section statistiques par type d'appartement
if not suivi_alerte.empty:
    st.markdown("#### Répartition par type d'appartement")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("2 pièces", value=int(get_val("nb_2p")), delta=int(get_delta("nb_2p")), delta_color="inverse")
        style_metric_cards(background_color= "#292D34")
    with col2:
        st.metric("3 pièces", value=int(get_val("nb_3p")), delta=int(get_delta("nb_3p")), delta_color="inverse")
        style_metric_cards(background_color= "#292D34")
    with col3:
        st.metric("4 pièces", value=int(get_val("nb_4p")), delta=int(get_delta("nb_4p")), delta_color="inverse")
        style_metric_cards(background_color= "#292D34")
    with col4:
        st.metric("5 pièces", value=int(get_val("nb_5p")), delta=int(get_delta("nb_5p")), delta_color="inverse")
        style_metric_cards(background_color= "#292D34")
    with col5:
        st.metric("Non classé", value=int(get_val("nb_na")), delta=int(get_delta("nb_na")), delta_color="inverse") 
        style_metric_cards(background_color= "#292D34")


if not alertes_df.empty:
    # Filtre par type d'appartement
    types_disponibles = ["Tous"] + sorted(alertes_df["TypeApt"].dropna().unique().tolist())
    type_selectionne = st.selectbox("Filtrer par type d'appartement", types_disponibles)
    
    if type_selectionne != "Tous":
        alertes_filtrees = alertes_df[alertes_df["TypeApt"] == type_selectionne]
    else:
        alertes_filtrees = alertes_df
    
    st.markdown("#### Détail des alertes")
    st.dataframe(
        alertes_filtrees[["Proprietaire", "Code", "Debit", "TypeApt", "FirstDetection", "LastDetection", "Occurence"]]
        .sort_values(by="Debit", ascending=False),
        column_config={
            "Proprietaire": "Propriétaire",
            "TypeApt": "Type Apt",
            "Debit": st.column_config.NumberColumn("Débit", format="%.2f €"),
            "FirstDetection": "Première détection",
            "LastDetection": "Dernière détection",
            "Occurence": "Occurrences"
        },
        hide_index=True
    )
    
    # Graphique des occurrences par copropriétaire
    fig = px.bar(alertes_filtrees, x='Proprietaire', y='Occurence', color='TypeApt',
                 title='Nombre d\'occurrences par copropriétaire')
    st.plotly_chart(fig, width="stretch")
    
    # Graphique de répartition par type d'appartement
    if len(alertes_df["TypeApt"].unique()) > 1:
        repartition = alertes_df.groupby("TypeApt").agg(
            NbAlertes=("TypeApt", "count"),
            TotalDebit=("Debit", "sum")
        ).reset_index()
        fig_pie = px.pie(repartition, values='NbAlertes', names='TypeApt',
                         title='Répartition des alertes par type d\'appartement')
        st.plotly_chart(fig_pie, width="stretch")
