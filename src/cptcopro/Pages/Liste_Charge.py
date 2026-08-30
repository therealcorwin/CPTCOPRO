"""Page unifiée de suivi des charges et débits des copropriétaires.

Cette page regroupe :
- La consultation tabulaire détaillée avec filtres multicritères rapides
- L'analyse graphique interactive de l'évolution temporelle des débits
- La synthèse statistique (KPIs, répartition par type de lot et Top débits)
"""

from __future__ import annotations

import io
import sqlite3
import datetime as dt
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import loguru

from cptcopro.utils.paths import get_db_path
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
    preparer_df_pour_graphe,
    is_privacy_enabled,
)
from cptcopro.utils.ui_components import render_header, apply_plotly_theme


DB_PATH = get_db_path()


def _get_db_cache_key(db_path: Path) -> int:
    try:
        return db_path.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=300, show_spinner=False)
def load_charges(db_path: Path, db_cache_key: int) -> pd.DataFrame:
    """Charger la vue `vw_charge_coproprietaires` depuis SQLite et normaliser la date."""
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


def _normalize_date_range(date_val, min_d, max_d) -> tuple[dt.date, dt.date]:
    """Extrait en toute sécurité start_date et end_date d'un st.date_input."""
    if isinstance(date_val, (tuple, list)):
        if len(date_val) >= 2:
            return date_val[0], date_val[1]
        elif len(date_val) == 1:
            return date_val[0], date_val[0]
        return min_d, max_d
    elif isinstance(date_val, dt.date):
        return date_val, date_val
    return min_d, max_d


# --- En-tête de la page ---
render_header(
    "💳 Suivi des Charges & Débits",
    "Consultation détaillée, filtres à facettes et analyse graphique de l'historique financier",
)

db_cache_key = _get_db_cache_key(DB_PATH)
df_all = load_charges(DB_PATH, db_cache_key)

if df_all.empty:
    st.warning("⚠️ Aucune donnée de charge trouvée dans la base de données.")
    st.stop()

date_min = df_all["date"].min()
date_max = df_all["date"].max()
all_types = ["Tous"] + sorted([t for t in df_all["type_apt"].dropna().unique() if t])

# ============================================================================
# FILTRES ERGONOMIQUES
# ============================================================================
with st.container():
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1, 1.2, 1.2], gap="medium")

    with col_f1:
        search_query = st.text_input(
            "🔍 Recherche rapide",
            placeholder="Nom ou code copropriétaire...",
            key="charges_search_input",
        ).strip()

    with col_f2:
        selected_type = st.selectbox(
            "Type de lot",
            options=all_types,
            index=0,
            key="charges_type_filter",
        )

    with col_f3:
        quick_focus = st.selectbox(
            "Filtre prédéfini",
            options=["Tous les copropriétaires", "Top 5 Débits récents", "Top 10 Débits récents", "Débits > 0 uniquement"],
            index=0,
            key="charges_quick_focus",
        )

    with col_f4:
        date_range = st.date_input(
            "Période d'analyse",
            value=(date_min, date_max),
            min_value=date_min,
            max_value=date_max,
            key="charges_date_range",
        )

start_date, end_date = _normalize_date_range(date_range, date_min, date_max)

# Application des filtres
filtered_df = df_all[
    (df_all["date"] >= start_date) & (df_all["date"] <= end_date)
].copy()

if search_query:
    filtered_df = filtered_df[
        filtered_df["proprietaire"].str.contains(search_query, case=False, na=False)
        | filtered_df["code"].str.contains(search_query, case=False, na=False)
    ]

if selected_type != "Tous":
    filtered_df = filtered_df[filtered_df["type_apt"] == selected_type]

if quick_focus == "Top 5 Débits récents":
    derniers = filtered_df[filtered_df["date"] == end_date]
    top_5_owners = derniers.nlargest(5, "debit")["proprietaire"].unique()
    filtered_df = filtered_df[filtered_df["proprietaire"].isin(top_5_owners)]
elif quick_focus == "Top 10 Débits récents":
    derniers = filtered_df[filtered_df["date"] == end_date]
    top_10_owners = derniers.nlargest(10, "debit")["proprietaire"].unique()
    filtered_df = filtered_df[filtered_df["proprietaire"].isin(top_10_owners)]
