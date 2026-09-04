import sqlite3
from pathlib import Path

import loguru
import pandas as pd
import plotly.express as px
import streamlit as st

# Import du module de chemins portables
try:
    from cptcopro.utils.paths import get_db_path

    DB_PATH = get_db_path()
except Exception as e:
    # Fallback si l'import échoue ou si get_db_path() lève une exception
    loguru.logger.warning(f"Failed to get DB path: {e}. Using fallback path.")
    DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"


def _get_db_cache_key(db_path: Path) -> int:
    try:
        return db_path.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=300, show_spinner=False)
def chargement_somme_debit_global(db_path: Path, db_cache_key: int) -> pd.DataFrame:
    del db_cache_key
    query = "SELECT sum(debit) AS 'debit global', date FROM vw_charge_coproprietaires GROUP BY date"
    conn = sqlite3.connect(str(db_path))
    try:
        debit_global = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    # Convertir la colonne date en datetime
    if "date" in debit_global.columns:
        debit_global["date"] = pd.to_datetime(debit_global["date"], errors="coerce")
    # Convertir la colonne debit global en numérique, en remplaçant les erreurs par NaN puis en remplissant les NaN par 0
    if "debit global" in debit_global.columns:
        debit_global["debit global"] = pd.to_numeric(
            debit_global["debit global"], errors="coerce"
        ).fillna(0)
    # supprimer les lignes sans date valide et trier par date
    debit_global = debit_global.dropna(subset=["date"]).sort_values("date")
    return debit_global


@st.cache_data(ttl=300, show_spinner=False)
def suivi_nbre_alertes(db_path: Path, db_cache_key: int) -> tuple[int, int]:
    """Récupère les deux derniers relevés d'alertes pour calculer le delta.

    Returns:
        Tuple (nombre_alertes_actuel, nombre_alertes_precedent)
    """
    del db_cache_key
    query = "SELECT nombre_alertes FROM suivi_alertes ORDER BY date_releve DESC LIMIT 2;"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            recup_alerte_df = pd.read_sql_query(query, conn)
            if recup_alerte_df.empty:
                return 0, 0
            # Dernier relevé
            actuel = (
                int(recup_alerte_df["nombre_alertes"].iat[0]) if len(recup_alerte_df) >= 1 else 0
            )
            # Avant-dernier relevé
            precedent = (
                int(recup_alerte_df["nombre_alertes"].iat[1])
                if len(recup_alerte_df) >= 2
                else actuel
            )
        finally:
            conn.close()
        return actuel, precedent
    except sqlite3.Error as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return 0, 0
    except Exception as e:
        st.error(f"Erreur inattendue : {e}")
        return 0, 0


try:
    from cptcopro.utils.ui_components import apply_plotly_theme, render_header
except ImportError:

    def render_header(
        title: str,
        subtitle: str | None = None,
        badge_text: str | None = None,
        badge_variant: str = "info",
        show_privacy_toggle: bool = True,
    ) -> None:
        st.title(title)
        if subtitle:
            st.caption(subtitle)

    def apply_plotly_theme(fig: object) -> object:
        return fig


loguru.logger.info("Starting Streamlit app for coproprietaires display")
db_cache_key = _get_db_cache_key(DB_PATH)
Charge_globale = chargement_somme_debit_global(DB_PATH, db_cache_key)
nbre_alerte, nbre_alerte_precedent = suivi_nbre_alertes(DB_PATH, db_cache_key)
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
