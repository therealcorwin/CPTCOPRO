"""Page d'analyse graphique comparative des débits des copropriétaires."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import fetch_dataframe, normalize_date_columns
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
    preparer_df_pour_graphe,
)
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


def _normalize_date_range(date_val: object, min_d: object, max_d: object) -> tuple[object, object]:
    """Extrait en toute sécurité start_date et end_date d'un composant date."""
    if isinstance(date_val, (tuple, list)):
        if len(date_val) >= 2:
            return date_val[0], date_val[1]
        elif len(date_val) == 1:
            return date_val[0], max_d
        return min_d, max_d
    elif date_val is not None:
        return date_val, max_d
    return min_d, max_d


@st.cache_data(ttl=300, show_spinner=False)
def load_data() -> pd.DataFrame:
    """Charge les données des charges depuis MariaDB."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, "
            "num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires"
        )
        df = fetch_dataframe(cur)
    df = normalize_date_columns(df, ["date"])
    if "date" in df.columns:
        df = df.dropna(subset=["date"]).sort_values("date")
    return df


render_header(
    "📈 Analyse Graphique des Débits",
    "Comparaison temporelle ciblée des soldes débiteurs entre copropriétaires",
)

df = load_data()


if df.empty:
    st.warning("⚠️ Aucune donnée disponible pour l'analyse graphique.")
    st.stop()

date_min = df["date"].min()
date_max = df["date"].max()
derniere_date = df["date"].max()

# --- Barre de filtres principale ---
col_c1, col_c2, col_c3 = st.columns([2.2, 0.9, 0.9], gap="medium")

with col_c1:
    top_10_debit_owners = (
        df[df["date"] == derniere_date].nlargest(10, "debit")["proprietaire"].tolist()
    )
    all_owners_sorted = sorted(df["proprietaire"].unique())
    selected_proprietaires = st.multiselect(
        "Copropriétaires à comparer (Top 10 pré-sélectionné par défaut) :",
        options=all_owners_sorted,
        default=top_10_debit_owners,
        key="courbe_charge_proprietaires",
    )

with col_c2:
    start_date = st.date_input(
        "Date début",
        value=date_min,
        min_value=date_min,
        max_value=date_max,
        format="DD/MM/YYYY",
        key="courbe_charge_start_date",
    )

with col_c3:
    end_date = st.date_input(
        "Date fin",
        value=date_max,
        min_value=date_min,
        max_value=date_max,
        format="DD/MM/YYYY",
        key="courbe_charge_end_date",
    )

if start_date is None:
    start_date = date_min
if end_date is None:
    end_date = date_max

if start_date > end_date:
    st.warning("⚠️ La date de début est postérieure à la date de fin. La période a été réajustée.")
    start_date, end_date = min(start_date, end_date), max(start_date, end_date)

filtered_df = df[
    df["proprietaire"].isin(selected_proprietaires)
    & (df["date"] >= start_date)
    & (df["date"] <= end_date)
]

st.divider()

if filtered_df.empty:
    st.warning("Aucune donnée correspondant aux critères sélectionnés.")
else:
    fig = px.line(
        preparer_df_pour_graphe(filtered_df, "proprietaire"),
        x="date",
        y="debit",
        color="proprietaire",
        title="Évolution comparée des débits (€)",
        markers=True,
    )
    fig = apply_plotly_theme(fig)
    fig.update_layout(
        height=520,
        xaxis_title="Date",
        yaxis_title="Débit (€)",
        margin=dict(l=20, r=20, t=50, b=90),
        title=dict(
            text="Évolution comparée des débits (€)",
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

    with st.expander("📋 Données filtrées associées au graphique"):
        st.dataframe(
            appliquer_confidentialite(
                filtered_df.sort_values(by=["date", "proprietaire"], ascending=[False, True])
            ),
            width="stretch",
            hide_index=True,
            column_config={
                "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "proprietaire": st.column_config.TextColumn("Copropriétaire"),
                "debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €"),
                "credit": st.column_config.NumberColumn("Crédit (€)", format="%.2f €"),
            },
        )
