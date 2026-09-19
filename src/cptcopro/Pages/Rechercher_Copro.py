"""Page de recherche et Fiche 360° détaillée par copropriétaire."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import fetch_dataframe, normalize_date_columns
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
    preparer_df_pour_graphe,
)
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


@st.cache_data(ttl=300, show_spinner=False)
def load_all_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Charge les données des charges, copropriétaires et seuils d'alerte."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, "
            "num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires"
        )
        charges_df = fetch_dataframe(cur)
        cur.execute(
            "SELECT code_proprietaire AS code, debit, type_alerte, first_detection, "
            "last_detection, occurence FROM alertes_debit_eleve"
        )
        alertes_df = fetch_dataframe(cur)
        cur.execute("SELECT type_apt, threshold FROM config_alerte")
        config_df = fetch_dataframe(cur)

    charges_df = normalize_date_columns(charges_df, ["date"])
    charges_df = charges_df.dropna(subset=["date"]).sort_values("date")
    alertes_df = normalize_date_columns(alertes_df, ["first_detection", "last_detection"])
    return charges_df, alertes_df, config_df


render_header(
    "🔍 Fiche Copropriétaire & Analyse 360°",
    "Consultez l'historique complet, la situation financière et le statut d'alerte d'un copropriétaire",
)

charges_df, alertes_df, config_df = load_all_data()


if charges_df.empty:
    st.warning("⚠️ Aucune donnée disponible.")
    st.stop()

# Liste unique des copropriétaires et métadonnées associées
proprietaires_uniques = sorted(charges_df["proprietaire"].unique())
thresholds_by_type = dict(zip(config_df["type_apt"], config_df["threshold"], strict=False))

# Table de correspondance métadonnées par propriétaire
copro_meta_df = (
    charges_df[["proprietaire", "code", "num_apt", "type_apt"]]
    .drop_duplicates(subset=["proprietaire"])
    .set_index("proprietaire")
)


def filter_coproprietaires(query: str, all_owners: list[str]) -> list[str]:
    """Filtre la liste des copropriétaires par nom, code, numéro de lot ou type."""
    if not query:
        return all_owners
    q = query.lower().strip()
    matched = []
    for p in all_owners:
        if q in p.lower():
            matched.append(p)
            continue
        if p in copro_meta_df.index:
            row = copro_meta_df.loc[p]
            code = str(row.get("code") or "").lower()
            num_apt = str(row.get("num_apt") or "").lower()
            type_apt = str(row.get("type_apt") or "").lower()

            # Normalisation du lot (ex: "01" -> "1")
            num_apt_clean = num_apt.lstrip("0") if num_apt != "0" else "0"
            q_clean = q.lstrip("0") if q != "0" else "0"

            if (
                q in code
                or q == num_apt
                or q_clean == num_apt_clean
                or q in f"lot {num_apt}"
                or q in f"lot {num_apt_clean}"
                or q in f"apt {num_apt}"
                or q in type_apt
            ):
                matched.append(p)
    return matched


# Onglets principaux : Fiche Individuelle vs Comparateur Multi-copropriétaires
tab_fiche, tab_compare = st.tabs(
    [
        "👤 Fiche Individuelle 360°",
        "📊 Comparateur Multi-Copropriétaires",
    ]
)

# ============================================================================
# ONGLET 1: FICHE INDIVIDUELLE 360°
# ============================================================================
with tab_fiche:
    col_s1, col_s2 = st.columns([1.2, 2], gap="medium")

    with col_s1:
        search_filter = st.text_input(
            "🔍 Filtrer par nom, code ou n° de lot :",
            placeholder="Ex: Dupont, D001, 12, T3...",
            key="fiche_search_box",
        ).strip()

    matching_proprietaires = filter_coproprietaires(search_filter, proprietaires_uniques)

    with col_s2:
        if not matching_proprietaires:
            st.warning(f"Aucun copropriétaire trouvé pour la recherche : '{search_filter}'")
            selected_copro = None
        else:
            label_select = f"Sélectionnez le copropriétaire ({len(matching_proprietaires)} résultat{'s' if len(matching_proprietaires) > 1 else ''}) :"
            selected_copro = st.selectbox(
                label_select,
                options=matching_proprietaires,
                index=0,
                format_func=lambda p: (
                    f"{p}  (Code: {copro_meta_df.loc[p, 'code']} | Lot: {copro_meta_df.loc[p, 'num_apt']} - {str(copro_meta_df.loc[p, 'type_apt']).upper()})"
                    if p in copro_meta_df.index
                    else p
                ),
                key=f"fiche_copro_select_{search_filter}",
            )

    if not selected_copro:
        st.info("Veuillez affiner ou effacer votre recherche pour sélectionner un compte.")
    else:
        # Données du copropriétaire sélectionné
        df_copro = charges_df[charges_df["proprietaire"] == selected_copro].sort_values("date")

        if df_copro.empty:
            st.info("Aucune donnée pour ce copropriétaire.")
        else:
            dernier_releve = df_copro.iloc[-1]
            code_copro = dernier_releve["code"]
            type_lot = dernier_releve["type_apt"] or "NA"
            num_lot = dernier_releve["num_apt"] or "NA"
            debit_actuel = float(dernier_releve["debit"])
            credit_actuel = float(dernier_releve["credit"])
            date_releve = dernier_releve["date"].strftime("%d/%m/%Y")

            # Vérifier si en alerte
            if not alertes_df.empty and "code" in alertes_df.columns:
                alerte_info = alertes_df[alertes_df["code"] == code_copro]
            else:
                alerte_info = pd.DataFrame()
            is_in_alert = not alerte_info.empty
            seuil_lot = thresholds_by_type.get(
                str(type_lot).lower(), thresholds_by_type.get("default", 2000.0)
            )

            st.divider()

            # --- Bandeau d'identité & Situation ---
            st.markdown(f"### Situation au {date_releve} : **{selected_copro}**")

            col_c1, col_c2, col_c3, col_c4 = st.columns(4, gap="medium")
            with col_c1:
                st.metric("Code Copropriétaire", code_copro)
            with col_c2:
                st.metric(
                    "Lot & Typologie", f"Lot {num_lot} ({type_lot.upper() if type_lot else 'N/A'})"
                )
            with col_c3:
                st.metric(
                    "Débit Actuel",
                    f"{debit_actuel:,.2f} €".replace(",", " "),
                    delta=f"Seuil : {seuil_lot:,.0f} €",
                    delta_color="off",
                )
            with col_c4:
                if is_in_alert:
                    occ = alerte_info.iloc[0]["occurence"]
                    st.metric(
                        "Statut Alerte",
                        f"⚠️ En Alerte ({occ}x)",
                        delta="Débit élevé",
                        delta_color="inverse",
                    )
                else:
                    st.metric(
                        "Statut Alerte", "✅ Normal", delta="Sous le seuil", delta_color="normal"
                    )

            st.space("small")

            # --- Graphique temporel individuel ---
            fig_indiv = go.Figure()

            # Courbe du débit
            fig_indiv.add_trace(
                go.Scatter(
                    x=df_copro["date"],
                    y=df_copro["debit"],
                    mode="lines+markers",
                    name="Débit (€)",
                    line=dict(color="#38BDF8", width=3),
                    marker=dict(size=8, color="#0284C7"),
                )
            )

            # Ligne de seuil d'alerte
            fig_indiv.add_hline(
                y=seuil_lot,
                line_dash="dash",
                line_color="#EF4444",
                annotation_text=f"Seuil Alerte {type_lot.upper()} ({seuil_lot:.0f} €)",
                annotation_position="top right",
            )

            fig_indiv.update_layout(
                title=f"Évolution temporelle du débit — {selected_copro}",
                xaxis_title="Date de relevé",
                yaxis_title="Montant (€)",
            )
            fig_indiv = apply_plotly_theme(fig_indiv)
            st.plotly_chart(fig_indiv, width="stretch")

            # --- Historique des relevés ---
            with st.expander(
                f"📋 Historique complet des relevés pour {selected_copro} ({len(df_copro)} relevés)",
                expanded=False,
            ):
                df_display = df_copro.sort_values("date", ascending=False).copy()
                df_display["date_str"] = pd.to_datetime(df_display["date"]).dt.strftime("%d/%m/%Y")
                st.dataframe(
                    appliquer_confidentialite(df_display),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "date_str": st.column_config.TextColumn("Date relevé", width="medium"),
                        "proprietaire": st.column_config.TextColumn(
                            "Copropriétaire", width="large"
                        ),
                        "code": st.column_config.TextColumn("Code", width="small"),
                        "num_apt": st.column_config.TextColumn("Lot", width="small"),
                        "type_apt": st.column_config.TextColumn("Type", width="small"),
                        "debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €"),
                        "credit": st.column_config.NumberColumn("Crédit (€)", format="%.2f €"),
                    },
                )


# ============================================================================
# ONGLET 2: COMPARATEUR MULTI-COPROPRIÉTAIRES
# ============================================================================
with tab_compare:
    st.subheader("Comparaison simultanée de plusieurs copropriétaires")
    st.caption("Sélectionnez plusieurs comptes pour analyser l'évolution croisée de leurs charges.")

    selected_multiple = st.multiselect(
        "Choisissez les copropriétaires à superposer :",
        options=proprietaires_uniques,
        default=proprietaires_uniques[:3]
        if len(proprietaires_uniques) >= 3
        else proprietaires_uniques,
        key="compare_copros_multiselect",
    )

    if not selected_multiple:
        st.info("Veuillez sélectionner au moins un copropriétaire pour afficher le comparatif.")
    else:
        df_multi = charges_df[charges_df["proprietaire"].isin(selected_multiple)].sort_values(
            ["proprietaire", "date"]
        )

        fig_multi = px.line(
            preparer_df_pour_graphe(df_multi, "proprietaire"),
            x="date",
            y="debit",
            color="proprietaire",
            title="Comparatif des débits (€)",
            markers=True,
        )
        fig_multi = apply_plotly_theme(fig_multi)
        fig_multi.update_layout(
            height=520,
            xaxis_title="Date",
            yaxis_title="Débit (€)",
            margin=dict(l=20, r=20, t=50, b=90),
            title=dict(
                text="Comparatif des débits (€)",
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
        st.plotly_chart(fig_multi, width="stretch")

        with st.expander("📋 Tableau des données comparées", expanded=False):
            st.dataframe(
                appliquer_confidentialite(
                    df_multi.sort_values(by=["date", "proprietaire"], ascending=[False, True])
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
