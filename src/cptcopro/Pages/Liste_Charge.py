"""Page unifiée de suivi des charges et débits des copropriétaires.

Cette page regroupe :
- La consultation tabulaire détaillée avec filtres multicritères rapides
- L'analyse graphique interactive de l'évolution temporelle des débits
- La synthèse statistique (KPIs, répartition par type de lot et Top débits)
"""

from __future__ import annotations

import io

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import (
    fetch_dataframe,
    normalize_date_columns,
    normalize_numeric_columns,
)
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
    is_privacy_enabled,
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
def load_alertes_codes() -> set[str]:
    """Charger la liste des codes copropriétaires ayant une alerte de débit actif."""
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT code_proprietaire FROM alertes_debit_eleve")
            rows = cur.fetchall()
        return {str(r["code_proprietaire"]) for r in rows if r and "code_proprietaire" in r}
    except Exception:
        return set()


@st.cache_data(ttl=120, show_spinner=False)
def load_statut_relance_par_copro() -> dict[str, str]:
    """Retourne dict {code: statut_relance} pour enrichissement du tableau."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT
                    code_proprietaire,
                    MAX(created_at) AS derniere_relance,
                    COUNT(*) AS nb_relances,
                    MAX(status) AS dernier_statut
                FROM relance_draft
                WHERE status NOT IN ('deleted')
                GROUP BY code_proprietaire
                """
            )
            rows = cur.fetchall()
        result = {}
        for r in rows:
            if not r or not r.get("code_proprietaire"):
                continue
            code = str(r["code_proprietaire"])
            nb = int(r.get("nb_relances") or 0)
            date_raw = r.get("derniere_relance")
            date_str = str(date_raw)[:10] if date_raw else None
            statut = str(r.get("dernier_statut") or "").lower()
            if statut == "sent":
                label = f"✅ Envoyé {date_str or ''}"
            elif statut in ("draft_imap", "draft_local"):
                label = f"📝 Brouillon ({date_str or '—'})"
            elif statut == "error":
                label = f"❌ Erreur relance"
            else:
                label = f"📬 {nb} relance(s)"
            result[code] = label
        return result
    except Exception:
        return {}


def _determiner_statut(row: pd.Series, alert_codes: set[str]) -> str:
    """Détermine le statut synthétique d'un copropriétaire pour la balance de gestion."""
    code = str(row.get("code", ""))
    debit = float(row.get("debit", 0.0))
    credit = float(row.get("credit", 0.0))
    delta = float(row.get("delta_debit", 0.0))

    if code in alert_codes:
        return "🚨 Alerte seuil"
    if debit > 0:
        if delta > 0:
            return "🔴 Débiteur (+)"
        elif delta < 0:
            return "🟡 Débiteur (-)"
        return "🟠 Débiteur"
    if credit > 0:
        return "🔵 Créditeur"
    return "🟢 À jour"


