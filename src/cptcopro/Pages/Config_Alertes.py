"""Page de configuration des seuils d'alerte par typologie d'appartement."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cptcopro.Database import (
    DEFAULT_THRESHOLD_FALLBACK,
    get_config_alertes,
    update_config_alerte,
)
from cptcopro.utils.ui_components import render_header


@st.cache_data(ttl=300, show_spinner=False)
def load_config() -> pd.DataFrame:
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


render_header(
    "⚙️ Configuration des Seuils d'Alerte",
    "Définition des montants de charges moyennes et des seuils de déclenchement des alertes d'impayés",
)

config_df = load_config()


if config_df.empty:
    st.warning("⚠️ Aucune configuration trouvée dans la base de données.")
    st.stop()

# ============================================================================
# TABLEAU DE LA CONFIGURATION ACTUELLE
# ============================================================================
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
            "Taux": st.column_config.NumberColumn("Coefficient", format="%.2f", width="small"),
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
    st.markdown("""
    Une alerte est déclenchée pour un copropriétaire si son débit dépasse le seuil défini :

    $$\\text{Seuil} = \\text{Charge Moyenne} \\times \\text{Taux}$$

    - **Taux 1.33** = Alerte dès 33% au-dessus de la moyenne
    - **Taux 1.50** = Alerte dès 50% au-dessus de la moyenne
    """)

st.divider()

# ============================================================================
# FORMULAIRE DE MODIFICATION INTERACTIF
# ============================================================================
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

with st.form("form_modifier_seuil"):
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
            "💾 Enregistrer la modification", type="primary", use_container_width=True
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
