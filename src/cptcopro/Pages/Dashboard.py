"""Dashboard CPTCOPRO — Tableau de bord enrichi pour conseil syndical.

KPIs affichés :
- Dernier relevé, créances actives, taux de recouvrement, alertes actives
- Copros débiteurs, débit moyen/débiteur, relances dues, brouillons en attente
- Top 5 débiteurs avec ancienneté de la dette
- Mini-balance âgée (donut 4 tranches)
- Évolution du débit global (graphe ligne)
"""

from __future__ import annotations

import loguru
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cptcopro.Database import get_relance_config, get_relance_drafts, list_relances_due
from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.analytics import compute_aging_balance, load_charges_dataset
from cptcopro.utils.ui_components import apply_plotly_theme, render_header

# ── Chargements de données complémentaires ───────────────────────────────────


@st.cache_data(ttl=300, show_spinner=False)
def _load_alertes_count() -> tuple[int, int]:
    """Nombre d'alertes actuel et précédent."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT nombre_alertes FROM suivi_alertes ORDER BY date_releve DESC LIMIT 2"
            )
            rows = list(cur.fetchall())
        actuel = int(rows[0]["nombre_alertes"]) if rows else 0
        precedent = int(rows[1]["nombre_alertes"]) if len(rows) >= 2 else actuel
        return actuel, precedent
    except Exception:
        return 0, 0


@st.cache_data(ttl=180, show_spinner=False)
def _load_relances_due_count() -> int:
    """Nombre de copropriétaires dont la relance est due aujourd'hui."""
    try:
        cfg = get_relance_config()
        freq = int(cfg.get("frequency_days", 14) or 14)
        rows = list_relances_due(freq)
        return len(rows) if rows else 0
    except Exception:
        return 0


@st.cache_data(ttl=120, show_spinner=False)
def _load_brouillons_en_attente() -> int:
    """Nombre de brouillons locaux non encore déposés sur IMAP."""
    try:
        drafts = get_relance_drafts(limit=500)
        if not drafts:
            return 0
        return sum(
            1 for d in drafts if str(d.get("status", "")).lower() in ("draft_local", "error")
        )
    except Exception:
        return 0


# ── Chargement principal ───────────────────────────────────────────────────

loguru.logger.info("Dashboard: chargement données")

charges_all = load_charges_dataset()
if not charges_all.empty:
    debit_global_df = (
        charges_all.groupby("date")["debit"]
        .sum()
        .reset_index()
        .rename(columns={"debit": "debit global"})
        .sort_values("date")
    )
    derniere_date = charges_all["date"].max()
    snapshot_df = charges_all[charges_all["date"] == derniere_date].copy()
    aging_df = compute_aging_balance(charges_all)
else:
    debit_global_df = pd.DataFrame()
    snapshot_df = pd.DataFrame()
    aging_df = pd.DataFrame()

nbre_alerte, nbre_alerte_precedent = _load_alertes_count()
nb_relances_dues = _load_relances_due_count()
nb_brouillons_attente = _load_brouillons_en_attente()

# ── Header ────────────────────────────────────────────────────────────────

render_header(
    "📊 Tableau de bord",
    "Synthèse financière et indicateurs clés de la copropriété",
)

if debit_global_df.empty:
    st.info(
        "👋 **Bienvenue dans CPTCOPRO !**\n\n"
        "Aucune donnée de charge n'a encore été importée dans la base de données. "
        "Pour commencer :\n\n"
        "1. **Importez vos données** via le module d'import (fichier CSV des charges)\n"
        "2. **Rafraîchissez** avec le bouton 🔄 dans la barre latérale\n"
        "3. Le tableau de bord se remplira automatiquement\n\n"
        "*Si les données ont déjà été importées, vérifiez la connexion à la base MariaDB.*"
    )
    st.stop()

st.divider()

# ── KPIs calculés ─────────────────────────────────────────────────────────

date_dernier = debit_global_df["date"].iat[-1]
date_precedent = debit_global_df["date"].iat[-2] if len(debit_global_df) >= 2 else None
charge_n = float(debit_global_df["debit global"].iat[-1])
charge_prec = float(debit_global_df["debit global"].iat[-2]) if len(debit_global_df) >= 2 else charge_n

