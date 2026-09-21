"""Page Bilan AG — Rapport annuel de la copropriété pour l'Assemblée Générale.

Sections :
- Sélecteur d'année
- Résumé financier de l'année (créances, taux recouvrement, évolution)
- Balance âgée au dernier relevé de l'année
- Évolution mensuelle des créances
- Copropriétaires en anomalie persistante (> 90j)
- Efficacité des relances (relances envoyées, comptes régularisés)
- Répartition par type de lot
- Export HTML imprimable (PDF via navigateur)
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cptcopro.Database import get_relance_config, get_relance_drafts
from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


# ── Chargements ────────────────────────────────────────────────────────────


@st.cache_data(ttl=300, show_spinner=False)
def _load_all_charges() -> pd.DataFrame:
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT nom_proprietaire, code_proprietaire, num_apt, type_apt, debit, credit, date "
                "FROM vw_charge_coproprietaires"
            )
            df = pd.DataFrame(cur.fetchall())
        # Conversion explicite en datetime64 (normalize_date_columns insuffisant sur certains types)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0)
        df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0)
        return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    except Exception as e:
        st.error(f"Erreur chargement charges : {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def _load_drafts() -> list[dict]:
    try:
        return get_relance_drafts(limit=2000) or []
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _load_nb_copros() -> int:
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS nb FROM coproprietaires")
            row = cur.fetchone()
            return int(row["nb"]) if row else 0
    except Exception:
        return 0


# ── Calculs ────────────────────────────────────────────────────────────────


def _compute_aging(df_annee: pd.DataFrame, annee: int) -> pd.DataFrame:
    """Balance âgée au dernier relevé de l'année."""
    if df_annee.empty:
        return pd.DataFrame()
    derniere_date = df_annee["date"].max()
    snap = df_annee[df_annee["date"] == derniere_date]
    debiteurs = snap[snap["debit"] > 0].copy()
    if debiteurs.empty:
        return pd.DataFrame()

    records = []
    for _, row in debiteurs.iterrows():
        code = row["code_proprietaire"]
        hist = df_annee[df_annee["code_proprietaire"] == code].sort_values("date")
        date_debut = derniere_date
        for _, h in hist.iloc[::-1].iterrows():
            if float(h["debit"]) > 0:
                date_debut = h["date"]
            else:
                break
        jours = max(0, (derniere_date - date_debut).days)
        if jours <= 30:
            tranche, order, color = "< 30 j", 1, "#22c55e"
        elif jours <= 60:
            tranche, order, color = "30-60 j", 2, "#f59e0b"
        elif jours <= 90:
            tranche, order, color = "60-90 j", 3, "#f97316"
        else:
            tranche, order, color = "> 90 j", 4, "#ef4444"
        records.append({
            "Copropriétaire": row["nom_proprietaire"],
            "Lot": row.get("num_apt", "—"),
            "Type": row.get("type_apt", "—"),
            "Débit (€)": float(row["debit"]),
            "Ancienneté (j)": jours,
            "Tranche": tranche,
            "order": order,
            "color": color,
        })
    return pd.DataFrame(records).sort_values("Débit (€)", ascending=False)


# ── Header ─────────────────────────────────────────────────────────────────

render_header(
    "📋 Bilan AG — Rapport annuel",
    "Synthèse financière annuelle pour l'Assemblée Générale de copropriété",
)

charges_all = _load_all_charges()
drafts_all = _load_drafts()
nb_copros_total = _load_nb_copros()

if charges_all.empty:
    st.warning("⚠️ Aucune donnée de charges disponible.")
    st.stop()

# ── Sélecteur d'année ──────────────────────────────────────────────────────

annees_disponibles = sorted(charges_all["date"].dt.year.unique(), reverse=True)
annee_courante = date.today().year

col_sel, col_info, _ = st.columns([1.2, 2.5, 3], gap="medium")
with col_sel:
    annee = st.selectbox(
        "📅 Année du bilan :",
        options=annees_disponibles,
        index=0 if annees_disponibles[0] == annee_courante else 0,
        key="bilan_annee",
    )
with col_info:
    st.info(
        f"Rapport pour l'exercice **{annee}** — données du {annee}/01/01 au {annee}/12/31."
    )

# ── Filtrage des données sur l'année ─────────────────────────────────────

df_annee = charges_all[charges_all["date"].dt.year == annee].copy()
df_annee_prev = charges_all[charges_all["date"].dt.year == (annee - 1)].copy()

