"""Page de suivi des alertes de débit élevé des copropriétaires."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import normalize_date_columns
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
    preparer_df_pour_graphe,
)
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


@st.cache_data(ttl=300, show_spinner=False)
def recup_alertes() -> tuple[pd.DataFrame, pd.DataFrame]:
    query = (
        "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, "
        "debit AS Debit, type_alerte AS TypeApt, first_detection AS FirstDetection, "
        "last_detection AS LastDetection, occurence AS Occurence "
        "FROM alertes_debit_eleve ORDER BY debit DESC"
    )
    query2 = "SELECT SUM(debit) AS TotalDebit FROM alertes_debit_eleve"
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            recup_alerte = pd.DataFrame(cur.fetchall())
            cur.execute(query2)
            recup_total_debit = pd.DataFrame(cur.fetchall())
        recup_alerte = normalize_date_columns(recup_alerte, ["FirstDetection", "LastDetection"])
        return recup_alerte, recup_total_debit
    except Exception as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def recup_debits_proprietaires_alertes() -> pd.DataFrame:
    """Récupère l'historique des débits pour les propriétaires actuellement en alerte."""
    query = (
        "SELECT c.code_proprietaire AS Code, c.nom_proprietaire AS Proprietaire, c.date, c.debit "
        "FROM vw_charge_coproprietaires c "
        "INNER JOIN alertes_debit_eleve a ON a.code_proprietaire = c.code_proprietaire "
        "ORDER BY c.date ASC"
    )
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            df = pd.DataFrame(cur.fetchall())
        return normalize_date_columns(df, ["date"])
    except Exception as e:
        st.error(f"Impossible de récupérer l'historique des débits : {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def recup_suivi_alertes() -> pd.DataFrame:
    query = """
        SELECT date_releve, nombre_alertes, total_debit,
               nb_2p, nb_3p, nb_4p, nb_5p, nb_na,
               debit_2p, debit_3p, debit_4p, debit_5p, debit_na
        FROM suivi_alertes
        ORDER BY date_releve DESC
    """
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            suivi_df = pd.DataFrame(cur.fetchall())
        return normalize_date_columns(suivi_df, ["date_releve"])
    except Exception as e:
        st.error(f"Erreur lors de la récupération du suivi des alertes : {e}")
        return pd.DataFrame()


render_header(
    "🚨 Alertes Débit Élevé",
    "Surveillance en temps réel des copropriétaires dépassant les seuils d'impayés définis",
)

alertes_df, sommealertes_df = recup_alertes()
suivi_alerte = recup_suivi_alertes()
debits_df = recup_debits_proprietaires_alertes()


# Données de synthèse temporelle
raw_date_releve = suivi_alerte["date_releve"].iat[0] if not suivi_alerte.empty else None
raw_date_precedent = suivi_alerte["date_releve"].iat[1] if len(suivi_alerte) >= 2 else None

date_releve_str = (
    raw_date_releve.strftime("%d/%m/%Y")
    if hasattr(raw_date_releve, "strftime")
    else (str(raw_date_releve) if raw_date_releve is not None else "N/A")
)
date_precedent_str = (
    raw_date_precedent.strftime("%d/%m/%Y")
    if hasattr(raw_date_precedent, "strftime")
    else (str(raw_date_precedent) if raw_date_precedent is not None else None)
)

nombre_alerte = (
    int(suivi_alerte["nombre_alertes"].iat[0]) if not suivi_alerte.empty else len(alertes_df)
)
dernier_nombre = (
    int(suivi_alerte["nombre_alertes"].iat[1]) if len(suivi_alerte) >= 2 else nombre_alerte
)
delta_nombre = nombre_alerte - dernier_nombre

total_debit_alerte = (
    float(suivi_alerte["total_debit"].iat[0])
    if not suivi_alerte.empty
    else (float(alertes_df["Debit"].sum()) if not alertes_df.empty else 0.0)
)
dernier_total = (
    float(suivi_alerte["total_debit"].iat[1]) if len(suivi_alerte) >= 2 else total_debit_alerte
)
delta_total = total_debit_alerte - dernier_total

# ============================================================================
# KPIS GLOBAUX
# ============================================================================
kpi1, kpi2, kpi3 = st.columns(3, gap="medium")

with kpi1:
    st.metric(
        "Date du relevé",
        value=date_releve_str,
        delta=f"Précédent : {date_precedent_str}" if date_precedent_str else None,
        delta_color="off",
    )

with kpi2:
    st.metric(
        "Copropriétaires en alerte",
        value=nombre_alerte,
        delta=f"{'+' if delta_nombre > 0 else ''}{delta_nombre}" if delta_nombre != 0 else None,
        delta_color="inverse",
        help="Nombre de copropriétaires dont le solde débiteur excède le seuil de leur type d'appartement.",
    )

with kpi3:
    st.metric(
        "Montant total des impayés critiques",
        value=f"{total_debit_alerte:,.2f} €".replace(",", " "),
        delta=f"{'+' if delta_total > 0 else ''}{delta_total:,.2f} €".replace(",", " ")
        if delta_total != 0
        else None,
        delta_color="inverse",
        help="Somme cumulée des débits de tous les copropriétaires en situation d'alerte.",
    )

st.divider()

# ============================================================================
# CONTENU PRINCIPAL
# ============================================================================
if alertes_df.empty:
    st.success(
        "🎉 **Excellente nouvelle !** Aucun copropriétaire n'est actuellement en situation d'alerte de débit élevé."
    )
else:
    st.subheader(f"📋 Détail des {len(alertes_df)} compte(s) en alerte active")

    alertes_affiche = appliquer_confidentialite(
        alertes_df[
            [
                "Proprietaire",
                "Code",
                "Debit",
                "TypeApt",
                "Occurence",
                "FirstDetection",
                "LastDetection",
            ]
        ].copy()
    )

    st.dataframe(
        alertes_affiche,
        width="stretch",
        hide_index=True,
        column_config={
            "Proprietaire": st.column_config.TextColumn("Copropriétaire", width="large"),
            "Code": st.column_config.TextColumn("Code", width="small"),
            "Debit": st.column_config.NumberColumn(
                "Débit actuel (€)", format="%.2f €", width="medium"
            ),
            "TypeApt": st.column_config.TextColumn("Type Lot", width="small"),
            "Occurence": st.column_config.NumberColumn("Occurrences (relevés)", width="small"),
            "FirstDetection": st.column_config.DateColumn(
                "1ère détection", format="DD/MM/YYYY", width="small"
            ),
            "LastDetection": st.column_config.DateColumn(
                "Dernière détection", format="DD/MM/YYYY", width="small"
            ),
        },
    )

    st.divider()

    # --- Graphique de suivi temporel des comptes en alerte ---
    if not debits_df.empty:
        st.subheader("📈 Évolution temporelle des comptes en alerte")
        try:
            agg = (
                debits_df.groupby(["date", "Proprietaire"])["debit"]
                .sum()
                .reset_index()
                .sort_values(["date", "Proprietaire"])
            )
            if not agg.empty:
                fig = px.line(
                    preparer_df_pour_graphe(agg, "Proprietaire"),
                    x="date",
                    y="debit",
                    color="Proprietaire",
                    title="Courbes des débits pour les copropriétaires en alerte (€)",
                    markers=True,
                )
                fig = apply_plotly_theme(fig)
                fig.update_layout(
                    height=520,
                    xaxis_title="Date de relevé",
                    yaxis_title="Débit (€)",
                    margin=dict(l=20, r=20, t=50, b=90),
                    title=dict(
                        text="Courbes des débits pour les copropriétaires en alerte (€)",
                        x=0.01,
                        xanchor="left",
                        y=0.98,
                        yanchor="top",
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="top",
                        y=-0.22,
                        xanchor="center",
                        x=0.5,
                        title=dict(text=""),
                    ),
                )
                st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"Impossible de générer le graphique : {e}")