@st.cache_data(ttl=300, show_spinner=False)
def load_charges() -> pd.DataFrame:
    """Charger la vue `vw_charge_coproprietaires` depuis MariaDB et normaliser la date."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, "
            "num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires"
        )
        df = fetch_dataframe(cur)
    df = normalize_date_columns(df, ["date"])
    df = normalize_numeric_columns(df, ["debit", "credit"])
    if "date" in df.columns:
        df = df.dropna(subset=["date"]).sort_values("date")
    return df


# --- En-tête de la page ---
render_header(
    "💳 Suivi des Charges & Débits",
    "Consultation détaillée, filtres à facettes et analyse graphique de l'historique financier",
)

df_all = load_charges()


if df_all.empty:
    st.warning("⚠️ Aucune donnée de charge trouvée dans la base de données.")
    st.stop()

available_dates = sorted(df_all["date"].dropna().unique())
date_labels = [
    d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)
    for d in available_dates
]
all_types = ["Tous", *sorted(t for t in df_all["type_apt"].dropna().unique() if t)]

# ============================================================================
# FILTRES ERGONOMIQUES
# ============================================================================
with st.container():
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.4, 0.9, 1.1, 1.1], gap="medium")

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
            options=[
                "Tous les copropriétaires",
                "Débits > 0 uniquement",
                "Top 5 Débits",
                "Top 10 Débits",
            ],
            index=0,
            key="charges_quick_focus",
        )

    with col_f4:
        selected_date_label = st.selectbox(
            "📅 Relevé de référence",
            options=date_labels,
            index=len(date_labels) - 1,
            help="Sélectionnez la date du relevé pour la situation instantanée et les indicateurs.",
            key="charges_date_ref",
        )

# Toggle débiteurs
col_tog, _ = st.columns([1.5, 5])
with col_tog:
    only_debiteurs = st.checkbox(
        "🔴 Débiteurs seulement",
        value=False,
        key="charges_only_debiteurs",
        help="N'afficher que les copropriétaires dont le débit est positif au relevé de référence.",
    )

# Application du périmètre de recherche et typologie
df_scope = df_all.copy()
if search_query:
    df_scope = df_scope[
        df_scope["proprietaire"].str.contains(search_query, case=False, na=False)
        | df_scope["code"].str.contains(search_query, case=False, na=False)
    ]

if selected_type != "Tous":
    df_scope = df_scope[df_scope["type_apt"] == selected_type]

# Identification du relevé actif et du relevé antérieur (N-1)
date_ref_idx = date_labels.index(selected_date_label)
date_ref = available_dates[date_ref_idx]
date_prev = available_dates[date_ref_idx - 1] if date_ref_idx > 0 else None

df_ref = df_scope[df_scope["date"] == date_ref].copy()
df_prev = (
    df_scope[df_scope["date"] == date_prev].copy()
    if date_prev is not None
    else pd.DataFrame()
)

# Application du filtre prédéfini sur le relevé actif
if quick_focus == "Top 5 Débits":
    top_5_owners = df_ref.nlargest(5, "debit")["proprietaire"].unique()
    df_ref = df_ref[df_ref["proprietaire"].isin(top_5_owners)]
elif quick_focus == "Top 10 Débits":
    top_10_owners = df_ref.nlargest(10, "debit")["proprietaire"].unique()
    df_ref = df_ref[df_ref["proprietaire"].isin(top_10_owners)]
elif quick_focus == "Débits > 0 uniquement":
    df_ref = df_ref[df_ref["debit"] > 0]

# Application du toggle débiteurs seulement
if only_debiteurs:
    df_ref = df_ref[df_ref["debit"] > 0]

# Périmètre historique correspondant pour les graphiques (jusqu'au relevé de référence)
active_owners = (
    df_ref["proprietaire"].unique()
    if not df_ref.empty
    else df_scope["proprietaire"].unique()
)
filtered_df = df_scope[
    df_scope["proprietaire"].isin(active_owners) & (df_scope["date"] <= date_ref)
].copy()

# Calcul des variations individuelles et du statut
if not df_prev.empty:
    prev_map_debit = df_prev.set_index("code")["debit"].to_dict()
    prev_map_credit = df_prev.set_index("code")["credit"].to_dict()
else:
    prev_map_debit = {}
    prev_map_credit = {}

df_ref["debit_prev"] = df_ref["code"].map(prev_map_debit).fillna(0.0)
df_ref["credit_prev"] = df_ref["code"].map(prev_map_credit).fillna(0.0)
df_ref["delta_debit"] = df_ref["debit"] - df_ref["debit_prev"]
df_ref["solde_net"] = df_ref["debit"] - df_ref["credit"]

alert_codes = load_alertes_codes()
df_ref["statut"] = df_ref.apply(lambda r: _determiner_statut(r, alert_codes), axis=1)
relance_statuts = load_statut_relance_par_copro()
df_ref["statut_relance"] = df_ref["code"].map(
    lambda c: relance_statuts.get(str(c), "—")
)

st.divider()

# ============================================================================
# SECTION KPI DYNAMIQUE (Situation au relevé de référence)
# ============================================================================
if df_ref.empty:
    st.info("ℹ️ Aucun enregistrement ne correspond aux filtres pour ce relevé.")
elif df_ref["proprietaire"].nunique() == 1:
    # --- Vue Individuelle Contextuelle (Fiche Copropriétaire) ---
    copro_row = df_ref.iloc[0]
    copro_debit = float(copro_row["debit"])
    copro_credit = float(copro_row["credit"])
    copro_delta = float(copro_row["delta_debit"])
    copro_solde_net = copro_debit - copro_credit
    copro_statut = copro_row["statut"]

    copro_history = df_scope[df_scope["code"] == copro_row["code"]].sort_values("date")
    max_debit = (
        float(copro_history["debit"].max()) if not copro_history.empty else copro_debit
    )
    nb_deb = int((copro_history["debit"] > 0).sum())
    total_releves = len(copro_history)
    pct_deb = (nb_deb / total_releves * 100) if total_releves > 0 else 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4, gap="medium")

    with kpi1:
        label_solde = (
            "Solde Débiteur Actuel"
            if copro_solde_net > 0
            else ("Solde Créditeur Actuel" if copro_solde_net < 0 else "Solde Actuel (À jour)")
        )
        delta_str = (
            f"{'+' if copro_delta > 0 else ''}{copro_delta:,.2f} € vs N-1"
            if date_prev is not None
            else None
        )
        st.metric(
            label_solde,
            f"{abs(copro_solde_net):,.2f} €".replace(",", " "),
            delta=delta_str,
            delta_color="inverse" if copro_delta > 0 else "normal",
            help="Solde net (Débit - Crédit) au relevé de référence.",
        )

    with kpi2:
        st.metric(
            "Statut du compte",
            copro_statut,
            delta=f"Relevé du {selected_date_label}",
            delta_color="off",
            help="Statut calculé à la date du relevé de référence.",
        )

    with kpi3:
        st.metric(
            "Pic Débiteur Historique",
            f"{max_debit:,.2f} €".replace(",", " "),
            delta=f"Sur {total_releves} relevé(s)",
            delta_color="off",
            help="Plus haut solde débiteur atteint dans l'historique disponible.",
        )

    with kpi4:
        st.metric(
            "Fréquence en Débit",
            f"{nb_deb} / {total_releves} relevés",
            delta=f"{pct_deb:.0f} % du temps",
            delta_color="inverse" if pct_deb > 50 else "off",
            help="Proportion de relevés dans lesquels le compte a présenté un solde débiteur.",
        )
else:
    # --- Vue Globale Copropriété ---
    nb_copros = len(df_ref)
    total_debit = float(df_ref["debit"].sum())
    prev_debit = float(df_prev["debit"].sum()) if not df_prev.empty else total_debit
    delta_total_debit = total_debit - prev_debit if not df_prev.empty else None

    nb_debiteurs = int((df_ref["debit"] > 0).sum())
    nb_debiteurs_prev = (
        int((df_prev["debit"] > 0).sum()) if not df_prev.empty else nb_debiteurs
    )
    delta_nb_debiteurs = (
        nb_debiteurs - nb_debiteurs_prev if not df_prev.empty else None
    )
    taux_debiteurs = (nb_debiteurs / nb_copros * 100) if nb_copros > 0 else 0.0

    debit_moyen = (total_debit / nb_debiteurs) if nb_debiteurs > 0 else 0.0
    debit_moyen_prev = (
        (prev_debit / nb_debiteurs_prev) if nb_debiteurs_prev > 0 else debit_moyen
    )
    delta_debit_moyen = (
        debit_moyen - debit_moyen_prev if not df_prev.empty else None
    )

    total_credit = float(df_ref["credit"].sum())
    prev_credit = float(df_prev["credit"].sum()) if not df_prev.empty else total_credit
    delta_total_credit = (
        total_credit - prev_credit if not df_prev.empty else None
    )

    solde_net_global = total_debit - total_credit

    kpi1, kpi2, kpi3, kpi4 = st.columns(4, gap="medium")

    with kpi1:
        delta_debit_str = (
            f"{'+' if delta_total_debit > 0 else ''}{delta_total_debit:,.2f} € vs N-1"
            if delta_total_debit is not None
            else None
        )
        st.metric(
            "Encours Débiteur Réel",
            f"{total_debit:,.2f} €".replace(",", " "),
            delta=delta_debit_str,
            delta_color="inverse",
            help="Total réel des impayés au relevé sélectionné (hors cumul artificiel des années passées).",
        )

    with kpi2:
        delta_nb_str = (
            f"{'+' if delta_nb_debiteurs > 0 else ''}{delta_nb_debiteurs} compte(s) vs N-1"
            if delta_nb_debiteurs is not None
            else None
        )
        st.metric(
            "Copropriétaires Débiteurs",
            f"{nb_debiteurs} / {nb_copros} ({taux_debiteurs:.1f} %)",
            delta=delta_nb_str,
            delta_color="inverse",
            help="Nombre et pourcentage de copropriétaires ayant un solde débiteur strict (> 0 €).",
        )

    with kpi3:
        delta_moy_str = (
            f"{'+' if delta_debit_moyen > 0 else ''}{delta_debit_moyen:,.2f} € vs N-1"
            if delta_debit_moyen is not None
            else None
        )
        st.metric(
            "Débit Moyen par Débiteur",
            f"{debit_moyen:,.2f} €".replace(",", " "),
            delta=delta_moy_str,
            delta_color="inverse",
            help="Montant moyen de découvert parmi les seuls copropriétaires débiteurs.",
        )

    with kpi4:
        delta_cred_str = (
            f"{'+' if delta_total_credit > 0 else ''}{delta_total_credit:,.2f} € vs N-1"
            if delta_total_credit is not None
            else None
        )
        st.metric(
            "Avances & Trop-Perçus",
            f"{total_credit:,.2f} €".replace(",", " "),
            delta=delta_cred_str,
            delta_color="normal",
            help="Total des soldes créditeurs (avances de charges) versés par les copropriétaires.",
        )

    date_prev_str = date_prev.strftime("%d/%m/%Y") if date_prev else "N/A"
    col_sub1, col_sub2 = st.columns([2, 1])
    with col_sub1:
        st.caption(
            f"📅 Situation arrêtée au **{selected_date_label}** (comparée au relevé antérieur du {date_prev_str})."
        )
    with col_sub2:
        statut_solde = "débiteur" if solde_net_global > 0 else "excédentaire"
        st.caption(
            f"⚖️ Solde net global de la copropriété : **{solde_net_global:,.2f} €** ({statut_solde})"
        )

st.space("small")

# ============================================================================
# ONGLETS DE VISUALISATION
# ============================================================================
tab_table, tab_graph, tab_stats = st.tabs(
    [
        "📋 Suivi Détaillé (Tableau)",
        "📈 Analyse Temporelle (Graphique)",
        "📊 Répartition & Top Débits",
    ]
)

# --- ONGLET 1: TABLEAU ---
with tab_table:
    col_t1, col_t2 = st.columns([2, 1])
    with col_t1:
        vue_historique = st.checkbox(
            "📜 Déplier tout l'historique chronologique de la sélection",
            value=False,
            key="charges_show_history",
            help="Cochez pour afficher l'ensemble des relevés passés au lieu de la balance au relevé de référence.",
        )

    if vue_historique:
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
                    "📥 Télécharger l'historique complet (CSV)",
                    data=csv_buf.getvalue().encode("utf-8-sig"),
                    file_name=f"charges_historique_{date_labels[0]}_{selected_date_label}.csv".replace(
                        "/", "-"
                    ),
                    mime="text/csv",
                    width="stretch",
                )
    else:
        if df_ref.empty:
            st.info("Aucun enregistrement ne correspond aux critères pour ce relevé.")
        else:
            df_ref_sorted = df_ref.sort_values(
                ["debit", "proprietaire"], ascending=[False, True]
            ).copy()
            display_ref = appliquer_confidentialite(df_ref_sorted)

            st.dataframe(
                display_ref,
                width="stretch",
                hide_index=True,
                column_order=[
                    "proprietaire",
                    "code",
                    "num_apt",
                    "type_apt",
                    "debit",
                    "credit",
                    "delta_debit",
                    "statut",
                    "statut_relance",
                ],
                column_config={
                    "proprietaire": st.column_config.TextColumn("Copropriétaire", width="medium"),
                    "code": st.column_config.TextColumn("Code", width="small"),
                    "num_apt": st.column_config.TextColumn("Lot / N°", width="small"),
                    "type_apt": st.column_config.TextColumn("Type", width="small"),
                    "debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €"),
                    "credit": st.column_config.NumberColumn("Crédit (€)", format="%.2f €"),
                    "delta_debit": st.column_config.NumberColumn(
                        "Variation vs N-1 (€)",
                        format="%.2f €",
                        help="Évolution de la dette par rapport au relevé précédent (positif = dette en hausse).",
                    ),
                    "statut": st.column_config.TextColumn("Statut", width="medium"),
                    "statut_relance": st.column_config.TextColumn(
                        "✉️ Relance",
                        help="Statut de la dernière relance générée pour ce copropriétaire."
                    ),
                },
            )

            col_csv, _ = st.columns([1, 3])
            with col_csv:
                csv_buf = io.StringIO()
                export_cols = [
                    "proprietaire",
                    "code",
                    "num_apt",
                    "type_apt",
                    "debit",
                    "credit",
                    "delta_debit",
                    "statut",
                    "statut_relance",
                ]
                display_ref[export_cols].to_csv(csv_buf, index=False, sep=";")
                st.download_button(
                    f"📥 Télécharger la balance du {selected_date_label} (CSV)",
                    data=csv_buf.getvalue().encode("utf-8-sig"),
                    file_name=f"balance_coproprietaires_{selected_date_label.replace('/', '-')}.csv",
                    mime="text/csv",
                    width="stretch",
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
        avg_df = avg_df[avg_df["date"] <= date_ref]

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
                focus_owners = derniers_soldes[derniers_soldes["debit"] > 2000][
                    "proprietaire"
                ].tolist()
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
                fig = apply_plotly_theme(fig)
                fig.update_layout(
                    height=500,
                    xaxis_title="Date de relevé",
                    yaxis_title="Débit (€)",
                    margin=dict(l=20, r=20, t=50, b=90),
                    title=dict(x=0.01, xanchor="left", y=0.98, yanchor="top"),
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
                custom_plot_df = filtered_df[
                    filtered_df["proprietaire"].isin(custom_selected_owners)
                ]
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
                fig = apply_plotly_theme(fig)
                fig.update_layout(
                    height=500,
                    xaxis_title="Date de relevé",
                    yaxis_title="Débit (€)",
                    margin=dict(l=20, r=20, t=50, b=90),
                    title=dict(x=0.01, xanchor="left", y=0.98, yanchor="top"),
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

        elif graph_mode == "📊 Tendance Globale & Typologies":
            macro_type = st.radio(
                "Type de vue macroscopique :",
                options=[
                    "Masse totale des débits (Cumul)",
                    "Débit moyen par typologie (T2, T3, T4, T5)",
                ],
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
                type_agg = filtered_df.groupby(["date", "type_apt"])["debit"].mean().reset_index()
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
    if df_ref.empty:
        st.info("Aucune donnée disponible pour le relevé sélectionné.")
    else:
        col_s1, col_s2 = st.columns(2, gap="large")

        with col_s1:
            st.markdown(f"#### Répartition des débits par type de lot ({selected_date_label})")
            repartition_type = (
                df_ref.groupby("type_apt")
                .agg(
                    TotalDebit=("debit", "sum"),
                    MoyenneDebit=("debit", "mean"),
                    NbLots=("debit", "count"),
                )
                .reset_index()
            )
            pie_data = repartition_type[repartition_type["TotalDebit"] > 0]
            if not pie_data.empty:
                fig_pie = px.pie(
                    pie_data,
                    values="TotalDebit",
                    names="type_apt",
                    color_discrete_sequence=px.colors.qualitative.Safe,
                )
                fig_pie = apply_plotly_theme(fig_pie)
                st.plotly_chart(fig_pie, width="stretch")
            else:
                st.info("Aucun débit supérieur à 0 € à répartir pour ce relevé.")

        with col_s2:
            st.markdown(f"#### Top 10 des débits au {selected_date_label}")
            top_10 = (
                df_ref[df_ref["debit"] > 0]
                .nlargest(10, "debit")
                .sort_values("debit", ascending=True)
            )
            if not top_10.empty:
                top_10_prep = preparer_df_pour_graphe(top_10, "proprietaire")

                fig_bar = px.bar(
                    top_10_prep,
                    x="debit",
                    y="proprietaire",
                    orientation="h",
                    title=f"Top 10 au {selected_date_label}",
                    labels={"debit": "Débit (€)", "proprietaire": "Copropriétaire"},
                    color="debit",
                    color_continuous_scale="Blues",
                )
                fig_bar.update_layout(coloraxis_showscale=False)
                fig_bar = apply_plotly_theme(fig_bar)
                st.plotly_chart(fig_bar, width="stretch")
            else:
                st.info("Aucun compte débiteur (> 0 €) sur ce relevé.")
