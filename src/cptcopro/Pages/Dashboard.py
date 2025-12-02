import streamlit as st
from streamlit_extras.metric_cards import style_metric_cards
import loguru
import sqlite3
from pathlib import Path
import pandas as pd
import plotly.express as px

DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

@st.cache_data()
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

@st.cache_data()
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

@st.cache_data()
def suivi_nbre_alertes(db_path: Path) -> int:
    query = "SELECT nombre_alertes FROM suivi_alertes ORDER BY date_releve DESC LIMIT 1;"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            recup_alerte_df = pd.read_sql_query(query, conn)
            recup_alerte = int(recup_alerte_df["nombre_alertes"].item())
            if recup_alerte == 0:
                return 0
        finally:
            conn.close()
        return recup_alerte
    except sqlite3.Error as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return 0
    except Exception as e:
        st.error(f"Erreur inattendue : {e}")
        return 0

loguru.logger.info("Starting Streamlit app for coproprietaires display")
Charge_globale = chargement_somme_debit_global(DB_PATH)
nbre_alerte = recup_nbre_alertes(DB_PATH)
suivi_alerte = suivi_nbre_alertes(DB_PATH)
delta_alerte = nbre_alerte - suivi_alerte
if Charge_globale.empty:
    st.error("Aucune donnée disponible à afficher.")
    st.stop()

st.image(Path(__file__).parent / "Assets" / "gb2.png", width= 1000)

gauche,centre, droite = st.columns(3)

with st.container():
    with gauche:
        st.space("small")
        date_dernier_releve = Charge_globale["date"].iat[-1].strftime("%d/%m/%Y")
        date_avant_dernier_releve = Charge_globale["date"].iat[-2].strftime("%d/%m/%Y") if len(Charge_globale) >=2 else "N/A"
        st.metric("Date du dernier relevé", value=date_dernier_releve, delta=date_avant_dernier_releve, delta_color="off")
        style_metric_cards(background_color= "#292D34")
    with centre:
        st.space("small")
        st.metric("Nombre d'alertes", value=nbre_alerte, delta=delta_alerte, delta_color="inverse")
        style_metric_cards(background_color= "#292D34")    
    with droite:
        st.space("small")
        # valeur la plus récente formatée
        charge_N = f'{Charge_globale["debit global"].iat[-1]:.2f}'
        # Vérifier qu'il existe au moins 2 lignes avant d'accéder à iat[-2]
        if len(Charge_globale) >= 2:
            charge_N_1 = f'{Charge_globale["debit global"].iat[-2]:.2f}'
            delta_val = Charge_globale["debit global"].iat[-1] - Charge_globale["debit global"].iat[-2]
            delta_charge = f'{delta_val:.2f}'
        else:
            # Valeur de repli : aucune valeur précédente -> ne pas afficher de delta
            charge_N_1 = None
            delta_charge = None
        st.metric(
            "CHARGE GLOBALE",
            value=charge_N,
            delta=delta_charge,
            delta_color="inverse",
            help="Si Indicateur vert, le débit global a diminué par rapport à la dernière mesure.",
        )
        style_metric_cards(background_color= "#292D34")


chart = px.line(Charge_globale, x="date", y="debit global", title="Evolution des débits des copropriétaires", markers=True)
st.plotly_chart(chart, width="stretch")
with st.expander("Table des données" ):
    st.dataframe(Charge_globale.sort_values(by="date", ascending=False))

if st.button("rerun"):
    st.rerun()
else:
    st.stop()
