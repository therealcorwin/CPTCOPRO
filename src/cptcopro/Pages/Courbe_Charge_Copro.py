"""Page d'analyse graphique comparative des débits des copropriétaires."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from cptcopro.utils.paths import get_db_path
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
    preparer_df_pour_graphe,
)
from cptcopro.utils.ui_components import apply_plotly_theme, render_header

DB_PATH = get_db_path()


def _get_db_cache_key(db_path: Path) -> int:
    try:
        return db_path.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=300, show_spinner=False)
def load_data(db_path: Path, db_cache_key: int) -> pd.DataFrame:
    """Charge les données des charges depuis SQLite."""
    del db_cache_key
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, "
            "num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires",
            conn,
        )
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"]).sort_values("date")
    return df


def _normalize_date_range(
    date_val: object, min_d: dt.date, max_d: dt.date
) -> tuple[dt.date, dt.date]:
    if isinstance(date_val, (tuple, list)):
        if len(date_val) >= 2:
            return date_val[0], date_val[1]
        elif len(date_val) == 1:
            return date_val[0], date_val[0]
        return min_d, max_d
    elif isinstance(date_val, dt.date):
        return date_val, date_val
    return min_d, max_d


render_header(
    "📈 Analyse Graphique des Débits",
    "Comparaison temporelle ciblée des soldes débiteurs entre copropriétaires",
)

db_cache_key = _get_db_cache_key(DB_PATH)
df = load_data(DB_PATH, db_cache_key)

if df.empty:
    st.warning("⚠️ Aucune donnée disponible pour l'analyse graphique.")
    st.stop()

date_min = df["date"].min()
date_max = df["date"].max()
derniere_date = df["date"].max()

# --- Barre de filtres principale ---
col_c1, col_c2 = st.columns([2, 1], gap="medium")

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
    date_range = st.date_input(
        "Période",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max,
        key="courbe_charge_dates",
    )

start_date, end_date = _normalize_date_range(date_range, date_min, date_max)

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
    fig.update_layout(xaxis_title="Date", yaxis_title="Débit (€)")
    fig = apply_plotly_theme(fig)
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
