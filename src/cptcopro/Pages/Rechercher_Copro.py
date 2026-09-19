"""Page Espace Copropriétaires : Annuaire des lots et Fiche 360° individuelle."""

from __future__ import annotations

import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from cptcopro.Database import get_copro_notes, save_copro_notes
except ImportError:
    import importlib
    import sys

    if "cptcopro.Database.Relance_Config" in sys.modules:
        importlib.reload(sys.modules["cptcopro.Database.Relance_Config"])
    if "cptcopro.Database" in sys.modules:
        importlib.reload(sys.modules["cptcopro.Database"])

    from cptcopro.Database.Relance_Config import get_copro_notes, save_copro_notes
from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import fetch_dataframe, normalize_date_columns
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
)
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


@st.cache_data(ttl=300, show_spinner=False)
def load_all_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Charge les données des charges, alertes et seuils."""
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


@st.cache_data(ttl=300, show_spinner=False)
def load_coproprietaires() -> pd.DataFrame:
    """Charge la liste complète des copropriétaires depuis MariaDB."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, "
            "type_apt AS Type, num_apt AS Numero, last_check AS Date FROM coproprietaires "
            "ORDER BY nom_proprietaire ASC"
        )
        df = fetch_dataframe(cur)
    return normalize_date_columns(df, ["Date"])


render_header(
    "👥 Espace Copropriétaires",
    "Répertoire complet des lots, annuaire des résidents et fiches individuelles 360°",
)

charges_df, alertes_df, config_df = load_all_data()
df_copros = load_coproprietaires()

if charges_df.empty and df_copros.empty:
    st.warning("⚠️ Aucune donnée disponible.")
    st.stop()

# Liste unique des copropriétaires et métadonnées associées
proprietaires_uniques = sorted(charges_df["proprietaire"].unique()) if not charges_df.empty else []
thresholds_by_type = (
    dict(zip(config_df["type_apt"], config_df["threshold"], strict=False))
    if not config_df.empty
    else {}
)

