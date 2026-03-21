"""Page Streamlit pour les statistiques avancées.

Cette page fournit des analyses statistiques complémentaires :
- Distribution des débits (histogramme)
- Charge moyenne par type d'appartement
- Taux de récidive des alertes
- Propriétaires à risque (proches du seuil)
- Durée moyenne des alertes
- Saisonnalité des impayés
"""

import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from streamlit_extras.metric_cards import style_metric_cards

# Import du module de chemins portables
try:
    from cptcopro.utils.paths import get_db_path
    from cptcopro.utils.privacy import appliquer_confidentialite, is_privacy_enabled

    DB_PATH = get_db_path()
except ImportError:
    DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"
    from cptcopro.utils.privacy import appliquer_confidentialite, is_privacy_enabled


# ============================================================================
# Fonctions de chargement des données
# ============================================================================


@st.cache_data
def load_charges(db_path: Path) -> pd.DataFrame:
    """Charge toutes les charges depuis la vue."""
    with sqlite3.connect(str(db_path)) as conn:
        df = pd.read_sql_query(
            """SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, 
                      num_apt, type_apt, debit, credit, date 
               FROM vw_charge_coproprietaires""",
            conn,
        )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["mois"] = df["date"].dt.month
    df["annee"] = df["date"].dt.year
    df["mois_nom"] = df["date"].dt.strftime("%B")
    return df


@st.cache_data
def load_alertes(db_path: Path) -> pd.DataFrame:
    """Charge les alertes actives."""
    with sqlite3.connect(str(db_path)) as conn:
        df = pd.read_sql_query(
            """SELECT nom_proprietaire AS proprietaire, code_proprietaire AS code, 
                      debit, type_alerte, first_detection, last_detection, occurence 
               FROM alertes_debit_eleve""",
            conn,
        )
    df["first_detection"] = pd.to_datetime(df["first_detection"], errors="coerce")
    df["last_detection"] = pd.to_datetime(df["last_detection"], errors="coerce")
    df["duree_jours"] = (df["last_detection"] - df["first_detection"]).dt.days
    return df


@st.cache_data
def load_config_alertes(db_path: Path) -> pd.DataFrame:
    """Charge la configuration des seuils d'alerte."""
    with sqlite3.connect(str(db_path)) as conn:
        df = pd.read_sql_query(
            "SELECT type_apt, charge_moyenne, taux, threshold FROM config_alerte",
            conn,
        )
    return df


@st.cache_data
def load_coproprietaires(db_path: Path) -> pd.DataFrame:
    """Charge la liste des copropriétaires."""
    with sqlite3.connect(str(db_path)) as conn:
        df = pd.read_sql_query(
            "SELECT nom_proprietaire, code_proprietaire, type_apt FROM coproprietaires",
            conn,
        )
    return df


# ============================================================================
# Configuration de la page
# ============================================================================

st.set_page_config(page_title="Statistiques Avancées", layout="wide")
st.title("📊 Statistiques Avancées")
st.markdown("Analyses statistiques complémentaires des données de copropriété.")

# Debug: afficher l'état de confidentialité
if is_privacy_enabled():
    st.info("🔒 Mode confidentiel actif - données anonymisées")

# Chargement des données
charges_df = load_charges(DB_PATH)
alertes_df = load_alertes(DB_PATH)
config_df = load_config_alertes(DB_PATH)
copro_df = load_coproprietaires(DB_PATH)

if charges_df.empty:
    st.warning("Aucune donnée de charges disponible.")
    st.stop()

# ============================================================================
# Section 1: Distribution des débits
# ============================================================================

st.header("1️⃣ Distribution des débits")

# Prendre le dernier débit par propriétaire
derniere_date = charges_df["date"].max()
derniers_debits = charges_df[charges_df["date"] == derniere_date].copy()

col1, col2 = st.columns(2)

with col1:
    # Histogramme des débits
    fig_hist = px.histogram(
        derniers_debits,
        x="debit",
        nbins=30,
        title=f"Distribution des débits au {derniere_date.strftime('%d/%m/%Y')}",
        labels={"debit": "Débit (€)", "count": "Nombre de propriétaires"},
        color_discrete_sequence=["#636EFA"],
    )

    # Ajouter les lignes de seuils
    for _, row in config_df.iterrows():
        if row["type_apt"] != "default":
            fig_hist.add_vline(
                x=row["threshold"],
                line_dash="dash",
                line_color="red",
                annotation_text=f"Seuil {row['type_apt']}",
                annotation_position="top",
            )

    st.plotly_chart(fig_hist, width="stretch")

