"""Page Centre d'Alertes : Surveillance en temps réel, répartition, historique et configuration."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from cptcopro.Database import (
    DEFAULT_THRESHOLD_FALLBACK,
    get_config_alertes,
    update_config_alerte,
)
from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import normalize_date_columns
from cptcopro.utils.privacy import (
    appliquer_confidentialite,
    preparer_df_pour_graphe,
)
from cptcopro.utils.ui_components import apply_plotly_theme, render_header


@st.cache_data(ttl=300, show_spinner=False)
def recup_alertes() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Récupère les alertes actives et le total des débits en alerte."""
    query = (
        "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, "
        "debit AS Debit, type_alerte AS TypeApt, first_detection AS FirstDetection, "
        "last_detection AS LastDetection, occurence AS Occurence "
        "FROM alertes_debit_eleve ORDER BY debit DESC"
    )
    query2 = "SELECT SUM(debit) AS TotalDebit FROM alertes_debit_eleve"
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            recup_alerte = pd.DataFrame(cur.fetchall())
            cur.execute(query2)
            recup_total_debit = pd.DataFrame(cur.fetchall())
        recup_alerte = normalize_date_columns(recup_alerte, ["FirstDetection", "LastDetection"])
        return recup_alerte, recup_total_debit
    except Exception as e:
        st.error(f"Erreur lors de la récupération des alertes : {e}")
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def recup_debits_proprietaires_alertes() -> pd.DataFrame:
    """Récupère l'historique des débits pour les propriétaires actuellement en alerte."""
    query = (
        "SELECT c.code_proprietaire AS Code, c.nom_proprietaire AS Proprietaire, c.date, c.debit "
        "FROM vw_charge_coproprietaires c "
        "INNER JOIN alertes_debit_eleve a ON a.code_proprietaire = c.code_proprietaire "
        "ORDER BY c.date ASC"
    )
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            df = pd.DataFrame(cur.fetchall())
        return normalize_date_columns(df, ["date"])
    except Exception as e:
        st.error(f"Impossible de récupérer l'historique des débits : {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def recup_suivi_alertes() -> pd.DataFrame:
    """Récupère le suivi agrégé des alertes par date de relevé."""
    query = """
        SELECT date_releve, nombre_alertes, total_debit,
               nb_2p, nb_3p, nb_4p, nb_5p, nb_na,
               debit_2p, debit_3p, debit_4p, debit_5p, debit_na
        FROM suivi_alertes
        ORDER BY date_releve DESC
    """
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            suivi_df = pd.DataFrame(cur.fetchall())
        return normalize_date_columns(suivi_df, ["date_releve"])
    except Exception as e:
        st.error(f"Erreur lors de la récupération du suivi des alertes : {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def load_config() -> pd.DataFrame:
    """Charge la configuration des seuils d'alerte."""
    try:
        config = get_config_alertes()
        if config:
            df = pd.DataFrame(config)
            df = df.rename(
                columns={
                    "type_apt": "Type Apt",
                    "charge_moyenne": "Charge Moyenne (€)",
                    "taux": "Taux",
                    "threshold": "Seuil Alerte (€)",
                    "last_update": "Dernière MAJ",
                }
            )
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur lors du chargement de la configuration : {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def load_derniere_relance_par_copro() -> dict[str, str]:
    """Retourne un dict {code_proprietaire: date_derniere_relance_str}."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT code_proprietaire, MAX(created_at) AS derniere_relance "
                "FROM relance_draft "
                "WHERE status NOT IN ('deleted') "
                "GROUP BY code_proprietaire"
            )
            rows = cur.fetchall()
        return {
            str(r["code_proprietaire"]): str(r["derniere_relance"])[:10]
            if r["derniere_relance"] else "—"
            for r in rows
            if r and r.get("code_proprietaire")
        }
    except Exception:
        return {}


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
    "🚨 Centre de Gestion des Alertes & Risques",
    "Surveillance en temps réel des impayés critiques, analyse des récidives et configuration des seuils",
)

alertes_df, sommealertes_df = recup_alertes()
suivi_alerte = recup_suivi_alertes()
debits_df = recup_debits_proprietaires_alertes()
config_df = load_config()
relance_dates = load_derniere_relance_par_copro()

tab_actives, tab_repartition, tab_evolution, tab_config = st.tabs(
    [
        "🚨 Alertes Actives & Actions",
        "📊 Répartition & Récidives",
        "📈 Évolution Temporelle",
        "⚙️ Configuration des Seuils",
    ]
)

# ============================================================================
# ONGLET 1: ALERTES ACTIVES & ACTIONS RAPIDES (1-CLIC RELANCE)
# ============================================================================
with tab_actives:
    raw_date_releve = suivi_alerte["date_releve"].iat[0] if not suivi_alerte.empty else None
    raw_date_precedent = suivi_alerte["date_releve"].iat[1] if len(suivi_alerte) >= 2 else None

    date_releve_str = (
        raw_date_releve.strftime("%d/%m/%Y")
        if hasattr(raw_date_releve, "strftime")
        else (str(raw_date_releve) if raw_date_releve is not None else "N/A")
    )
    date_precedent_str = (
        raw_date_precedent.strftime("%d/%m/%Y")
        if hasattr(raw_date_precedent, "strftime")
        else (str(raw_date_precedent) if raw_date_precedent is not None else None)
    )

    nombre_alerte = (
        int(suivi_alerte["nombre_alertes"].iat[0]) if not suivi_alerte.empty else len(alertes_df)
    )
    dernier_nombre = (
        int(suivi_alerte["nombre_alertes"].iat[1]) if len(suivi_alerte) >= 2 else nombre_alerte
    )
    delta_nombre = nombre_alerte - dernier_nombre

    total_debit_alerte = (
        float(suivi_alerte["total_debit"].iat[0])
        if not suivi_alerte.empty
        else (float(alertes_df["Debit"].sum()) if not alertes_df.empty else 0.0)
    )
    dernier_total = (
        float(suivi_alerte["total_debit"].iat[1]) if len(suivi_alerte) >= 2 else total_debit_alerte
    )
    delta_total = total_debit_alerte - dernier_total

    kpi1, kpi2, kpi3 = st.columns(3, gap="medium")
    with kpi1:
        st.metric(
            "Date du relevé",
            value=date_releve_str,
            delta=f"Précédent : {date_precedent_str}" if date_precedent_str else None,
            delta_color="off",
        )
    with kpi2:
        st.metric(
            "Copropriétaires en alerte",
            value=nombre_alerte,
            delta=f"{'+' if delta_nombre > 0 else ''}{delta_nombre}"
            if delta_nombre != 0
            else None,
            delta_color="inverse",
            help="Nombre de copropriétaires dont le solde débiteur excède le seuil de leur type d'appartement.",
        )
    with kpi3:
        st.metric(
            "Montant total des impayés critiques",
            value=f"{total_debit_alerte:,.2f} €".replace(",", " "),
            delta=f"{'+' if delta_total > 0 else ''}{delta_total:,.2f} €".replace(",", " ")
            if delta_total != 0
            else None,
            delta_color="inverse",
            help="Somme cumulée des débits de tous les copropriétaires en situation d'alerte.",
        )

    st.divider()

    if alertes_df.empty:
        st.success(
            "🎉 **Excellente nouvelle !** Aucun copropriétaire n'est actuellement en situation d'alerte de débit élevé."
        )
    else:
        # Passerelle 1-clic vers le module de relance
        col_act1, col_act2 = st.columns([2, 1.2], gap="large")
        with col_act1:
            st.subheader(f"📋 Détail des {len(alertes_df)} compte(s) en alerte active")
        with col_act2:
            alert_copros = {
                str(r["Code"]): f"{r['Proprietaire']} ({r['Code']} — {r['Debit']:,.2f} €)"
                for _, r in alertes_df.iterrows()
            }
            c_sel, c_btn, c_fiche = st.columns([2, 1, 1])
            with c_sel:
                selected_alert_code = st.selectbox(
                    "Action rapide :",
                    options=list(alert_copros.keys()),
                    format_func=lambda c: alert_copros[c],
                    key="quick_relance_select",
                    label_visibility="collapsed",
                )
            with c_btn:
                if st.button("✉️ Relancer", type="primary", width="stretch"):
                    st.session_state["target_relance_copro"] = selected_alert_code
                    st.switch_page("Pages/Relance.py")
            with c_fiche:
                if st.button("👤 Fiche copro", width="stretch",
                             help="Ouvre la fiche 360° de ce copropriétaire"):
                    st.session_state["target_fiche_copro"] = selected_alert_code
                    st.switch_page("Pages/Rechercher_Copro.py")

        alertes_work = alertes_df[
            [
                "Proprietaire",
                "Code",
                "Debit",
                "TypeApt",
                "Occurence",
                "FirstDetection",
                "LastDetection",
            ]
        ].copy()
        alertes_work["DerniereRelance"] = alertes_work["Code"].map(
            lambda c: relance_dates.get(str(c), "—")
        )
        alertes_affiche = appliquer_confidentialite(alertes_work)

        st.dataframe(
            alertes_affiche,
            width="stretch",
            hide_index=True,
            column_config={
                "Proprietaire": st.column_config.TextColumn("Copropriétaire", width="large"),
                "Code": st.column_config.TextColumn("Code", width="small"),
                "Debit": st.column_config.NumberColumn(
                    "Débit actuel (€)", format="%.2f €", width="medium"
                ),
                "TypeApt": st.column_config.TextColumn("Type Lot", width="small"),
                "Occurence": st.column_config.NumberColumn("Occurrences", width="small"),
                "FirstDetection": st.column_config.DateColumn(
                    "1ère détection", format="DD/MM/YYYY", width="small"
                ),
                "LastDetection": st.column_config.DateColumn(
                    "Dernière détection", format="DD/MM/YYYY", width="small"
                ),
                "DerniereRelance": st.column_config.TextColumn(
                    "✉️ Dernière relance", width="small",
                    help="Date de la dernière relance générée pour ce copropriétaire."
                ),
            },
        )


# ============================================================================
# ONGLET 2: RÉPARTITION PAR TYPOLOGIE & RÉCIDIVES (Ex-Stat_Alerte)
# ============================================================================
with tab_repartition:
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
        col_g1, col_g2 = st.columns(2, gap="large")

        with col_g1:
            fig_bar = px.bar(
                preparer_df_pour_graphe(alertes_df, "Proprietaire"),
                x="Proprietaire",
                y="Occurence",
                color="TypeApt",
                title="Nombre de relevés en situation d'alerte par propriétaire",
            )
            fig_bar = apply_plotly_theme(fig_bar)
            st.plotly_chart(fig_bar, width="stretch")

        with col_g2:
            if len(alertes_df["TypeApt"].unique()) > 1:
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
                    title="Part des alertes par typologie de lot",
                )
                fig_pie = apply_plotly_theme(fig_pie)
                st.plotly_chart(fig_pie, width="stretch")
    else:
        st.info("Aucune donnée d'alerte à ventiler.")


# ============================================================================
# ONGLET 3: ÉVOLUTION TEMPORELLE DES DÉBITS
# ============================================================================
with tab_evolution:
    if not debits_df.empty:
        st.subheader("📈 Évolution temporelle des comptes en alerte")
        try:
            agg = (
                debits_df.groupby(["date", "Proprietaire"])["debit"]
                .sum()
                .reset_index()
                .sort_values(["date", "Proprietaire"])
            )
            if not agg.empty:
                fig = px.line(
                    preparer_df_pour_graphe(agg, "Proprietaire"),
                    x="date",
                    y="debit",
                    color="Proprietaire",
                    title="Courbes des débits pour les copropriétaires en alerte (€)",
                    markers=True,
                )
                fig = apply_plotly_theme(fig)
                fig.update_layout(
                    height=520,
                    xaxis_title="Date de relevé",
                    yaxis_title="Débit (€)",
                    margin=dict(l=20, r=20, t=50, b=90),
                    title=dict(
                        text="Courbes des débits pour les copropriétaires en alerte (€)",
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
                st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"Impossible de générer le graphique : {e}")
    else:
        st.info("Aucun historique disponible pour les comptes en alerte.")


# ============================================================================
# ONGLET 4: CONFIGURATION DES SEUILS (Ex-Config_Alertes)
# ============================================================================
with tab_config:
    if config_df.empty:
        st.warning("⚠️ Aucune configuration trouvée dans la base de données.")
    else:
        display_df = config_df[config_df["Type Apt"] != "default"].copy()
        default_row = config_df[config_df["Type Apt"] == "default"]

        col_t1, col_t2 = st.columns([1.8, 1], gap="large")

        with col_t1:
            st.subheader("📊 Grille des seuils paramétrés")
            st.dataframe(
                display_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Type Apt": st.column_config.TextColumn("Type Lot", width="small"),
                    "Charge Moyenne (€)": st.column_config.NumberColumn(
                        "Charge Moyenne (€)", format="%.2f €", width="medium"
                    ),
                    "Taux": st.column_config.NumberColumn(
                        "Coefficient", format="%.2f", width="small"
                    ),
                    "Seuil Alerte (€)": st.column_config.NumberColumn(
                        "Seuil d'Alerte (€)", format="%.2f €", width="medium"
                    ),
                    "Dernière MAJ": st.column_config.DateColumn(
                        "Dernière MAJ", format="DD/MM/YYYY", width="medium"
                    ),
                },
            )

            if not default_row.empty:
                seuil_def = default_row["Seuil Alerte (€)"].values[0]
                st.info(f"🔄 **Seuil par défaut** (pour lots non classés) : **{seuil_def:.2f} €**")

        with col_t2:
            st.subheader("📐 Formule de calcul")
            st.markdown(r"""
            Une alerte est déclenchée pour un copropriétaire si son débit dépasse le seuil défini :

            $$\text{Seuil} = \text{Charge Moyenne} \times \text{Taux}$$

            - **Taux 1.33** = Alerte dès 33% au-dessus de la moyenne
            - **Taux 1.50** = Alerte dès 50% au-dessus de la moyenne
            """)

        st.divider()

        st.subheader("✏️ Modifier les seuils d'une typologie")

        types_disponibles = display_df["Type Apt"].tolist()
        if "default" not in types_disponibles:
            types_disponibles.append("default")

        col_sel_type, _ = st.columns([1.5, 2])
        with col_sel_type:
            type_selectionne = st.selectbox(
                "Sélectionnez la typologie de lot à ajuster :",
                options=types_disponibles,
                format_func=lambda x: (
                    f"Type {x.upper()}" if x != "default" else "Valeur par défaut (Générique)"
                ),
                key="config_alertes_type_selectionne",
            )

        if type_selectionne == "default":
            current_row = default_row
        else:
            current_row = display_df[display_df["Type Apt"] == type_selectionne]

        if not current_row.empty:
            current_charge = float(current_row["Charge Moyenne (€)"].values[0])
            current_taux = float(current_row["Taux"].values[0])
            current_threshold = float(current_row["Seuil Alerte (€)"].values[0])
        else:
            current_charge = DEFAULT_THRESHOLD_FALLBACK
            current_taux = 1.33
            current_threshold = DEFAULT_THRESHOLD_FALLBACK

        with st.form("form_modifier_seuil_integre"):
            col_a, col_b, col_c = st.columns(3, gap="medium")

            with col_a:
                new_charge = st.number_input(
                    "Charge Moyenne (€)",
                    min_value=0.0,
                    max_value=10000.0,
                    value=current_charge,
                    step=50.0,
                    help="Montant trimestriel moyen typique pour ce type de logement.",
                    key="config_alertes_charge_moyenne",
                )

            with col_b:
                new_taux = st.number_input(
                    "Coefficient multiplicateur",
                    min_value=1.0,
                    max_value=3.0,
                    value=current_taux,
                    step=0.05,
                    help="Multiplicateur d'alerte (ex: 1.33 = +33%).",
                    key="config_alertes_taux",
                )

            with col_c:
                calculated_threshold = new_charge * new_taux
                new_threshold = st.number_input(
                    "Seuil d'Alerte résultant (€)",
                    min_value=0.0,
                    max_value=20000.0,
                    value=calculated_threshold,
                    step=50.0,
                    help="Seuil absolu au-delà duquel l'alerte est active.",
                    key="config_alertes_threshold",
                )

            st.caption(
                f"📐 **Simulation** : {new_charge:,.2f} € × {new_taux:.2f} = **{calculated_threshold:,.2f} €**"
            )

            col_sub, _ = st.columns([1.5, 3])
            with col_sub:
                submitted = st.form_submit_button(
                    "💾 Enregistrer la modification", type="primary", width="stretch"
                )

            if submitted:
                success = update_config_alerte(
                    type_selectionne,
                    charge_moyenne=new_charge,
                    taux=new_taux,
                    threshold=new_threshold,
                )

                if success:
                    load_config.clear()
                    st.toast(f"Seuil mis à jour pour {type_selectionne.upper()} !", icon="💾")
                    st.rerun()
                else:
                    st.error("❌ Erreur lors de la sauvegarde.")
