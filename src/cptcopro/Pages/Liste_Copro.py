"""Page Annuaire de tous les copropriétaires."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from cptcopro.utils.paths import get_db_path
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
)
from cptcopro.utils.ui_components import render_header

DB_PATH = get_db_path()


def _get_db_cache_key(db_path: Path) -> int:
    try:
        return db_path.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=300, show_spinner=False)
def load_coproprietaires(db_path: Path, db_cache_key: int) -> pd.DataFrame:
    """Charge la liste complète des copropriétaires depuis SQLite."""
    del db_cache_key
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, "
            "type_apt AS Type, num_apt AS Numero, last_check AS Date FROM coproprietaires "
            "ORDER BY nom_proprietaire ASC",
            conn,
        )
    return df


render_header(
    "👥 Annuaire des Copropriétaires",
    "Répertoire complet des copropriétaires, lots rattachés et typologies d'appartements",
)

db_cache_key = _get_db_cache_key(DB_PATH)
df_copros = load_coproprietaires(DB_PATH, db_cache_key)

if df_copros.empty:
    st.warning("⚠️ Aucun copropriétaire trouvé dans la base de données.")
    st.stop()

# ============================================================================
# KPIS GLOBAUX
# ============================================================================
total_copros = len(df_copros)
repartition_types = df_copros["Type"].value_counts().to_dict()
derniere_maj = df_copros["Date"].max() if "Date" in df_copros.columns else "N/A"

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5, gap="small")
with kpi1:
    st.metric("Total Copropriétaires", total_copros)
with kpi2:
    st.metric("2 pièces (T2)", repartition_types.get("2p", 0))
with kpi3:
    st.metric("3 pièces (T3)", repartition_types.get("3p", 0))
with kpi4:
    st.metric("4 pièces (T4)", repartition_types.get("4p", 0))
with kpi5:
    st.metric("5 pièces (T5+)", repartition_types.get("5p", 0))

st.divider()

# ============================================================================
# FILTRES ERGONOMIQUES
# ============================================================================
col_f1, col_f2, col_f3 = st.columns([2, 1, 1], gap="medium")

with col_f1:
    search_text = st.text_input(
        "🔍 Recherche rapide",
        placeholder="Rechercher par nom, code ou numéro de lot...",
        key="annuaire_search_text",
    ).strip()

with col_f2:
    types_disponibles = ["Tous", *sorted(t for t in df_copros["Type"].dropna().unique() if t)]
    filtre_type = st.selectbox(
        "Type d'appartement",
        options=types_disponibles,
        index=0,
        key="annuaire_type_filter",
    )

with col_f3:
    st.caption(
        "💡 Astuce : Rendez-vous sur la page **Recherche & Fiche copropriétaire** pour une analyse 360° individuelle."
    )

# Filtrage du DataFrame
df_filtre = df_copros.copy()

if search_text:
    df_filtre = df_filtre[
        df_filtre["Proprietaire"].str.contains(search_text, case=False, na=False)
        | df_filtre["Code"].str.contains(search_text, case=False, na=False)
        | df_filtre["Numero"].astype(str).str.contains(search_text, case=False, na=False)
    ]

if filtre_type != "Tous":
    df_filtre = df_filtre[df_filtre["Type"] == filtre_type]

# ============================================================================
# TABLEAU PRINCIPAL
# ============================================================================
st.markdown(f"**{len(df_filtre)} copropriétaire(s) affiché(s)**")

display_df = appliquer_confidentialite(df_filtre)

st.dataframe(
    display_df,
    width="stretch",
    hide_index=True,
    column_config={
        "Proprietaire": st.column_config.TextColumn("Nom du copropriétaire", width="large"),
        "Code": st.column_config.TextColumn("Code", width="small"),
        "Type": st.column_config.TextColumn("Type Lot", width="small"),
        "Numero": st.column_config.TextColumn("Numéro Lot / Apt", width="small"),
        "Date": st.column_config.DateColumn(
            "Dernière vérification", format="DD/MM/YYYY", width="medium"
        ),
    },
)

# Export CSV
col_dl, _ = st.columns([1, 3])
with col_dl:
    csv_buffer = io.StringIO()
    display_df.to_csv(csv_buffer, index=False, sep=";")
    st.download_button(
        "📥 Exporter l'annuaire (CSV)",
        data=csv_buffer.getvalue().encode("utf-8-sig"),
        file_name="annuaire_coproprietaires.csv",
        mime="text/csv",
        use_container_width=True,
    )