elif quick_focus == "Débits > 0 uniquement":
    filtered_df = filtered_df[filtered_df["debit"] > 0]

st.divider()

# ============================================================================
# SECTION KPI DYNAMIQUE
# ============================================================================
nb_lignes = len(filtered_df)
nb_copros = filtered_df["proprietaire"].nunique()
total_debit = float(filtered_df["debit"].sum())
total_credit = float(filtered_df["credit"].sum())
solde_net = total_debit - total_credit

kpi1, kpi2, kpi3, kpi4 = st.columns(4, gap="medium")

with kpi1:
    st.metric("Copropriétaires filtrés", f"{nb_copros} ({nb_lignes} relevés)")
with kpi2:
    st.metric("Total Débits", f"{total_debit:,.2f} €".replace(",", " "))
with kpi3:
    st.metric("Total Crédits", f"{total_credit:,.2f} €".replace(",", " "))
with kpi4:
    st.metric(
        "Solde Net Débiteur",
        f"{solde_net:,.2f} €".replace(",", " "),
        delta=f"{'+' if solde_net > 0 else ''}{solde_net:,.0f} €",
        delta_color="inverse" if solde_net > 0 else "normal",
    )

st.space("small")

# ============================================================================
# ONGLETS DE VISUALISATION
# ============================================================================
tab_table, tab_graph, tab_stats = st.tabs([
    "📋 Suivi Détaillé (Tableau)",
    "📈 Analyse Temporelle (Graphique)",
    "📊 Répartition & Top Débits",
])

# --- ONGLET 1: TABLEAU ---
with tab_table:
    if filtered_df.empty:
        st.info("Aucun enregistrement ne correspond aux critères sélectionnés.")
    else:
        df_sorted = filtered_df.sort_values(
            ["date", "proprietaire"], ascending=[False, True]
        ).copy()
        
        display_df = appliquer_confidentialite(df_sorted)

        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            column_config={
                "date": st.column_config.DateColumn("Date relevé", format="DD/MM/YYYY"),
                "proprietaire": st.column_config.TextColumn("Copropriétaire", width="medium"),
                "code": st.column_config.TextColumn("Code", width="small"),
                "num_apt": st.column_config.TextColumn("Lot / N°", width="small"),
                "type_apt": st.column_config.TextColumn("Type", width="small"),
                "debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €"),
                "credit": st.column_config.NumberColumn("Crédit (€)", format="%.2f €"),
            },
        )

        col_csv, _ = st.columns([1, 3])
        with col_csv:
            csv_buf = io.StringIO()
            display_df.to_csv(csv_buf, index=False, sep=";")
            st.download_button(
                "📥 Télécharger la sélection (CSV)",
                data=csv_buf.getvalue().encode("utf-8-sig"),
                file_name=f"charges_coproprietaires_{start_date}_{end_date}.csv",
                mime="text/csv",
                use_container_width=True,
            )

