import loguru
import pandas as pd
import plotly.express as px
import streamlit as st

from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import normalize_date_columns
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


@st.cache_data(ttl=300, show_spinner=False)
def chargement_somme_debit_global() -> pd.DataFrame:
    query = "SELECT sum(debit) AS 'debit global', date FROM vw_charge_coproprietaires GROUP BY date"
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            debit_global = pd.DataFrame(cur.fetchall())
        debit_global = normalize_date_columns(debit_global, ["date"])
        if "debit global" in debit_global.columns:
            debit_global["debit global"] = pd.to_numeric(
                debit_global["debit global"], errors="coerce"
            ).fillna(0)
        debit_global = debit_global.dropna(subset=["date"]).sort_values("date")
        return debit_global
    except Exception as e:
        st.error(f"Erreur chargement debit global : {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def suivi_nbre_alertes() -> tuple[int, int]:
    """Récupère les deux derniers relevés d'alertes pour calculer le delta.

    Returns:
        Tuple (nombre_alertes_actuel, nombre_alertes_precedent)
    """
    query = "SELECT nombre_alertes FROM suivi_alertes ORDER BY date_releve DESC LIMIT 2;"
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            rows = list(cur.fetchall())
        if not rows:
            return 0, 0
        actuel = int(rows[0]["nombre_alertes"]) if len(rows) >= 1 else 0
        precedent = int(rows[1]["nombre_alertes"]) if len(rows) >= 2 else actuel
        return actuel, precedent
    except Exception as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return 0, 0


loguru.logger.info("Starting Streamlit app for coproprietaires display")
Charge_globale = chargement_somme_debit_global()
nbre_alerte, nbre_alerte_precedent = suivi_nbre_alertes()
delta_alerte = nbre_alerte - nbre_alerte_precedent


render_header(
    "📊 Tableau de bord",
    "Synthèse financière et indicateurs clés de la copropriété",
)

if Charge_globale.empty:
    st.warning("Aucune donnée de charge disponible.")
    st.stop()

st.divider()

gauche, centre, droite = st.columns(3, gap="medium")

date_dernier_releve = Charge_globale["date"].iat[-1].strftime("%d/%m/%Y")
date_avant_dernier_releve = (
    Charge_globale["date"].iat[-2].strftime("%d/%m/%Y") if len(Charge_globale) >= 2 else None
)

with gauche:
    st.metric(
        "Dernier relevé",
        value=date_dernier_releve,
        delta=f"Précédent : {date_avant_dernier_releve}" if date_avant_dernier_releve else None,
        delta_color="off",
    )

with centre:
    st.metric(
        "Alertes actives",
        value=nbre_alerte,
        delta=delta_alerte,
        delta_color="inverse",
        help="Nombre de copropriétaires dont le débit dépasse le seuil configuré.",
    )

with droite:
    charge_n = Charge_globale["debit global"].iat[-1]
    delta_str: str | None = None
    if len(Charge_globale) >= 2:
        delta_val = charge_n - Charge_globale["debit global"].iat[-2]
        delta_str = f"{delta_val:,.2f} €".replace(",", " ")

    st.metric(
        "Débit global de la copropriété",
        value=f"{charge_n:,.2f} €".replace(",", " "),
        delta=delta_str,
        delta_color="inverse",
        help="Total cumulé des débits. En vert si le montant diminue par rapport au relevé précédent.",
    )

st.divider()

chart = px.line(
    Charge_globale,
    x="date",
    y="debit global",
    title="Évolution du débit global de la copropriété",
    markers=True,
)
chart.update_traces(line_color="#0284C7", marker=dict(size=7, color="#38BDF8"))
chart.update_layout(xaxis_title="Date de relevé", yaxis_title="Débit global (€)")
chart = apply_plotly_theme(chart)

st.plotly_chart(chart, width="stretch")

with st.expander("📋 Consulter l'historique complet des relevés"):
    st.dataframe(
        Charge_globale.sort_values(by="date", ascending=False),
        width="stretch",
        hide_index=True,
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "debit global": st.column_config.NumberColumn("Débit global (€)", format="%.2f €"),
        },
    )