if df_annee.empty:
    st.warning(f"⚠️ Aucune donnée pour l'exercice {annee}.")
    st.stop()

# Snapshots début / fin d'année
derniere_date_annee = df_annee["date"].max()
premiere_date_annee = df_annee["date"].min()
snap_fin = df_annee[df_annee["date"] == derniere_date_annee]
snap_debut = df_annee[df_annee["date"] == premiere_date_annee]

# Calculs globaux
total_creances_fin = float(snap_fin[snap_fin["debit"] > 0]["debit"].sum())
total_creances_debut = float(snap_debut[snap_debut["debit"] > 0]["debit"].sum()) if not snap_debut.empty else 0.0
nb_debiteurs_fin = int((snap_fin["debit"] > 0).sum())
nb_a_jour_fin = len(snap_fin) - nb_debiteurs_fin
nb_total_snap = len(snap_fin)
taux_recouvrement = (nb_a_jour_fin / nb_total_snap * 100) if nb_total_snap > 0 else 0.0

# Relances de l'année
drafts_annee = [
    d for d in drafts_all
    if d.get("created_at") and str(d.get("created_at", ""))[:4] == str(annee)
]
nb_relances_envoyees = len(drafts_annee)
codes_relances = {str(d.get("code_proprietaire", "")) for d in drafts_annee}

# Comptes régularisés après relance : débiteurs au début de l'année et à jour à la fin
codes_debiteurs_debut = set(snap_debut[snap_debut["debit"] > 0]["code_proprietaire"].astype(str))
codes_a_jour_fin = set(snap_fin[snap_fin["debit"] <= 0]["code_proprietaire"].astype(str))
codes_regularises = codes_debiteurs_debut & codes_a_jour_fin & codes_relances

st.divider()

# ── Résumé financier ──────────────────────────────────────────────────────

st.markdown("## 💶 Résumé Financier de l'Exercice")
variation = total_creances_fin - total_creances_debut
signe = "+" if variation >= 0 else ""

k1, k2, k3, k4, k5 = st.columns(5, gap="medium")
with k1:
    st.metric(
        "Créances fin d'exercice",
        f"{total_creances_fin:,.0f} €".replace(",", " "),
        delta=f"{signe}{variation:,.0f} €".replace(",", " "),
        delta_color="inverse",
        help=f"Total des débits au {derniere_date_annee.strftime('%d/%m/%Y')}",
    )
with k2:
    st.metric(
        "Copros débiteurs",
        f"{nb_debiteurs_fin}",
        delta=f"sur {nb_total_snap} lots",
        delta_color="off",
    )
with k3:
    st.metric(
        "Taux de recouvrement",
        f"{taux_recouvrement:.1f} %",
        delta=f"{nb_a_jour_fin}/{nb_total_snap} à jour",
        delta_color="off",
    )
with k4:
    st.metric(
        "Relances envoyées",
        nb_relances_envoyees,
        delta=f"{len(codes_relances)} copros relancées",
        delta_color="off",
    )
with k5:
    st.metric(
        "Comptes régularisés",
        len(codes_regularises),
        delta=(
            f"{len(codes_regularises)/len(codes_debiteurs_debut)*100:.0f}% taux efficacité"
            if codes_debiteurs_debut else "N/A"
        ),
        delta_color="normal",
        help="Copros débitrices en début d'année, à jour en fin d'année, et ayant reçu une relance.",
    )

st.divider()

# ── Évolution mensuelle ───────────────────────────────────────────────────

st.markdown("## 📈 Évolution Mensuelle des Créances")

# Débit global par date de relevé (sur l'année)
evol_mensuelle = (
    df_annee.groupby("date")["debit"]
    .sum()
    .reset_index()
    .rename(columns={"debit": "Débit global (€)"})
    .sort_values("date")
)

fig_evol = px.line(
    evol_mensuelle,
    x="date",
    y="Débit global (€)",
    markers=True,
    labels={"date": "Relevé"},
)
fig_evol.update_traces(line_color="#0284C7", marker=dict(size=8, color="#38BDF8"))
fig_evol.update_layout(margin=dict(t=20, b=20))
fig_evol = apply_plotly_theme(fig_evol)
st.plotly_chart(fig_evol, width="stretch")

st.divider()

# ── Balance âgée ─────────────────────────────────────────────────────────