# --- ONGLET 2: GRAPHIQUE ---
with tab_graph:
    if filtered_df.empty:
        st.info("Aucune donnée à tracer pour les filtres sélectionnés.")
    else:
        graph_mode = st.radio(
            "Mode d'analyse temporelle :",
            options=[
                "🎯 Focus Top Débits (5/10)",
                "👥 Comparateur Sur-Mesure",
                "📊 Tendance Globale & Typologies",
                "🗺️ Matrice / Heatmap (Vue globale)",
            ],
            horizontal=True,
            key="charges_graph_mode",
        )

        # Moyenne globale par date en guise de benchmark
        avg_df = (
            df_all.groupby("date")["debit"]
            .mean()
            .reset_index()
            .rename(columns={"debit": "debit_moyen"})
        )
        avg_df = avg_df[(avg_df["date"] >= start_date) & (avg_df["date"] <= end_date)]

        if graph_mode == "🎯 Focus Top Débits (5/10)":
            col_f1, col_f2 = st.columns([2, 1], gap="medium")
            with col_f1:
                preset_focus = st.radio(
                    "Nombre de comptes à afficher :",
                    options=["Top 5", "Top 10", "Débits > 2000 €"],
                    horizontal=True,
                    key="graph_preset_focus",
                )
            with col_f2:
                show_avg_ref = st.checkbox(
                    "📐 Superposer la moyenne copropriété",
                    value=True,
                    key="graph_show_avg_ref",
                )

            derniere_date_sel = filtered_df["date"].max()
            derniers_soldes = filtered_df[filtered_df["date"] == derniere_date_sel]

            if preset_focus == "Top 5":
                focus_owners = derniers_soldes.nlargest(5, "debit")["proprietaire"].tolist()
            elif preset_focus == "Top 10":
                focus_owners = derniers_soldes.nlargest(10, "debit")["proprietaire"].tolist()
            else:
                focus_owners = derniers_soldes[derniers_soldes["debit"] > 2000]["proprietaire"].tolist()
                if not focus_owners:
                    focus_owners = derniers_soldes.nlargest(5, "debit")["proprietaire"].tolist()

            plot_df = filtered_df[filtered_df["proprietaire"].isin(focus_owners)]

            if plot_df.empty:
                st.info("Aucun compte ne correspond à ce critère.")
            else:
                prep_df = preparer_df_pour_graphe(plot_df, "proprietaire")
                fig = px.line(
                    prep_df,
                    x="date",
                    y="debit",
                    color="proprietaire",
                    title=f"Évolution des {len(focus_owners)} comptes les plus débiteurs (€)",
                    markers=True,
                )
                if show_avg_ref and not avg_df.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=avg_df["date"],
                            y=avg_df["debit_moyen"],
                            mode="lines",
                            name="Moyenne Copropriété",
                            line=dict(color="#F59E0B", dash="dash", width=2.5),
                        )
                    )
                fig.update_layout(xaxis_title="Date de relevé", yaxis_title="Débit (€)")
                fig = apply_plotly_theme(fig)
                st.plotly_chart(fig, width="stretch")

        elif graph_mode == "👥 Comparateur Sur-Mesure":
            col_c1, col_c2 = st.columns([2.5, 1], gap="medium")
            all_filtered_owners = sorted(filtered_df["proprietaire"].unique())
            latest_date_sel = filtered_df["date"].max()
            default_sel = (
                filtered_df[filtered_df["date"] == latest_date_sel]
                .nlargest(3, "debit")["proprietaire"]
                .tolist()
            )

            with col_c1:
                custom_selected_owners = st.multiselect(
                    "Sélectionnez les copropriétaires à comparer (1 à 8 comptes) :",
                    options=all_filtered_owners,
                    default=[o for o in default_sel if o in all_filtered_owners],
                    max_selections=8,
                    key="graph_custom_owners",
                )
            with col_c2:
                show_custom_avg = st.checkbox(
                    "📐 Superposer la moyenne copropriété",
                    value=True,
                    key="graph_show_custom_avg",
                )

            if not custom_selected_owners:
                st.info("Sélectionnez au moins un copropriétaire pour afficher les courbes.")
            else:
                custom_plot_df = filtered_df[filtered_df["proprietaire"].isin(custom_selected_owners)]
                prep_df = preparer_df_pour_graphe(custom_plot_df, "proprietaire")
                fig = px.line(
                    prep_df,
                    x="date",
                    y="debit",
                    color="proprietaire",
                    title=f"Comparatif ciblé ({len(custom_selected_owners)} compte(s) sélectionné(s))",
                    markers=True,
                )
                if show_custom_avg and not avg_df.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=avg_df["date"],
                            y=avg_df["debit_moyen"],
                            mode="lines",
                            name="Moyenne Copropriété",
                            line=dict(color="#F59E0B", dash="dash", width=2.5),
                        )
                    )
                fig.update_layout(xaxis_title="Date de relevé", yaxis_title="Débit (€)")
                fig = apply_plotly_theme(fig)
                st.plotly_chart(fig, width="stretch")

        elif graph_mode == "📊 Tendance Globale & Typologies":
            macro_type = st.radio(
                "Type de vue macroscopique :",
                options=["Masse totale des débits (Cumul)", "Débit moyen par typologie (T2, T3, T4, T5)"],
                horizontal=True,
                key="graph_macro_type",
            )

            if macro_type == "Masse totale des débits (Cumul)":
                agg_df = filtered_df.groupby("date")["debit"].sum().reset_index()
                fig = px.area(
                    agg_df,
                    x="date",
                    y="debit",
                    title="Évolution de la masse globale des débits (€)",
                    markers=True,
                )
                fig.update_traces(line_color="#0284C7", fillcolor="rgba(2, 132, 199, 0.25)")
                fig.update_layout(xaxis_title="Date de relevé", yaxis_title="Débit total (€)")
                fig = apply_plotly_theme(fig)
                st.plotly_chart(fig, width="stretch")
            else:
                type_agg = (
                    filtered_df.groupby(["date", "type_apt"])["debit"]
                    .mean()
                    .reset_index()
                )
                fig = px.line(
                    type_agg,
                    x="date",
                    y="debit",
                    color="type_apt",
                    title="Débit moyen par typologie de logement (€)",
                    markers=True,
                )
                fig.update_layout(xaxis_title="Date de relevé", yaxis_title="Débit moyen (€)")
                fig = apply_plotly_theme(fig)
                st.plotly_chart(fig, width="stretch")

        else:  # Mode 4 : Matrice / Heatmap
            st.markdown("#### Matrice thermique temporelle des débits")
            st.caption(
                "Chaque ligne représente un copropriétaire (triés par débit actuel décroissant) et chaque colonne une date. Les teintes chaudes indiquent un débit élevé."
            )

            pivot_df = filtered_df.pivot_table(
                index="proprietaire", columns="date", values="debit", aggfunc="sum"
            ).fillna(0)

            if pivot_df.empty:
                st.info("Données insuffisantes pour générer la matrice.")
            else:
                last_col = pivot_df.columns[-1]
                pivot_df = pivot_df.sort_values(by=last_col, ascending=True)

                dates_str = [
                    d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)
                    for d in pivot_df.columns
                ]
                owners_display = (
                    ["●●●●●●" if is_privacy_enabled() else name for name in pivot_df.index]
                    if is_privacy_enabled()
                    else list(pivot_df.index)
                )

                fig_heat = go.Figure(
                    data=go.Heatmap(
                        z=pivot_df.values,
                        x=dates_str,
                        y=owners_display,
                        colorscale="Blues",
                        colorbar=dict(title="Débit (€)"),
                        hovertemplate="Copropriétaire: %{y}<br>Date: %{x}<br>Débit: %{z:,.2f} €<extra></extra>",
                    )
                )
                fig_heat.update_layout(
                    xaxis_title="Date de relevé",
                    yaxis=dict(showticklabels=len(pivot_df) <= 25),
                    height=max(450, len(pivot_df) * 15),
                )
                fig_heat = apply_plotly_theme(fig_heat)
                st.plotly_chart(fig_heat, width="stretch")