nb_total = len(snapshot_df) if not snapshot_df.empty else 0
nb_debiteurs = int((snapshot_df["debit"] > 0).sum()) if not snapshot_df.empty else 0
nb_a_jour = nb_total - nb_debiteurs
taux_recouvrement = (nb_a_jour / nb_total * 100) if nb_total > 0 else 0.0
total_creances = float(snapshot_df[snapshot_df["debit"] > 0]["debit"].sum()) if not snapshot_df.empty else 0.0
debit_moyen = float(snapshot_df[snapshot_df["debit"] > 0]["debit"].mean()) if nb_debiteurs > 0 else 0.0
delta_alerte = nbre_alerte - nbre_alerte_precedent

# ── Ligne 1 : 4 KPIs principaux ──────────────────────────────────────────

k1, k2, k3, k4 = st.columns(4, gap="medium")

with k1:
    delta_date = f"Précédent : {date_precedent.strftime('%d/%m/%Y')}" if date_precedent is not None else None
    st.metric(
        "📅 Dernier relevé",
        value=date_dernier.strftime("%d/%m/%Y"),
        delta=delta_date,
        delta_color="off",
    )

with k2:
    delta_creances = charge_n - charge_prec
    st.metric(
        "💶 Créances actives",
        value=f"{total_creances:,.0f} €".replace(",", " "),
        delta=f"{delta_creances:+,.0f} €".replace(",", " "),
        delta_color="inverse",
        help="Somme des débits positifs au dernier relevé.",
    )

with k3:
    st.metric(
        "✅ Taux de recouvrement",
        value=f"{taux_recouvrement:.1f} %",
        delta=f"{nb_a_jour}/{nb_total} copros à jour",
        delta_color="off",
        help="Pourcentage de copropriétaires dont le solde est nul ou créditeur.",
    )

with k4:
    st.metric(
        "🚨 Alertes actives",
        value=nbre_alerte,
        delta=delta_alerte,
        delta_color="inverse",
        help="Copropriétaires dont le débit dépasse le seuil configuré.",
    )

st.space("small")

# ── Ligne 2 : 4 KPIs secondaires ─────────────────────────────────────────

k5, k6, k7, k8 = st.columns(4, gap="medium")

with k5:
    st.metric(
        "👥 Copros débiteurs",
        value=f"{nb_debiteurs}",
        delta=f"sur {nb_total} lots",
        delta_color="off",
        help="Nombre de copropriétaires présentant un débit positif au dernier relevé.",
    )

with k6:
    st.metric(
        "📊 Débit moyen / débiteur",
        value=f"{debit_moyen:,.0f} €".replace(",", " "),
        help="Moyenne des débits parmi les comptes débiteurs uniquement.",
    )

with k7:
    st.metric(
        "✉️ Relances dues",
        value=nb_relances_dues,
        help="Copropriétaires éligibles à une relance selon la fréquence configurée.",
        delta="à traiter" if nb_relances_dues > 0 else "Aucune",
        delta_color="inverse" if nb_relances_dues > 0 else "off",
    )

with k8:
    st.metric(
        "📬 Brouillons en attente",
        value=nb_brouillons_attente,
        help="Brouillons générés mais pas encore déposés sur Hotmail (IMAP).",
        delta="à déposer" if nb_brouillons_attente > 0 else "Aucun",
        delta_color="inverse" if nb_brouillons_attente > 0 else "off",
    )

st.divider()

# ── Graphe + Mini-aging ───────────────────────────────────────────────────

col_graph, col_aging = st.columns([2, 1], gap="large")

with col_graph:
    st.markdown("#### 📈 Évolution du débit global")
    chart = px.line(
        debit_global_df,
        x="date",
        y="debit global",
        markers=True,
    )
    chart.update_traces(line_color="#0284C7", marker=dict(size=7, color="#38BDF8"))
    chart.update_layout(
        xaxis_title="Date de relevé",
        yaxis_title="Débit global (€)",
        margin=dict(t=20, b=20),
    )
    chart = apply_plotly_theme(chart)
    st.plotly_chart(chart, width="stretch")

