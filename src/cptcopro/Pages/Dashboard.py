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
from cptcopro.utils.db_helpers import normalize_date_columns
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


# ── Chargements de données ─────────────────────────────────────────────────


@st.cache_data(ttl=300, show_spinner=False)
def _load_debit_global() -> pd.DataFrame:
    """Débit global agrégé par date (historique)."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT sum(debit) AS 'debit global', date "
                "FROM vw_charge_coproprietaires GROUP BY date"
            )
            df = pd.DataFrame(cur.fetchall())
        df = normalize_date_columns(df, ["date"])
        if "debit global" in df.columns:
            df["debit global"] = pd.to_numeric(df["debit global"], errors="coerce").fillna(0)
        return df.dropna(subset=["date"]).sort_values("date")
    except Exception as e:
        st.error(f"Erreur chargement débit global : {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def _load_snapshot_derniere_date() -> pd.DataFrame:
    """Snapshot complet du dernier relevé : débit, crédit, nom, lot, type par copropriétaire."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT nom_proprietaire, code_proprietaire, num_apt, type_apt, debit, credit, date "
                "FROM vw_charge_coproprietaires "
                "WHERE date = (SELECT MAX(date) FROM vw_charge_coproprietaires)"
            )
            df = pd.DataFrame(cur.fetchall())
        if df.empty:
            return df
        df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0)
        df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0)
        return df
    except Exception as e:
        st.error(f"Erreur chargement snapshot : {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def _load_historique_charges() -> pd.DataFrame:
    """Historique complet de tous les relevés (pour calcul ancienneté)."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT code_proprietaire, debit, date "
                "FROM vw_charge_coproprietaires ORDER BY date ASC"
            )
            df = pd.DataFrame(cur.fetchall())
        df = normalize_date_columns(df, ["date"])
        df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0)
        return df.dropna(subset=["date"])
    except Exception as e:
        return pd.DataFrame()


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
    except Exception as e:
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


# ── Calculs de la balance âgée (ancienneté ininterrompue) ─────────────────


def _compute_aging(snapshot_df: pd.DataFrame, hist_df: pd.DataFrame) -> pd.DataFrame:
    """Calcule la tranche d'âge de la dette pour chaque débiteur du dernier relevé."""
    if snapshot_df.empty or hist_df.empty:
        return pd.DataFrame()

    derniere_date = snapshot_df["date"].max() if "date" in snapshot_df.columns else pd.NaT
    debiteurs = snapshot_df[snapshot_df["debit"] > 0].copy()
    if debiteurs.empty:
        return pd.DataFrame()

    records = []
    for _, row in debiteurs.iterrows():
        code = row["code_proprietaire"]
        copro_hist = hist_df[hist_df["code_proprietaire"] == code].sort_values("date")
        if copro_hist.empty:
            continue
        date_debut = row.get("date", derniere_date) if pd.notna(row.get("date")) else derniere_date
        for _, h in copro_hist.iloc[::-1].iterrows():
            if float(h["debit"]) > 0:
                date_debut = h["date"]
            else:
                break
        jours = max(0, (derniere_date - date_debut).days) if pd.notna(derniere_date) and pd.notna(date_debut) else 0
        if jours <= 30:
            tranche = "< 30 j"
            order = 1
            color = "#22c55e"
        elif jours <= 60:
            tranche = "30-60 j"
            order = 2
            color = "#f59e0b"
        elif jours <= 90:
            tranche = "60-90 j"
            order = 3
            color = "#f97316"
        else:
            tranche = "> 90 j"
            order = 4
            color = "#ef4444"
        records.append({
            "code": code,
            "nom": row["nom_proprietaire"],
            "num_apt": row.get("num_apt", "—"),
            "type_apt": row.get("type_apt", "—"),
            "debit": float(row["debit"]),
            "jours": jours,
            "tranche": tranche,
            "order": order,
            "color": color,
        })
    return pd.DataFrame(records).sort_values("debit", ascending=False)


# ── Chargement ────────────────────────────────────────────────────────────

loguru.logger.info("Dashboard: chargement données")

debit_global_df = _load_debit_global()
snapshot_df = _load_snapshot_derniere_date()
hist_df = _load_historique_charges()
nbre_alerte, nbre_alerte_precedent = _load_alertes_count()
nb_relances_dues = _load_relances_due_count()
nb_brouillons_attente = _load_brouillons_en_attente()
aging_df = _compute_aging(snapshot_df, hist_df)

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

st.write("")

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
    st.plotly_chart(chart, use_container_width=True)

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
        st.plotly_chart(fig_donut, use_container_width=True)
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
    top5["Ancienneté"] = top5["jours"].apply(
        lambda j: f"{'🟢' if j <= 30 else '🟡' if j <= 60 else '🟠' if j <= 90 else '🔴'} {j} j"
    )
    top5["Débit"] = top5["debit"].apply(lambda v: f"{v:,.2f} €".replace(",", " "))
    top5_display = top5.rename(columns={
        "nom": "Copropriétaire",
        "num_apt": "Lot",
        "type_apt": "Type",
        "tranche": "Tranche",
    })[["Copropriétaire", "Lot", "Type", "Débit", "Ancienneté", "Tranche"]]

    st.dataframe(
        top5_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Débit": st.column_config.TextColumn("Débit actuel"),
            "Ancienneté": st.column_config.TextColumn("Ancienneté dette"),
            "Tranche": st.column_config.TextColumn("Balance âgée"),
        },
    )

    if nb_relances_dues > 0:
        col_btn, _ = st.columns([1.5, 4])
        with col_btn:
            if st.button("✉️ Aller aux relances dues →", use_container_width=True, type="primary"):
                st.switch_page("Pages/Relance.py")

st.divider()

# ── Historique complet ────────────────────────────────────────────────────

with st.expander("📋 Historique complet des relevés"):
    st.dataframe(
        debit_global_df.sort_values(by="date", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "debit global": st.column_config.NumberColumn("Débit global (€)", format="%.2f €"),
        },
    )
