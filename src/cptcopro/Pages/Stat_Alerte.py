"""Page d'historique et de répartition des alertes par typologie d'appartement."""

from __future__ import annotations

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
def recup_alertes(db_path: Path, db_cache_key: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    del db_cache_key
    query = (
        "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, "
        "debit AS Debit, type_alerte AS TypeApt, first_detection AS FirstDetection, "
        "last_detection AS LastDetection, occurence AS Occurence "
        "FROM alertes_debit_eleve"
    )
    query2 = "SELECT SUM(debit) AS TotalDebit FROM alertes_debit_eleve"
    try:
        with sqlite3.connect(str(db_path)) as conn:
            recup_alerte = pd.read_sql_query(query, conn)
            recup_total_debit = pd.read_sql_query(query2, conn)
        return recup_alerte, recup_total_debit
    except Exception as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def recup_suivi_alertes(db_path: Path, db_cache_key: int) -> pd.DataFrame:
    del db_cache_key
    query = """
        SELECT date_releve, nombre_alertes, total_debit,
               nb_2p, nb_3p, nb_4p, nb_5p, nb_na,
               debit_2p, debit_3p, debit_4p, debit_5p, debit_na
        FROM suivi_alertes
        ORDER BY date_releve DESC
    """
    try:
        with sqlite3.connect(str(db_path)) as conn:
            suivi_df = pd.read_sql_query(query, conn)
        return suivi_df
    except Exception as e:
        st.error(f"Erreur lors de la récupération du suivi : {e}")
        return pd.DataFrame()


def get_val(df: pd.DataFrame, col: str, default: int = 0) -> int:
    if col in df.columns and not df.empty:
        val = df[col].iat[0]
        return int(val) if pd.notna(val) else default
    return default


def get_delta(df: pd.DataFrame, col: str) -> int:
    if col in df.columns and len(df) >= 2:
        curr = df[col].iat[0] or 0
        prev = df[col].iat[1] or 0
        return int(curr - prev)
    return 0


render_header(
    "📈 Historique & Répartition des Alertes",
    "Ventilation des anomalies d'impayés par typologie de logement et récurrence",
)

db_cache_key = _get_db_cache_key(DB_PATH)
suivi_alerte = recup_suivi_alertes(DB_PATH, db_cache_key)
alertes_df, total_debit_df = recup_alertes(DB_PATH, db_cache_key)

if not suivi_alerte.empty:
    st.subheader("Répartition des alertes actives par type de lot")
    col1, col2, col3, col4, col5 = st.columns(5, gap="small")

    with col1:
        d2 = get_delta(suivi_alerte, "nb_2p")
        st.metric(
            "2 pièces (T2)",
            value=get_val(suivi_alerte, "nb_2p"),
            delta=f"{'+' if d2 > 0 else ''}{d2}" if d2 != 0 else None,
            delta_color="inverse",
        )
    with col2:
        d3 = get_delta(suivi_alerte, "nb_3p")
        st.metric(
            "3 pièces (T3)",
            value=get_val(suivi_alerte, "nb_3p"),
            delta=f"{'+' if d3 > 0 else ''}{d3}" if d3 != 0 else None,
            delta_color="inverse",
        )
    with col3:
        d4 = get_delta(suivi_alerte, "nb_4p")
        st.metric(
            "4 pièces (T4)",
            value=get_val(suivi_alerte, "nb_4p"),
            delta=f"{'+' if d4 > 0 else ''}{d4}" if d4 != 0 else None,
            delta_color="inverse",
        )
    with col4:
        d5 = get_delta(suivi_alerte, "nb_5p")
        st.metric(
            "5 pièces (T5+)",
            value=get_val(suivi_alerte, "nb_5p"),
            delta=f"{'+' if d5 > 0 else ''}{d5}" if d5 != 0 else None,
            delta_color="inverse",
        )
    with col5:
        dna = get_delta(suivi_alerte, "nb_na")
        st.metric(
            "Non classé",
            value=get_val(suivi_alerte, "nb_na"),
            delta=f"{'+' if dna > 0 else ''}{dna}" if dna != 0 else None,
            delta_color="inverse",
        )

st.divider()

if not alertes_df.empty:
    col_sel, _ = st.columns([1.5, 2])
    with col_sel:
        types_disponibles = ["Tous", *sorted(alertes_df["TypeApt"].dropna().unique().tolist())]
        type_selectionne = st.selectbox(
            "Filtrer par type de lot :",
            options=types_disponibles,
            index=0,
            key="stat_alerte_filtre_type",
        )

    if type_selectionne != "Tous":
        alertes_filtrees = alertes_df[alertes_df["TypeApt"] == type_selectionne]
    else:
        alertes_filtrees = alertes_df

    st.subheader("Détail des occurrences par copropriétaire")
    alertes_affiche = appliquer_confidentialite(
        alertes_filtrees[
            [
                "Proprietaire",
                "Code",
                "Debit",
                "TypeApt",
                "Occurence",
                "FirstDetection",
                "LastDetection",
            ]
        ].sort_values(by="Debit", ascending=False)
    )

    st.dataframe(
        alertes_affiche,
        width="stretch",
        hide_index=True,
        column_config={
            "Proprietaire": st.column_config.TextColumn("Copropriétaire"),
            "Code": st.column_config.TextColumn("Code", width="small"),
            "Debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €"),
            "TypeApt": st.column_config.TextColumn("Type", width="small"),
            "Occurence": st.column_config.NumberColumn("Occurrences", width="small"),
            "FirstDetection": st.column_config.TextColumn("1ère détection"),
            "LastDetection": st.column_config.TextColumn("Dernière détection"),
        },
    )

    st.divider()

    col_g1, col_g2 = st.columns(2, gap="large")

    with col_g1:
        fig_bar = px.bar(
            preparer_df_pour_graphe(alertes_filtrees, "Proprietaire"),
            x="Proprietaire",
            y="Occurence",
            color="TypeApt",
            title="Nombre de relevés en situation d'alerte",
        )
        fig_bar = apply_plotly_theme(fig_bar)
        st.plotly_chart(fig_bar, width="stretch")

    with col_g2:
        if len(alertes_df["TypeApt"].unique()) > 1:
            st.markdown("#### Part des alertes par typologie de lot")
            repartition = (
                alertes_df.groupby("TypeApt")
                .agg(NbAlertes=("TypeApt", "count"), TotalDebit=("Debit", "sum"))
                .reset_index()
            )
            fig_pie = px.pie(
                repartition,
                values="NbAlertes",
                names="TypeApt",
                color_discrete_sequence=px.colors.qualitative.Safe,
            )
            fig_pie = apply_plotly_theme(fig_pie)
            st.plotly_chart(fig_pie, width="stretch")
else:
    st.info("Aucune alerte active à afficher.")