with col_aging:
    st.markdown("#### ⏳ Balance âgée")
    if aging_df.empty:
        st.success("🎉 Aucun impayé au dernier relevé !")
    else:
        aging_summary = (
            aging_df.groupby(["tranche", "order", "color"])["debit"]
            .sum()
            .reset_index()
            .sort_values("order")
        )
        fig_donut = go.Figure(
            go.Pie(
                labels=aging_summary["tranche"],
                values=aging_summary["debit"],
                hole=0.55,
                marker_colors=aging_summary["color"].tolist(),
                textinfo="label+percent",
                textposition="outside",
                showlegend=False,
            )
        )
        total_aging = aging_df["debit"].sum()
        fig_donut.update_layout(
            annotations=[
                dict(
                    text=f"<b>{total_aging:,.0f} €</b>".replace(",", " "),
                    x=0.5, y=0.5, font_size=14, showarrow=False,
                )
            ],
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
        )
        fig_donut = apply_plotly_theme(fig_donut)
        st.plotly_chart(fig_donut, width="stretch")
        # Légende compacte sous le donut
        leg_cols = st.columns(2)
        tranche_colors = [("< 30 j", "#22c55e"), ("30-60 j", "#f59e0b"), ("60-90 j", "#f97316"), ("> 90 j", "#ef4444")]
        for idx, (tname, tcolor) in enumerate(tranche_colors):
            row_data = aging_summary[aging_summary["tranche"] == tname]
            val = row_data["debit"].values[0] if not row_data.empty else 0.0
            leg_cols[idx % 2].markdown(
                f"<span style='color:{tcolor}'>●</span> **{tname}** : {val:,.0f} €".replace(",", " "),
                unsafe_allow_html=True,
            )

st.divider()

# ── Top 5 débiteurs ───────────────────────────────────────────────────────

st.markdown("#### 🔴 Top 5 débiteurs")
if aging_df.empty:
    st.info("Aucun compte débiteur au dernier relevé.")
else:
    top5 = aging_df.head(5).copy()
    anc_series = top5["jours"].apply(
        lambda j: f"{'🟢' if j <= 30 else '🟡' if j <= 60 else '🟠' if j <= 90 else '🔴'} {j} j"
    )
    debit_series = top5["debit"].apply(lambda v: f"{v:,.2f} €".replace(",", " "))
    nom_series = top5["nom"] if "nom" in top5.columns else top5.get("proprietaire", "")
    num_apt_series = top5["num_apt"] if "num_apt" in top5.columns else "—"
    type_apt_series = top5["type_apt"] if "type_apt" in top5.columns else "—"

    top5_display = pd.DataFrame({
        "Copropriétaire": nom_series,
        "Lot": num_apt_series,
        "Type": type_apt_series,
        "Débit": debit_series,
        "Ancienneté": anc_series,
        "Tranche": top5["tranche"],
    })

    top5_event = st.dataframe(
        top5_display,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="dashboard_top5_selection",
        column_config={
            "Débit": st.column_config.TextColumn("Débit actuel"),
            "Ancienneté": st.column_config.TextColumn("Ancienneté dette"),
            "Tranche": st.column_config.TextColumn("Balance âgée"),
        },
    )

    selected_rows = (
        top5_event.get("selection", {}).get("rows", [])
        if isinstance(top5_event, dict)
        else getattr(getattr(top5_event, "selection", None), "rows", [])
    )
    if selected_rows and len(selected_rows) > 0:
        sel_idx = int(selected_rows[0])
        if sel_idx < len(top5):
            sel_copro = top5.iloc[sel_idx]
            sel_nom = str(sel_copro["nom"])
            sel_code = str(sel_copro["code"])
            col_sel_info, col_sel_fiche, col_sel_relance = st.columns([2, 1.2, 1.2], gap="small")
            with col_sel_info:
                st.info(f"👉 Sélectionné : **{sel_nom}** (Code : `{sel_code}` — {sel_copro['Débit']})")
            with col_sel_fiche:
                if st.button("👤 Voir la fiche 360°", key="top5_btn_fiche", width="stretch"):
                    st.session_state["target_fiche_copro"] = sel_code
                    st.switch_page("Pages/Rechercher_Copro.py")
            with col_sel_relance:
                if st.button("✉️ Préparer une relance", type="primary", key="top5_btn_relance", width="stretch"):
                    st.session_state["target_relance_copro"] = sel_code
                    st.switch_page("Pages/Relance.py")

    if nb_relances_dues > 0:
        col_btn, _ = st.columns([1.5, 4])
        with col_btn:
            if st.button("✉️ Aller aux relances dues →", width="stretch", type="primary"):
                st.switch_page("Pages/Relance.py")

st.divider()

# ── Historique complet ────────────────────────────────────────────────────

with st.expander("📋 Historique complet des relevés"):
    st.dataframe(
        debit_global_df.sort_values(by="date", ascending=False),
        width="stretch",
        hide_index=True,
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "debit global": st.column_config.NumberColumn("Débit global (€)", format="%.2f €"),
        },
    )