with col2:
    # Statistiques descriptives
    st.subheader("Statistiques descriptives")
    stats = derniers_debits["debit"].describe()

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Moyenne", f"{stats['mean']:.2f} €")
        style_metric_cards(background_color="#292D34")
    with col_b:
        st.metric("Médiane", f"{stats['50%']:.2f} €")
        style_metric_cards(background_color="#292D34")
    with col_c:
        st.metric("Écart-type", f"{stats['std']:.2f} €")
        style_metric_cards(background_color="#292D34")

    col_d, col_e, col_f = st.columns(3)
    with col_d:
        st.metric("Minimum", f"{stats['min']:.2f} €")
        style_metric_cards(background_color="#292D34")
    with col_e:
        st.metric("Maximum", f"{stats['max']:.2f} €")
        style_metric_cards(background_color="#292D34")
    with col_f:
        st.metric("Nb propriétaires", f"{int(stats['count'])}")
        style_metric_cards(background_color="#292D34")

st.divider()

# ============================================================================
# Section 2: Charge moyenne par type d'appartement
# ============================================================================

st.header("2️⃣ Charge moyenne par type d'appartement")

# Joindre les types d'appartement
derniers_debits_typed = derniers_debits.merge(
    copro_df[["code_proprietaire", "type_apt"]].rename(
        columns={"code_proprietaire": "code"}
    ),
    on="code",
    how="left",
    suffixes=("", "_copro"),
)
derniers_debits_typed["type_apt"] = (
    derniers_debits_typed["type_apt_copro"]
    .fillna(derniers_debits_typed["type_apt"])
    .fillna("NA")
)

# Calculer les moyennes par type
stats_par_type = (
    derniers_debits_typed.groupby("type_apt")
    .agg(
        moyenne_debit=("debit", "mean"),
        mediane_debit=("debit", "median"),
        nb_proprietaires=("code", "count"),
        total_debit=("debit", "sum"),
    )
    .reset_index()
)

# Ajouter les seuils de config
stats_par_type = stats_par_type.merge(
    config_df[["type_apt", "threshold", "charge_moyenne"]].rename(
        columns={"charge_moyenne": "charge_ref"}
    ),
    on="type_apt",
    how="left",
)

col1, col2 = st.columns(2)

with col1:
    # Bar chart comparatif
    fig_bar = go.Figure()

    fig_bar.add_trace(
        go.Bar(
            name="Moyenne réelle",
            x=stats_par_type["type_apt"],
            y=stats_par_type["moyenne_debit"],
            marker_color="#636EFA",
        )
    )

    fig_bar.add_trace(
        go.Bar(
            name="Charge référence",
            x=stats_par_type["type_apt"],
            y=stats_par_type["charge_ref"],
            marker_color="#EF553B",
        )
    )

    fig_bar.add_trace(
        go.Scatter(
            name="Seuil alerte",
            x=stats_par_type["type_apt"],
            y=stats_par_type["threshold"],
            mode="markers+lines",
            marker=dict(size=10, symbol="diamond"),
            line=dict(dash="dash"),
        )
    )

    fig_bar.update_layout(
        title="Comparaison des charges par type d'appartement",
        xaxis_title="Type d'appartement",
        yaxis_title="Montant (€)",
        barmode="group",
    )

    st.plotly_chart(fig_bar, width="stretch")

with col2:
    # Tableau récapitulatif
    st.subheader("Détail par type")
    display_df = stats_par_type[
        ["type_apt", "nb_proprietaires", "moyenne_debit", "mediane_debit", "threshold"]
    ].copy()
    display_df.columns = [
        "Type",
        "Nb proprio",
        "Moyenne (€)",
        "Médiane (€)",
        "Seuil (€)",
    ]
    display_df["Moyenne (€)"] = display_df["Moyenne (€)"].round(2)
    display_df["Médiane (€)"] = display_df["Médiane (€)"].round(2)
    display_df["Seuil (€)"] = display_df["Seuil (€)"].round(2)
    st.dataframe(display_df, width="stretch", hide_index=True)

st.divider()

# ============================================================================
# Section 3: Taux de récidive et durée des alertes
# ============================================================================

st.header("3️⃣ Analyse des alertes")

