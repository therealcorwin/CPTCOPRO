"""Page Streamlit pour les analyses et statistiques avancées."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import fetch_dataframe
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
)
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


@st.cache_data(ttl=300, show_spinner=False)
def load_charges() -> pd.DataFrame:
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, "
            "num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires"
        )
        df = fetch_dataframe(cur)
    if df.empty:
        df["mois"] = pd.Series(dtype=int)
        df["annee"] = pd.Series(dtype=int)
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["mois"] = df["date"].dt.month
    df["annee"] = df["date"].dt.year
    return df


@st.cache_data(ttl=300, show_spinner=False)
def load_alertes() -> pd.DataFrame:
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, "
            "debit, type_alerte, first_detection, last_detection, occurence "
            "FROM alertes_debit_eleve"
        )
        df = fetch_dataframe(cur)
    if df.empty:
        df["duree_jours"] = pd.Series(dtype=float)
        return df
    df["first_detection"] = pd.to_datetime(df["first_detection"], errors="coerce")
    df["last_detection"] = pd.to_datetime(df["last_detection"], errors="coerce")
    df["duree_jours"] = (df["last_detection"] - df["first_detection"]).dt.days
    return df


@st.cache_data(ttl=300, show_spinner=False)
def load_config_alertes() -> pd.DataFrame:
    with get_db_cursor() as cur:
        cur.execute("SELECT type_apt, charge_moyenne, taux, threshold FROM config_alerte")
        return fetch_dataframe(cur)


@st.cache_data(ttl=300, show_spinner=False)
def load_coproprietaires() -> pd.DataFrame:
    with get_db_cursor() as cur:
        cur.execute("SELECT nom_proprietaire, code_proprietaire, type_apt FROM coproprietaires")
        return fetch_dataframe(cur)


render_header(
    "📊 Analyses & Statistiques Avancées",
    "Distribution des soldes, ratios de solvabilité, récidives et détection précoce des risques",
)

charges_df = load_charges()
alertes_df = load_alertes()
config_df = load_config_alertes()
copro_df = load_coproprietaires()


if charges_df.empty:
    st.info(
        "⚠️ **Aucune donnée disponible pour l'analyse.**\n\n"
        "Cette page nécessite des données de charges importées dans la base. "
        "Commencez par importer vos relevés via le module d'import, puis revenez ici "
        "pour accéder aux analyses avancées (balance âgée, distributions, prévisions)."
    )
    st.stop()

derniere_date = charges_df["date"].max()
derniers_debits = charges_df[charges_df["date"] == derniere_date].copy()

# Enrichir avec les types d'appartements
derniers_debits_typed = derniers_debits.merge(
    copro_df[["code_proprietaire", "type_apt"]].rename(columns={"code_proprietaire": "code"}),
    on="code",
    how="left",
    suffixes=("", "_copro"),
)
derniers_debits_typed["type_apt"] = (
    derniers_debits_typed["type_apt_copro"].fillna(derniers_debits_typed["type_apt"]).fillna("NA")
)

tab_aging, tab_distrib, tab_risques, tab_recidive, tab_saison, tab_prevision = st.tabs(
    [
        "⏳ 1. Balance Âgée (Aging)",
        "📊 2. Distribution & Ratios",
        "⚠️ 3. Détection Précoce (Risques)",
        "🔁 4. Récidives & Durée",
        "📅 5. Typologie & Saisonnalité",
        "🔮 6. Prévision",
    ]
)


# ============================================================================
# ONGLET 1: BALANCE ÂGÉE DES CRÉANCES
# ============================================================================
with tab_aging:
    st.subheader(f"⏳ Balance Âgée des Créances au {derniere_date.strftime('%d/%m/%Y')}")
    st.caption(
        "Ventilation de l'ancienneté des soldes débiteurs ininterrompus par tranches d'âge standard (<30j, 30-60j, 60-90j, >90j)."
    )

    aging_records = []
    for code, group in charges_df.groupby("code"):
        group_sorted = group.sort_values("date", ascending=True)
        derniere_ligne = group_sorted.iloc[-1]
        debit_actuel = float(derniere_ligne["debit"])

        if debit_actuel > 0:
            reversed_rows = group_sorted.iloc[::-1]
            date_debut_dette = derniere_ligne["date"]
            for _, r in reversed_rows.iterrows():
                if float(r["debit"]) > 0:
                    date_debut_dette = r["date"]
                else:
                    break

            jours_anciennete = max(0, (derniere_date - date_debut_dette).days)

            if jours_anciennete <= 30:
                tranche = "< 30 jours"
                tranche_order = 1
            elif jours_anciennete <= 60:
                tranche = "30 - 60 jours"
                tranche_order = 2
            elif jours_anciennete <= 90:
                tranche = "60 - 90 jours"
                tranche_order = 3
            else:
                tranche = "> 90 jours"
                tranche_order = 4

            aging_records.append(
                {
                    "code": code,
                    "proprietaire": derniere_ligne["proprietaire"],
                    "num_apt": derniere_ligne.get("num_apt", "N/A"),
                    "type_apt": derniere_ligne.get("type_apt", "N/A"),
                    "debit": debit_actuel,
                    "date_debut_dette": date_debut_dette,
                    "jours_anciennete": jours_anciennete,
                    "tranche": tranche,
                    "tranche_order": tranche_order,
                }
            )

    if not aging_records:
        st.success("🎉 Aucun compte débiteur au dernier relevé ! Toutes les charges sont apurées.")
    else:
        df_aging = pd.DataFrame(aging_records)

        total_creances = df_aging["debit"].sum()
        nb_debiteurs = len(df_aging)

        tranche_30 = df_aging[df_aging["tranche"] == "< 30 jours"]
        tranche_60 = df_aging[df_aging["tranche"] == "30 - 60 jours"]
        tranche_90 = df_aging[df_aging["tranche"] == "60 - 90 jours"]
        tranche_plus90 = df_aging[df_aging["tranche"] == "> 90 jours"]

        col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5, gap="small")
        with col_k1:
            st.metric(
                "Total Créances",
                f"{total_creances:,.2f} €".replace(",", " "),
                delta=f"{nb_debiteurs} débiteur(s)",
                delta_color="off",
            )
        with col_k2:
            st.metric(
                "< 30 jours (Courant)",
                f"{tranche_30['debit'].sum():,.2f} €".replace(",", " "),
                delta=f"{len(tranche_30)} compte(s)",
                delta_color="off",
            )
        with col_k3:
            st.metric(
                "30 - 60 jours (Rappel)",
                f"{tranche_60['debit'].sum():,.2f} €".replace(",", " "),
                delta=f"{len(tranche_60)} compte(s)",
                delta_color="inverse",
            )
        with col_k4:
            st.metric(
                "60 - 90 jours (Alerte)",
                f"{tranche_90['debit'].sum():,.2f} €".replace(",", " "),
                delta=f"{len(tranche_90)} compte(s)",
                delta_color="inverse",
            )
        with col_k5:
            st.metric(
                "> 90 jours (Critique)",
                f"{tranche_plus90['debit'].sum():,.2f} €".replace(",", " "),
                delta=f"{len(tranche_plus90)} compte(s)",
                delta_color="inverse",
            )

        st.divider()

        col_g_age1, col_g_age2 = st.columns([1.5, 1], gap="large")
        colors_map = {
            "< 30 jours": "#10B981",
            "30 - 60 jours": "#F59E0B",
            "60 - 90 jours": "#F97316",
            "> 90 jours": "#EF4444",
        }

        with col_g_age1:
            summary_aging = (
                df_aging.groupby(["tranche", "tranche_order"])
                .agg(TotalDebit=("debit", "sum"), Nombre=("code", "count"))
                .reset_index()
                .sort_values("tranche_order")
            )
            fig_aging_bar = px.bar(
                summary_aging,
                x="tranche",
                y="TotalDebit",
                color="tranche",
                color_discrete_map=colors_map,
                text_auto=".2f",
                title="Créances cumulées par tranche d'ancienneté (€)",
                labels={"tranche": "Classe d'âge", "TotalDebit": "Montant (€)"},
            )
            fig_aging_bar.update_layout(showlegend=False)
            fig_aging_bar = apply_plotly_theme(fig_aging_bar)
            st.plotly_chart(fig_aging_bar, width="stretch")

        with col_g_age2:
            fig_aging_pie = px.pie(
                summary_aging,
                values="TotalDebit",
                names="tranche",
                color="tranche",
                color_discrete_map=colors_map,
                hole=0.4,
                title="Part des impayés par classe d'âge",
            )
            fig_aging_pie = apply_plotly_theme(fig_aging_pie)
            st.plotly_chart(fig_aging_pie, width="stretch")

        st.divider()

        col_filtre_age, _ = st.columns([1.5, 2])
        with col_filtre_age:
            filtre_tranche = st.selectbox(
                "Filtrer le tableau par classe d'âge :",
                options=["Toutes", "< 30 jours", "30 - 60 jours", "60 - 90 jours", "> 90 jours"],
                index=0,
                key="aging_tranche_filter",
            )

        df_aging_filtre = df_aging.copy()
        if filtre_tranche != "Toutes":
            df_aging_filtre = df_aging_filtre[df_aging_filtre["tranche"] == filtre_tranche]

        df_aging_filtre["date_debut_str"] = pd.to_datetime(
            df_aging_filtre["date_debut_dette"]
        ).dt.strftime("%d/%m/%Y")

        st.markdown(f"**{len(df_aging_filtre)} compte(s) débiteur(s) affiché(s)**")
        st.dataframe(
            appliquer_confidentialite(
                df_aging_filtre.sort_values(
                    by=["tranche_order", "debit"], ascending=[False, False]
                )
            ),
            width="stretch",
            hide_index=True,
            column_config={
                "proprietaire": st.column_config.TextColumn("Copropriétaire", width="large"),
                "code": st.column_config.TextColumn("Code", width="small"),
                "num_apt": st.column_config.TextColumn("Lot", width="small"),
                "type_apt": st.column_config.TextColumn("Type", width="small"),
                "debit": st.column_config.NumberColumn(
                    "Débit total (€)", format="%.2f €", width="medium"
                ),
                "tranche": st.column_config.TextColumn("Tranche d'ancienneté", width="medium"),
                "jours_anciennete": st.column_config.NumberColumn(
                    "Ancienneté (jours)", format="%d j", width="small"
                ),
                "date_debut_str": st.column_config.TextColumn(
                    "Dette ininterrompue depuis", width="medium"
                ),
            },
        )


# ============================================================================
# ONGLET 2: DISTRIBUTION & RATIOS
# ============================================================================
with tab_distrib:
    st.subheader(f"Distribution des soldes au {derniere_date.strftime('%d/%m/%Y')}")

    col_d1, col_d2 = st.columns(2, gap="large")

    with col_d1:
        fig_hist = px.histogram(
            derniers_debits,
            x="debit",
            nbins=25,
            title="Histogramme des débits (€)",
            labels={"debit": "Débit (€)", "count": "Nombre de copropriétaires"},
            color_discrete_sequence=["#0284C7"],
        )
        for _, row in config_df.iterrows():
            if row["type_apt"] != "default":
                fig_hist.add_vline(
                    x=row["threshold"],
                    line_dash="dash",
                    line_color="#EF4444",
                    annotation_text=f"Seuil {row['type_apt'].upper()}",
                    annotation_position="top",
                )
        fig_hist = apply_plotly_theme(fig_hist)
        st.plotly_chart(fig_hist, width="stretch")

    with col_d2:
        st.markdown("#### Indicateurs statistiques descriptifs")
        stats = derniers_debits["debit"].describe()

        c_a, c_b = st.columns(2, gap="medium")
        with c_a:
            st.metric("Moyenne", f"{stats['mean']:,.2f} €".replace(",", " "))
            st.metric("Minimum", f"{stats['min']:,.2f} €".replace(",", " "))
            st.metric("Comptes analysés", int(stats["count"]))
        with c_b:
            st.metric("Médiane (50%)", f"{stats['50%']:,.2f} €".replace(",", " "))
            st.metric("Maximum", f"{stats['max']:,.2f} €".replace(",", " "))
            st.metric("Écart-type", f"{stats['std']:,.2f} €".replace(",", " "))

    st.divider()

    # --- Ratios Crédit / Débit ---
    st.subheader("Ratio de couverture (Crédit / Débit)")
    derniers_debits_ratio = derniers_debits.copy()
    derniers_debits_ratio["ratio"] = derniers_debits_ratio.apply(
        lambda r: r["credit"] / r["debit"] if r["debit"] > 0 else float("inf"), axis=1
    )
    ratios_valides = derniers_debits_ratio[
        (derniers_debits_ratio["ratio"] != float("inf")) & (derniers_debits_ratio["ratio"] >= 0)
    ]

    col_r1, col_r2 = st.columns(2, gap="large")
    with col_r1:
        fig_ratio = px.histogram(
            ratios_valides[ratios_valides["ratio"] <= 2],
            x="ratio",
            nbins=20,
            title="Distribution du ratio Crédit/Débit",
            labels={"ratio": "Ratio", "count": "Effectif"},
            color_discrete_sequence=["#10B981"],
        )
        fig_ratio.add_vline(
            x=1, line_dash="dash", line_color="#EF4444", annotation_text="Équilibre (1.0)"
        )
        fig_ratio = apply_plotly_theme(fig_ratio)
        st.plotly_chart(fig_ratio, width="stretch")

    with col_r2:
        nb_equilibre = len(ratios_valides[ratios_valides["ratio"] >= 1])
        nb_deficit = len(ratios_valides[ratios_valides["ratio"] < 1])
        ratio_moyen = ratios_valides["ratio"].mean() if not ratios_valides.empty else 0.0

        st.metric(
            "Comptes à jour (Crédit ≥ Débit)", nb_equilibre, delta="Normal", delta_color="normal"
        )
        st.metric(
            "Comptes en retard (Crédit < Débit)", nb_deficit, delta="Déficit", delta_color="inverse"
        )
        st.metric("Ratio moyen de couverture", f"{ratio_moyen:.2f}")


# ============================================================================
# ONGLET 2: DÉTECTION PRÉCOCE & RISQUES
# ============================================================================
with tab_risques:
    st.subheader("Surveillance des comptes proches du seuil de rupture")
    st.caption(
        "Identifiez les copropriétaires dont le solde approche dangereusement du seuil d'alerte."
    )

    derniers_debits_risk = derniers_debits_typed.merge(
        config_df[["type_apt", "threshold"]],
        on="type_apt",
        how="left",
    )
    default_threshold = config_df[config_df["type_apt"] == "default"]["threshold"].values
    def_val = default_threshold[0] if len(default_threshold) > 0 else 2000.0
    derniers_debits_risk["threshold"] = derniers_debits_risk["threshold"].fillna(def_val)
    derniers_debits_risk["pct_seuil"] = (
        derniers_debits_risk["debit"] / derniers_debits_risk["threshold"] * 100
    )

    pct_risque = st.slider(
        "Sensibilité de détection (% du seuil d'alerte déclenchant la vigilance) :",
        min_value=50,
        max_value=99,
        value=80,
        step=5,
        key="stats_avancees_pct_risque",
    )

    a_risque = derniers_debits_risk[
        (derniers_debits_risk["pct_seuil"] >= pct_risque)
        & (derniers_debits_risk["pct_seuil"] < 100)
    ].sort_values("pct_seuil", ascending=False)

    col_k1, col_k2 = st.columns(2, gap="medium")
    with col_k1:
        st.metric(
            "Comptes en zone de vigilance",
            len(a_risque),
            help="Entre le pourcentage sélectionné et 100% du seuil.",
        )
    with col_k2:
        total_risque = a_risque["debit"].sum() if not a_risque.empty else 0.0
        st.metric("Montant total à risque", f"{total_risque:,.2f} €".replace(",", " "))

    st.space("small")

    if not a_risque.empty:
        display_risk = a_risque[
            ["proprietaire", "type_apt", "debit", "threshold", "pct_seuil"]
        ].copy()
        display_risk["pct_seuil"] = display_risk["pct_seuil"].round(1)

        st.dataframe(
            appliquer_confidentialite(display_risk),
            width="stretch",
            hide_index=True,
            column_config={
                "proprietaire": st.column_config.TextColumn("Copropriétaire", width="large"),
                "type_apt": st.column_config.TextColumn("Type", width="small"),
                "debit": st.column_config.NumberColumn("Débit actuel (€)", format="%.2f €"),
                "threshold": st.column_config.NumberColumn("Seuil d'alerte (€)", format="%.2f €"),
                "pct_seuil": st.column_config.ProgressColumn(
                    "% d'atteinte du seuil", format="%.1f %%", min_value=0, max_value=100
                ),
            },
        )
    else:
        st.success(f"✅ Aucun compte ne dépasse actuellement {pct_risque}% de son seuil d'alerte.")


# ============================================================================
# ONGLET 3: RÉCIDIVES & DURÉE DES ALERTES
# ============================================================================
with tab_recidive:
    st.subheader("Analyse de la persistance et récidive des impayés")

    if alertes_df.empty:
        st.info("Aucune alerte active pour calculer les statistiques de récidive.")
    else:
        nb_recidivistes = len(alertes_df[alertes_df["occurence"] > 1])
        nb_total_alertes = len(alertes_df)
        taux_recidive = (nb_recidivistes / nb_total_alertes * 100) if nb_total_alertes > 0 else 0
        duree_moyenne = (
            alertes_df["duree_jours"].mean() if "duree_jours" in alertes_df.columns else 0
        )
        occ_moyenne = alertes_df["occurence"].mean()

        col_m1, col_m2, col_m3 = st.columns(3, gap="medium")
        with col_m1:
            st.metric(
                "Taux de récidive",
                f"{taux_recidive:.1f} %",
                help="Copropriétaires en alerte sur plusieurs relevés.",
            )
        with col_m2:
            st.metric("Durée moyenne en alerte", f"{duree_moyenne:.0f} jours")
        with col_m3:
            st.metric("Nombre moyen d'occurrences", f"{occ_moyenne:.1f}")

        st.divider()

        col_top1, col_top2 = st.columns(2, gap="large")
        with col_top1:
            st.markdown("#### Répartition des alertes par type de lot")
            repartition = alertes_df.groupby("type_alerte").size().reset_index(name="count")
            fig_p = px.pie(
                repartition,
                values="count",
                names="type_alerte",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_p = apply_plotly_theme(fig_p)
            st.plotly_chart(fig_p, width="stretch")

        with col_top2:
            st.markdown("#### Top des comptes les plus récurrents")
            top_rec = alertes_df.nlargest(10, "occurence")[
                ["proprietaire", "type_alerte", "debit", "occurence", "duree_jours"]
            ].copy()
            st.dataframe(
                appliquer_confidentialite(top_rec),
                width="stretch",
                hide_index=True,
                column_config={
                    "proprietaire": st.column_config.TextColumn("Copropriétaire"),
                    "type_alerte": st.column_config.TextColumn("Type"),
                    "debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €"),
                    "occurence": st.column_config.NumberColumn("Occurrences"),
                    "duree_jours": st.column_config.NumberColumn("Durée (j)"),
                },
            )


# ============================================================================
# ONGLET 4: TYPOLOGIE & SAISONNALITÉ
# ============================================================================
with tab_saison:
    st.subheader("Analyse comparative par lot & Profil saisonnier")

    col_t1, col_t2 = st.columns(2, gap="large")

    with col_t1:
        st.markdown("#### Charges moyennes réelles vs Seuils de configuration")
        stats_par_type = (
            derniers_debits_typed.groupby("type_apt")
            .agg(moyenne_debit=("debit", "mean"), mediane_debit=("debit", "median"))
            .reset_index()
            .merge(
                config_df[["type_apt", "threshold", "charge_moyenne"]].rename(
                    columns={"charge_moyenne": "charge_ref"}
                ),
                on="type_apt",
                how="left",
            )
        )

        fig_bar = go.Figure()
        fig_bar.add_trace(
            go.Bar(
                name="Moyenne réelle",
                x=stats_par_type["type_apt"],
                y=stats_par_type["moyenne_debit"],
                marker_color="#0284C7",
            )
        )
        fig_bar.add_trace(
            go.Bar(
                name="Charge de référence",
                x=stats_par_type["type_apt"],
                y=stats_par_type["charge_ref"],
                marker_color="#F59E0B",
            )
        )
        fig_bar.add_trace(
            go.Scatter(
                name="Seuil d'alerte",
                x=stats_par_type["type_apt"],
                y=stats_par_type["threshold"],
                mode="markers+lines",
                marker=dict(size=9, color="#EF4444", symbol="diamond"),
                line=dict(dash="dash", color="#EF4444"),
            )
        )
        fig_bar.update_layout(
            title="Moyenne constatée vs Seuils d'alerte (€)",
            barmode="group",
            xaxis_title="Type de lot",
            yaxis_title="Montant (€)",
        )
        fig_bar = apply_plotly_theme(fig_bar)
        st.plotly_chart(fig_bar, width="stretch")

    with col_t2:
        st.markdown("#### Profil saisonnier moyen des débits")
        mois_noms = {
            1: "Janvier",
            2: "Février",
            3: "Mars",
            4: "Avril",
            5: "Mai",
            6: "Juin",
            7: "Juillet",
            8: "Août",
            9: "Septembre",
            10: "Octobre",
            11: "Novembre",
            12: "Décembre",
        }
        saisonnalite = charges_df.groupby("mois").agg(debit_moyen=("debit", "mean")).reset_index()
        saisonnalite["mois_nom"] = saisonnalite["mois"].map(mois_noms)

        fig_saison = px.bar(
            saisonnalite,
            x="mois_nom",
            y="debit_moyen",
            title="Débit moyen par mois (€)",
            labels={"mois_nom": "Mois", "debit_moyen": "Moyenne (€)"},
            color="debit_moyen",
            color_continuous_scale="Blues",
        )
        fig_saison.update_layout(coloraxis_showscale=False)
        fig_saison = apply_plotly_theme(fig_saison)
        st.plotly_chart(fig_saison, width="stretch")


# ============================================================================
# ONGLET 6: PRÉVISION DU DÉBIT GLOBAL
# ============================================================================
with tab_prevision:
    import numpy as np

    st.subheader("🔮 Prévision de l'évolution des créances")
    st.caption(
        "Projection basée sur une régression linéaire du débit global historique. "
        "Indicatif uniquement — la tendance réelle dépend des recouvrements futurs."
    )

    # Agréger le débit global par date
    debit_global = (
        charges_df.groupby("date")["debit"]
        .sum()
        .reset_index()
        .rename(columns={"debit": "debit_global"})
        .sort_values("date")
    )

    if len(debit_global) < 3:
        st.warning("⚠️ Pas assez de données historiques pour établir une prévision (minimum 3 relevés).")
    else:
        # Paramètre de prévision
        col_p1, col_p2, _ = st.columns([1, 1, 2])
        with col_p1:
            horizon_mois = st.selectbox(
                "Horizon de prévision",
                options=[3, 6, 12],
                index=1,
                key="prevision_horizon",
                format_func=lambda x: f"{x} mois",
            )
        with col_p2:
            methode = st.radio(
                "Méthode",
                options=["Tendance linéaire", "Moyenne mobile"],
                horizontal=True,
                key="prevision_methode",
            )

        # Conversion dates en numérique (jours depuis premier relevé)
        date_origine = debit_global["date"].min()
        debit_global["jours"] = (debit_global["date"] - date_origine).dt.days
        x = debit_global["jours"].values
        y = debit_global["debit_global"].values

        # Générer les dates futures (approximation : 30j par mois)
        dernier_jour = int(x[-1])
        futures_jours = np.array([
            dernier_jour + (i + 1) * 30 for i in range(horizon_mois)
        ])
        futures_dates = [
            date_origine + pd.Timedelta(days=int(j)) for j in futures_jours
        ]

        if methode == "Tendance linéaire":
            # Régression linéaire (degré 1)
            coeffs = np.polyfit(x, y, 1)
            poly = np.poly1d(coeffs)
            y_trend = poly(x)
            y_future = poly(futures_jours)
            tendance_label = (
                f"Tendance : {coeffs[0]:+.1f} €/jour "
                f"({'hausse' if coeffs[0] > 0 else 'baisse'})"
            )
        else:
            # Moyenne mobile sur les 3 derniers relevés → projection plate
            y_future = np.full(horizon_mois, float(np.mean(y[-3:])))
            y_trend = np.full(len(x), float(np.mean(y)))
            tendance_label = f"Moyenne des 3 derniers relevés : {float(np.mean(y[-3:])):,.0f} €".replace(",", " ")

        # KPIs de prévision
        val_actuelle = float(y[-1])
        val_prevue = float(y_future[-1])
        variation_prevue = val_prevue - val_actuelle
        signe = "+" if variation_prevue >= 0 else ""

        kpv1, kpv2, kpv3 = st.columns(3)
        kpv1.metric(
            "Débit global actuel",
            f"{val_actuelle:,.0f} €".replace(",", " "),
        )
        kpv2.metric(
            f"Prévision dans {horizon_mois} mois",
            f"{val_prevue:,.0f} €".replace(",", " "),
            delta=f"{signe}{variation_prevue:,.0f} €".replace(",", " "),
            delta_color="inverse",
        )
        kpv3.metric(
            "Tendance",
            "📈 Hausse" if variation_prevue > 0 else "📉 Baisse" if variation_prevue < 0 else "➡️ Stable",
            delta=tendance_label,
            delta_color="off",
        )

        # Graphique combiné historique + prévision
        fig_prev = go.Figure()

        # Courbe historique
        fig_prev.add_trace(go.Scatter(
            x=debit_global["date"],
            y=debit_global["debit_global"],
            mode="lines+markers",
            name="Débit réel",
            line=dict(color="#0284C7", width=2),
            marker=dict(size=6),
        ))

        # Courbe de tendance (sur historique)
        if methode == "Tendance linéaire":
            fig_prev.add_trace(go.Scatter(
                x=debit_global["date"],
                y=y_trend,
                mode="lines",
                name="Tendance",
                line=dict(color="#94a3b8", width=1, dash="dot"),
            ))

        # Zone de prévision (futur)
        fig_prev.add_trace(go.Scatter(
            x=futures_dates,
            y=y_future,
            mode="lines+markers",
            name=f"Prévision ({horizon_mois} mois)",
            line=dict(color="#f97316", width=2, dash="dash"),
            marker=dict(size=7, symbol="diamond"),
        ))

        # Ligne verticale séparant historique et prévision
        fig_prev.add_vline(
            x=debit_global["date"].max(),
            line_dash="dash",
            line_color="#64748b",
            annotation_text="Aujourd'hui",
            annotation_position="top left",
        )

        fig_prev.update_layout(
            xaxis_title="Date",
            yaxis_title="Débit global (€)",
            legend=dict(orientation="h", y=-0.2),
            margin=dict(t=20, b=20),
        )
        fig_prev = apply_plotly_theme(fig_prev)
        st.plotly_chart(fig_prev, width="stretch")

        st.caption(
            "⚠️ **Avertissement** : Cette prévision est purement mathématique (extrapolation de la tendance passée). "
            "Elle ne prend pas en compte les événements futurs (nouvelles relances, règlements, incidents). "
            "À utiliser comme indicateur de tendance, non comme certitude."
        )