st.markdown(f"## ⏳ Balance Âgée au {derniere_date_annee.strftime('%d/%m/%Y')}")
st.caption(
    "Ancienneté ininterrompue de chaque dette : remonte dans l'historique "
    "jusqu'au premier relevé où le débit était positif sans interruption."
)

aging_df = _compute_aging(charges_all, annee)

if aging_df.empty:
    st.success("🎉 Aucun compte débiteur au dernier relevé de l'exercice.")
else:
    aging_summary = (
        aging_df.groupby(["Tranche", "order", "color"])["Débit (€)"]
        .agg(["sum", "count"])
        .reset_index()
        .sort_values("order")
    )

    col_donut, col_aging_kpi = st.columns([1.2, 2], gap="large")

    with col_donut:
        total_aging = aging_df["Débit (€)"].sum()
        fig_donut = go.Figure(
            go.Pie(
                labels=aging_summary["Tranche"],
                values=aging_summary["sum"],
                hole=0.55,
                marker_colors=aging_summary["color"].tolist(),
                textinfo="label+percent",
                showlegend=False,
            )
        )
        fig_donut.update_layout(
            annotations=[
                dict(
                    text=f"<b>{total_aging:,.0f} €</b>".replace(",", " "),
                    x=0.5, y=0.5, font_size=13, showarrow=False,
                )
            ],
            margin=dict(t=10, b=10, l=5, r=5),
            height=260,
        )
        fig_donut = apply_plotly_theme(fig_donut)
        st.plotly_chart(fig_donut, width="stretch")

    with col_aging_kpi:
        color_map = {"< 30 j": "#22c55e", "30-60 j": "#f59e0b", "60-90 j": "#f97316", "> 90 j": "#ef4444"}
        for _, row in aging_summary.iterrows():
            color = color_map.get(str(row["Tranche"]), "#888")
            st.markdown(
                f"<span style='color:{color}; font-size:1.1em'>●</span> "
                f"**{row['Tranche']}** — "
                f"{int(row['count'])} compte(s) — "
                f"**{row['sum']:,.0f} €**".replace(",", " "),
                unsafe_allow_html=True,
            )
        st.write("")
        # Tableau des débiteurs > 90j
        df_critique = aging_df[aging_df["Tranche"] == "> 90 j"]
        if not df_critique.empty:
            st.markdown(f"**⚠️ {len(df_critique)} compte(s) en anomalie persistante (> 90 jours) :**")
            st.dataframe(
                df_critique[["Copropriétaire", "Lot", "Type", "Débit (€)", "Ancienneté (j)"]],
                width="stretch",
                hide_index=True,
                column_config={
                    "Débit (€)": st.column_config.NumberColumn(format="%.2f €"),
                    "Ancienneté (j)": st.column_config.NumberColumn(format="%d j"),
                },
            )

    st.write("")
    with st.expander("📋 Détail complet de la balance âgée", expanded=False):
        st.dataframe(
            aging_df.drop(columns=["order", "color"], errors="ignore"),
            width="stretch",
            hide_index=True,
            column_config={
                "Débit (€)": st.column_config.NumberColumn(format="%.2f €"),
                "Ancienneté (j)": st.column_config.NumberColumn(format="%d j"),
            },
        )

st.divider()

# ── Répartition par type de lot ───────────────────────────────────────────

st.markdown("## 🏠 Répartition des Créances par Type de Lot")

snap_fin_debiteurs = snap_fin[snap_fin["debit"] > 0].copy()
if snap_fin_debiteurs.empty:
    st.info("Aucune créance à répartir.")
else:
    type_repartition = (
        snap_fin_debiteurs.groupby("type_apt")["debit"]
        .agg(["sum", "count"])
        .reset_index()
        .rename(columns={"type_apt": "Type", "sum": "Total (€)", "count": "Nb comptes"})
    )
    col_bar, col_pie = st.columns(2, gap="large")
    with col_bar:
        fig_bar = px.bar(
            type_repartition,
            x="Type",
            y="Total (€)",
            text_auto=".0f",
            color="Type",
            labels={"Total (€)": "Créances (€)"},
        )
        fig_bar.update_layout(showlegend=False, margin=dict(t=20, b=20))
        fig_bar = apply_plotly_theme(fig_bar)
        st.plotly_chart(fig_bar, width="stretch")
    with col_pie:
        fig_pie = px.pie(
            type_repartition,
            names="Type",
            values="Total (€)",
            hole=0.4,
        )
        fig_pie.update_layout(margin=dict(t=10, b=10))
        fig_pie = apply_plotly_theme(fig_pie)
        st.plotly_chart(fig_pie, width="stretch")