if not alertes_df.empty:
    col1, col2, col3 = st.columns(3)

    # Taux de récidive
    nb_recidivistes = len(alertes_df[alertes_df["occurence"] > 1])
    nb_total_alertes = len(alertes_df)
    taux_recidive = (
        (nb_recidivistes / nb_total_alertes * 100) if nb_total_alertes > 0 else 0
    )

    with col1:
        st.metric(
            "Taux de récidive",
            f"{taux_recidive:.1f}%",
            help="Propriétaires avec plus d'une occurrence d'alerte",
        )
        style_metric_cards(background_color="#292D34")

    # Durée moyenne des alertes
    duree_moyenne = alertes_df["duree_jours"].mean()
    with col2:
        st.metric(
            "Durée moyenne alerte",
            f"{duree_moyenne:.0f} jours",
            help="Temps entre première et dernière détection",
        )
        style_metric_cards(background_color="#292D34")

    # Occurrence moyenne
    occ_moyenne = alertes_df["occurence"].mean()
    with col3:
        st.metric(
            "Occurrence moyenne",
            f"{occ_moyenne:.1f}",
            help="Nombre moyen de fois qu'un propriétaire est en alerte",
        )
        style_metric_cards(background_color="#292D34")

    col1, col2 = st.columns(2)

    with col1:
        # Pie chart répartition par type
        repartition = alertes_df.groupby("type_alerte").size().reset_index(name="count")
        fig_pie = px.pie(
            repartition,
            values="count",
            names="type_alerte",
            title="Répartition des alertes par type d'appartement",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        st.plotly_chart(fig_pie, width="stretch")

    with col2:
        # Top récidivistes
        st.subheader("Top 10 récidivistes")
        top_recidivistes = alertes_df.nlargest(10, "occurence")[
            ["proprietaire", "type_alerte", "debit", "occurence", "duree_jours"]
        ].copy()
        top_recidivistes.columns = [
            "Propriétaire",
            "Type",
            "Débit (€)",
            "Occurrences",
            "Durée (j)",
        ]

        # Anonymisation directe pour cette page (contourne le cache)
        if is_privacy_enabled():
            top_recidivistes["Propriétaire"] = "●●●●●●"

        st.dataframe(
            top_recidivistes,
            width="stretch",
            hide_index=True,
        )
else:
    st.info("Aucune alerte active actuellement.")

st.divider()

# ============================================================================
# Section 4: Propriétaires à risque
# ============================================================================

st.header("4️⃣ Propriétaires à risque (proches du seuil)")

# Calculer la marge par rapport au seuil
derniers_debits_risk = derniers_debits_typed.merge(
    config_df[["type_apt", "threshold"]],
    on="type_apt",
    how="left",
)

# Fallback seuil par défaut
default_threshold = config_df[config_df["type_apt"] == "default"]["threshold"].values
if len(default_threshold) > 0:
    derniers_debits_risk["threshold"] = derniers_debits_risk["threshold"].fillna(
        default_threshold[0]
    )
else:
    derniers_debits_risk["threshold"] = derniers_debits_risk["threshold"].fillna(2000)

derniers_debits_risk["marge"] = (
    derniers_debits_risk["threshold"] - derniers_debits_risk["debit"]
)
derniers_debits_risk["pct_seuil"] = (
    derniers_debits_risk["debit"] / derniers_debits_risk["threshold"] * 100
)

# Slider pour définir la zone de risque
pct_risque = st.slider(
    "Seuil de risque (% du seuil d'alerte)",
    min_value=50,
    max_value=99,
    value=80,
    help="Les propriétaires au-dessus de ce pourcentage sont considérés à risque",
)

# Filtrer les propriétaires à risque (pas encore en alerte mais proches)
a_risque = derniers_debits_risk[
    (derniers_debits_risk["pct_seuil"] >= pct_risque)
    & (derniers_debits_risk["pct_seuil"] < 100)
].sort_values("pct_seuil", ascending=False)

col1, col2 = st.columns([1, 2])

with col1:
    st.metric("Propriétaires à risque", len(a_risque))
    style_metric_cards(background_color="#292D34")

    if not a_risque.empty:
        total_risque = a_risque["debit"].sum()
        st.metric("Débit total à risque", f"{total_risque:,.2f} €")
        style_metric_cards(background_color="#292D34")

with col2:
    if not a_risque.empty:
        display_risk = (
            a_risque[["proprietaire", "type_apt", "debit", "threshold", "pct_seuil"]]
            .head(15)
            .copy()
        )
        display_risk.columns = [
            "Propriétaire",
            "Type",
            "Débit (€)",
            "Seuil (€)",
            "% du seuil",
        ]
        display_risk["% du seuil"] = display_risk["% du seuil"].round(1)

        # Anonymisation directe pour cette page
        if is_privacy_enabled():
            display_risk["Propriétaire"] = "●●●●●●"

        st.dataframe(display_risk, width="stretch", hide_index=True)
    else:
        st.success(
            f"Aucun propriétaire n'est au-dessus de {pct_risque}% du seuil d'alerte."
        )

st.divider()

# ============================================================================
# Section 5: Saisonnalité des impayés
# ============================================================================

st.header("5️⃣ Saisonnalité des impayés")

# Calculer le débit moyen par mois
saisonnalite = (
    charges_df.groupby("mois")
    .agg(
        debit_moyen=("debit", "mean"),
        debit_total=("debit", "sum"),
        nb_releves=("date", "nunique"),
    )
    .reset_index()
)

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
saisonnalite["mois_nom"] = saisonnalite["mois"].map(mois_noms)

col1, col2 = st.columns(2)

with col1:
    # Bar chart saisonnalité
    fig_saison = px.bar(
        saisonnalite,
        x="mois_nom",
        y="debit_moyen",
        title="Débit moyen par mois",
        labels={"mois_nom": "Mois", "debit_moyen": "Débit moyen (€)"},
        color="debit_moyen",
        color_continuous_scale="RdYlGn_r",
    )
    fig_saison.update_layout(
        xaxis={"categoryorder": "array", "categoryarray": list(mois_noms.values())}
    )
    st.plotly_chart(fig_saison, width="stretch")

with col2:
    # Identifier les mois critiques
    mois_max = saisonnalite.loc[saisonnalite["debit_moyen"].idxmax()]
    mois_min = saisonnalite.loc[saisonnalite["debit_moyen"].idxmin()]

    st.subheader("Analyse saisonnière")

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric(
            "Mois le plus critique",
            mois_max["mois_nom"],
            f"{mois_max['debit_moyen']:.2f} € en moyenne",
        )
        style_metric_cards(background_color="#292D34")
    with col_b:
        st.metric(
            "Mois le moins critique",
            mois_min["mois_nom"],
            f"{mois_min['debit_moyen']:.2f} € en moyenne",
        )
        style_metric_cards(background_color="#292D34")

    # Variation saisonnière
    variation = (
        (mois_max["debit_moyen"] - mois_min["debit_moyen"])
        / mois_min["debit_moyen"]
        * 100
    )
    st.metric("Variation saisonnière", f"{variation:.1f}%")
    style_metric_cards(background_color="#292D34")

st.divider()

# ============================================================================
# Section 6: Ratio crédit/débit
# ============================================================================

st.header("6️⃣ Ratio crédit/débit")

# Calculer le ratio pour chaque propriétaire (dernière date)
derniers_debits_ratio = derniers_debits.copy()
derniers_debits_ratio["ratio"] = derniers_debits_ratio.apply(
    lambda r: r["credit"] / r["debit"] if r["debit"] > 0 else float("inf"), axis=1
)

# Filtrer les ratios valides
ratios_valides = derniers_debits_ratio[
    (derniers_debits_ratio["ratio"] != float("inf"))
    & (derniers_debits_ratio["ratio"] >= 0)
]

col1, col2 = st.columns(2)

with col1:
    # Distribution des ratios
    fig_ratio = px.histogram(
        ratios_valides[ratios_valides["ratio"] <= 2],  # Limiter pour lisibilité
        x="ratio",
        nbins=20,
        title="Distribution du ratio crédit/débit",
        labels={"ratio": "Ratio crédit/débit", "count": "Nombre"},
        color_discrete_sequence=["#00CC96"],
    )
    fig_ratio.add_vline(
        x=1, line_dash="dash", line_color="red", annotation_text="Équilibre"
    )
    st.plotly_chart(fig_ratio, width="stretch")

with col2:
    # Statistiques
    nb_equilibre = len(ratios_valides[ratios_valides["ratio"] >= 1])
    nb_deficit = len(ratios_valides[ratios_valides["ratio"] < 1])

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric(
            "Crédit ≥ Débit", nb_equilibre, help="Propriétaires à jour ou en avance"
        )
        style_metric_cards(background_color="#292D34")
    with col_b:
        st.metric(
            "Crédit < Débit", nb_deficit, help="Propriétaires en retard de paiement"
        )
        style_metric_cards(background_color="#292D34")

    ratio_moyen = ratios_valides["ratio"].mean()
    st.metric("Ratio moyen", f"{ratio_moyen:.2f}")
    style_metric_cards(background_color="#292D34")

# Footer
st.divider()
st.caption(
    f"Données au {derniere_date.strftime('%d/%m/%Y')} — {len(charges_df)} enregistrements analysés"
)