# Table de correspondance métadonnées par propriétaire
copro_meta_df = (
    charges_df[["proprietaire", "code", "num_apt", "type_apt"]]
    .drop_duplicates(subset=["proprietaire"])
    .set_index("proprietaire")
    if not charges_df.empty
    else pd.DataFrame()
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


tab_annuaire, tab_fiche = st.tabs(
    [
        "📋 Annuaire des Lots & Résidents",
        "👤 Fiche Individuelle 360° & Notes",
    ]
)

# ============================================================================
# ONGLET 1: ANNUAIRE DES LOTS & COPROPRIÉTAIRES (Ex-Liste_Copro)
# ============================================================================
with tab_annuaire:
    if df_copros.empty:
        st.info("ℹ️ Aucun copropriétaire répertorié dans la base.")
    else:
        total_copros = len(df_copros)
        repartition_types = df_copros["Type"].value_counts().to_dict()

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

        col_f1, col_f2 = st.columns([2, 1], gap="medium")
        with col_f1:
            search_annuaire = st.text_input(
                "🔍 Recherche rapide dans l'annuaire",
                placeholder="Filtrer par nom, code ou n° de lot...",
                key="annuaire_quick_search",
            ).strip()
        with col_f2:
            types_dispo = ["Tous", *sorted(t for t in df_copros["Type"].dropna().unique() if t)]
            filtre_type = st.selectbox(
                "Type de lot",
                options=types_dispo,
                index=0,
                key="annuaire_type_sel",
            )

        df_filtre_annuaire = df_copros.copy()
        if search_annuaire:
            df_filtre_annuaire = df_filtre_annuaire[
                df_filtre_annuaire["Proprietaire"].str.contains(
                    search_annuaire, case=False, na=False
                )
                | df_filtre_annuaire["Code"].str.contains(search_annuaire, case=False, na=False)
                | df_filtre_annuaire["Numero"]
                .astype(str)
                .str.contains(search_annuaire, case=False, na=False)
            ]
        if filtre_type != "Tous":
            df_filtre_annuaire = df_filtre_annuaire[df_filtre_annuaire["Type"] == filtre_type]

        st.markdown(f"**{len(df_filtre_annuaire)} copropriétaire(s) affiché(s)**")

        display_annuaire = appliquer_confidentialite(df_filtre_annuaire)
        st.dataframe(
            display_annuaire,
            width="stretch",
            hide_index=True,
            column_config={
                "Proprietaire": st.column_config.TextColumn(
                    "Nom du copropriétaire", width="large"
                ),
                "Code": st.column_config.TextColumn("Code", width="small"),
                "Type": st.column_config.TextColumn("Type Lot", width="small"),
                "Numero": st.column_config.TextColumn("Numéro Lot / Apt", width="small"),
                "Date": st.column_config.DateColumn(
                    "Dernière vérification", format="DD/MM/YYYY", width="medium"
                ),
            },
        )

        # Export CSV
        col_csv, _ = st.columns([1, 3])
        with col_csv:
            csv_buf = io.StringIO()
            display_annuaire.to_csv(csv_buf, index=False, sep=";")
            st.download_button(
                "📥 Exporter l'annuaire (CSV)",
                data=csv_buf.getvalue().encode("utf-8-sig"),
                file_name="annuaire_coproprietaires.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ============================================================================
# ONGLET 2: FICHE INDIVIDUELLE 360° & BLOC-NOTES
# ============================================================================
with tab_fiche:
    col_s1, col_s2 = st.columns([1.2, 2], gap="medium")

    # Pré-sélection depuis un autre onglet ou page
    default_search = st.session_state.get("target_fiche_copro", "")

    with col_s1:
        search_filter = st.text_input(
            "🔍 Rechercher un copropriétaire :",
            value=default_search,
            placeholder="Ex: Dupont, D001, 12, T3...",
            key="fiche_search_box",
        ).strip()

    matching_proprietaires = filter_coproprietaires(search_filter, proprietaires_uniques)

    with col_s2:
        if not matching_proprietaires:
            st.warning(f"Aucun compte trouvé pour : '{search_filter}'")
            selected_copro = None
        else:
            label_select = (
                f"Sélectionnez le copropriétaire ({len(matching_proprietaires)} résultat"
                f"{'s' if len(matching_proprietaires) > 1 else ''}) :"
            )
            selected_copro = st.selectbox(
                label_select,
                options=matching_proprietaires,
                index=0,
                format_func=lambda p: (
                    f"{p}  (Code: {copro_meta_df.loc[p, 'code']} | Lot: "
                    f"{copro_meta_df.loc[p, 'num_apt']} - "
                    f"{str(copro_meta_df.loc[p, 'type_apt']).upper()})"
                    if p in copro_meta_df.index
                    else p
                ),
                key=f"fiche_copro_select_{search_filter}",
            )

    if not selected_copro:
        st.info("Veuillez sélectionner un compte pour afficher sa fiche 360°.")
    else:
        df_copro = charges_df[charges_df["proprietaire"] == selected_copro].sort_values("date")

        if df_copro.empty:
            st.info("Aucun historique financier pour ce copropriétaire.")
        else:
            dernier_releve = df_copro.iloc[-1]
            code_copro = str(dernier_releve["code"])
            type_lot = dernier_releve["type_apt"] or "NA"
            num_lot = dernier_releve["num_apt"] or "NA"
            debit_actuel = float(dernier_releve["debit"])
            date_releve = dernier_releve["date"].strftime("%d/%m/%Y")

            if not alertes_df.empty and "code" in alertes_df.columns:
                alerte_info = alertes_df[alertes_df["code"] == code_copro]
            else:
                alerte_info = pd.DataFrame()
            is_in_alert = not alerte_info.empty
            seuil_lot = thresholds_by_type.get(
                str(type_lot).lower(), thresholds_by_type.get("default", 2000.0)
            )

            st.divider()

            # --- Bandeau d'identité & Situation financière ---
            col_id, col_actions = st.columns([2.5, 1.2], gap="large")
            with col_id:
                st.markdown(f"### Situation au {date_releve} : **{selected_copro}**")
            with col_actions:
                # Passerelle 1-clic vers le module de relances
                if st.button(
                    "✉️ Préparer une relance",
                    type="primary",
                    help="Bascule vers le module de relance avec ce copropriétaire pré-sélectionné",
                    use_container_width=True,
                ):
                    st.session_state["target_relance_copro"] = code_copro
                    st.switch_page("Pages/Relance.py")

            col_c1, col_c2, col_c3, col_c4 = st.columns(4, gap="medium")
            with col_c1:
                st.metric("Code Copropriétaire", code_copro)
            with col_c2:
                st.metric(
                    "Lot & Typologie",
                    f"Lot {num_lot} ({type_lot.upper() if type_lot else 'N/A'})",
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
                        "Statut Alerte",
                        "✅ Normal",
                        delta="Sous le seuil",
                        delta_color="normal",
                    )

            # --- Bloc-notes interne & Suivi des promesses de paiement ---
            with st.expander(
                "📝 Bloc-notes interne & Promesses de paiement (Gestionnaire)",
                expanded=False,
            ):
                current_notes = get_copro_notes(code_copro)
                with st.form(f"notes_form_{code_copro}"):
                    notes_input = st.text_area(
                        "Notes internes (promesses de règlement, échanges téléphoniques, accords d'échéancier) :",
                        value=current_notes,
                        height=100,
                        placeholder="Ex: Promesse de virement de 450 € prévue le 28 du mois...",
                    )
                    submitted_notes = st.form_submit_button(
                        "💾 Enregistrer les notes", use_container_width=False
                    )
                    if submitted_notes:
                        save_copro_notes(code_copro, notes_input)
                        st.toast("Notes internes enregistrées avec succès !", icon="💾")
                        st.rerun()

            # --- Graphique temporel individuel ---
            fig_indiv = go.Figure()

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

            # --- Historique complet des relevés ---
            with st.expander(
                f"📋 Historique des relevés pour {selected_copro} ({len(df_copro)} relevés)",
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