st.divider()

# ── Efficacité des relances ───────────────────────────────────────────────

st.markdown("## ✉️ Efficacité du Recouvrement par Relance")

if not drafts_annee:
    st.info(f"Aucune relance enregistrée pour l'exercice {annee}.")
else:
    # Résumé par statut
    status_counts: dict[str, int] = {}
    for d in drafts_annee:
        s = str(d.get("status") or "inconnu").lower()
        status_counts[s] = status_counts.get(s, 0) + 1

    status_labels = {
        "sent": "✅ Envoyé",
        "draft_imap": "📤 Déposé Hotmail",
        "draft_local": "📝 Brouillon local",
        "error": "❌ Erreur",
        "deleted": "🗑️ Supprimé",
    }
    col_relances = st.columns(min(len(status_counts), 5), gap="medium")
    for idx, (s, cnt) in enumerate(status_counts.items()):
        col_relances[idx % len(col_relances)].metric(
            status_labels.get(s, s.upper()),
            cnt,
        )

    # Tableau des relances de l'année
    with st.expander(f"📜 Journal des {nb_relances_envoyees} relances de l'exercice {annee}", expanded=False):
        df_drafts = pd.DataFrame([
            {
                "Date": str(d.get("created_at", ""))[:10],
                "Copropriétaire": d.get("nom_proprietaire", "—"),
                "Lot": d.get("code_proprietaire", "—"),
                "Débit (€)": float(d.get("debit") or 0),
                "Objet": str(d.get("subject") or "")[:60],
                "Statut": str(d.get("status") or "—"),
                "Rédigé par": str(d.get("llm_provider") or "template"),
            }
            for d in drafts_annee
        ])
        st.dataframe(
            df_drafts,
            width="stretch",
            hide_index=True,
            column_config={
                "Débit (€)": st.column_config.NumberColumn(format="%.2f €"),
            },
        )

st.divider()

# ── Export ────────────────────────────────────────────────────────────────

st.markdown("## 📥 Exporter ce rapport")

col_exp1, col_exp2, _ = st.columns([1.5, 1.5, 3], gap="medium")

# Export CSV balance âgée
with col_exp1:
    if not aging_df.empty:
        csv_buf = io.StringIO()
        aging_df.drop(columns=["order", "color"], errors="ignore").to_csv(
            csv_buf, index=False, sep=";"
        )
        st.download_button(
            "📥 Balance âgée (CSV)",
            data=csv_buf.getvalue().encode("utf-8-sig"),
            file_name=f"balance_agee_{annee}.csv",
            mime="text/csv",
            width="stretch",
        )

# Export CSV rapport complet
with col_exp2:
    lines = [
        f"RAPPORT AG — EXERCICE {annee}",
        f"Généré le {date.today().strftime('%d/%m/%Y')}",
        "",
        "=== RÉSUMÉ FINANCIER ===",
        f"Créances fin d'exercice : {total_creances_fin:,.2f} EUR".replace(",", " "),
        f"Variation vs début d'exercice : {signe}{variation:,.2f} EUR".replace(",", " "),
        f"Copropriétaires débiteurs : {nb_debiteurs_fin} / {nb_total_snap}",
        f"Taux de recouvrement : {taux_recouvrement:.1f} %",
        "",
        "=== RELANCES ===",
        f"Relances enregistrées : {nb_relances_envoyees}",
        f"Comptes relancés : {len(codes_relances)}",
        f"Comptes régularisés : {len(codes_regularises)}",
        "",
        "=== BALANCE ÂGÉE ===",
    ]
    if not aging_df.empty:
        for _, row in aging_summary.iterrows():
            lines.append(
                f"{row['Tranche']} : {int(row['count'])} compte(s) — {row['sum']:,.2f} EUR".replace(",", " ")
            )
    rapport_txt = "\n".join(lines)
    st.download_button(
        "📄 Résumé AG (TXT)",
        data=rapport_txt.encode("utf-8"),
        file_name=f"rapport_AG_{annee}.txt",
        mime="text/plain",
        width="stretch",
    )

st.caption(
    "💡 **Astuce** : Pour obtenir un PDF, utilisez la fonction d'impression du navigateur "
    "(Ctrl+P) et sélectionnez « Enregistrer au format PDF »."
)