# --- ONGLET 3: STATS & RÉPARTITION ---
with tab_stats:
    if filtered_df.empty:
        st.info("Aucune donnée disponible.")
    else:
        col_s1, col_s2 = st.columns(2, gap="large")

        with col_s1:
            st.markdown("#### Répartition des débits par type de lot")
            repartition_type = (
                filtered_df.groupby("type_apt")
                .agg(
                    TotalDebit=("debit", "sum"),
                    MoyenneDebit=("debit", "mean"),
                    NbReleves=("debit", "count"),
                )
                .reset_index()
            )
            if not repartition_type.empty:
                fig_pie = px.pie(
                    repartition_type,
                    values="TotalDebit",
                    names="type_apt",
                    color_discrete_sequence=px.colors.qualitative.Safe,
                )
                fig_pie = apply_plotly_theme(fig_pie)
                st.plotly_chart(fig_pie, width="stretch")

        with col_s2:
            st.markdown("#### Top 10 des débits au relevé le plus récent")
            latest_date = filtered_df["date"].max()
            top_10 = (
                filtered_df[filtered_df["date"] == latest_date]
                .nlargest(10, "debit")
                .sort_values("debit", ascending=True)
            )
            top_10_prep = preparer_df_pour_graphe(top_10, "proprietaire")
            
            fig_bar = px.bar(
                top_10_prep,
                x="debit",
                y="proprietaire",
                orientation="h",
                title=f"Top 10 au {latest_date.strftime('%d/%m/%Y')}",
                labels={"debit": "Débit (€)", "proprietaire": "Copropriétaire"},
                color="debit",
                color_continuous_scale="Blues",
            )
            fig_bar.update_layout(coloraxis_showscale=False)
            fig_bar = apply_plotly_theme(fig_bar)
            st.plotly_chart(fig_bar, width="stretch")
