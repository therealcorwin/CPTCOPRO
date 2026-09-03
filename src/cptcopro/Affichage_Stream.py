"""Application Streamlit pour la visualisation des données de copropriété.

Ce module définit l'application web Streamlit avec navigation multi-pages
pour visualiser et analyser les données des copropriétaires.

Pages disponibles:
    - Dashboard: Vue d'ensemble du suivi des charges
    - Liste Charge: Suivi détaillé des charges par copropriétaire
    - Courbe Charge Copro: Analyse graphique des débits
    - Alertes: Suivi des copropriétaires en situation d'alerte
    - Config Alertes: Configuration des seuils d'alerte par type d'appartement
    - Liste Copro: Liste complète des copropriétaires
    - Recherche Copro: Recherche d'informations sur un copropriétaire

Usage:
    Lancé automatiquement via streamlit_launcher ou manuellement:
    $ streamlit run src/cptcopro/Affichage_Stream.py

Note:
    Les pages sont définies dans le dossier Pages/ avec leurs assets
    dans Pages/Assets/.
"""

from pathlib import Path

import streamlit as st

# Charger les variables d'environnement
try:
    from cptcopro.utils.paths import init_env

    init_env()
except ImportError:
    pass  # Fallback si l'import échoue

try:
    from cptcopro.utils.ui_components import inject_custom_css
except ImportError:

    def inject_custom_css() -> None:
        pass


# --- Configuration de la page ---
st.set_page_config(
    page_title="CPTCOPRO - Suivi des Copropriétaires",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Injecter les styles CSS globaux
inject_custom_css()

# --- Configuration des pages ---
Dashboard_page = st.Page(
    "Pages/Dashboard.py",
    title="Tableau de bord",
    icon=":material/dashboard:",
    default=True,
)

# Pôle Charges
Liste_Charge_page = st.Page(
    "Pages/Liste_Charge.py",
    title="Suivi détaillé des charges",
    icon=":material/table_chart:",
)
Courbe_Charge_Corpo_page = st.Page(
    "Pages/Courbe_Charge_Copro.py",
    title="Évolution & Analyse des débits",
    icon=":material/show_chart:",
)

# Pôle Copropriétaires
Recherche_Copro_page = st.Page(
    "Pages/Rechercher_Copro.py",
    title="Recherche & Fiche copropriétaire",
    icon=":material/person_search:",
)
Liste_Copro_page = st.Page(
    "Pages/Liste_Copro.py",
    title="Annuaire des copropriétaires",
    icon=":material/group:",
)

# Pôle Alertes & Risques
Alerte_page = st.Page(
    "Pages/Alerte.py",
    title="Alertes actives",
    icon=":material/warning:",
)
Statistiques_Avancees_page = st.Page(
    "Pages/Statistiques_Avancees.py",
    title="Analyses & Statistiques avancées",
    icon=":material/insights:",
)
Stat_Alerte_page = st.Page(
    "Pages/Stat_Alerte.py",
    title="Historique & Répartition",
    icon=":material/pie_chart:",
)
Config_Alertes_page = st.Page(
    "Pages/Config_Alertes.py",
    title="Configuration des seuils",
    icon=":material/tune:",
)

# Pôle Relances & Notifications
Relance_page = st.Page(
    "Pages/Relance.py",
    title="Génération des relances (IA)",
    icon=":material/mark_email_unread:",
)
Relance_Drafts_page = st.Page(
    "Pages/Relance_Drafts.py",
    title="Brouillons & Boîte d'envoi",
    icon=":material/drafts:",
)
Relance_Templates_page = st.Page(
    "Pages/Relance_Templates.py",
    title="Modèles d'emails",
    icon=":material/description:",
)
Relance_Config_page = st.Page(
    "Pages/Relance_Config.py",
    title="Paramètres messagerie & IA",
    icon=":material/settings:",
)
Relance_Admin_page = st.Page(
    "Pages/Relance_Admin.py",
    title="Administration",
    icon=":material/admin_panel_settings:",
)

# --- NAVIGATION SETUP [WITH SECTIONS]---
menus = st.navigation(
    {
        "📊 Vue d'ensemble": [Dashboard_page],
        "💳 Charges & Débits": [Liste_Charge_page, Courbe_Charge_Corpo_page],
        "👥 Copropriétaires": [Recherche_Copro_page, Liste_Copro_page],
        "🚨 Centre d'Alertes": [
            Alerte_page,
            Statistiques_Avancees_page,
            Stat_Alerte_page,
            Config_Alertes_page,
        ],
        "✉️ Relances & Messagerie": [
            Relance_page,
            Relance_Drafts_page,
            Relance_Templates_page,
            Relance_Config_page,
            Relance_Admin_page,
        ],
    },
    expanded=True,
)

# --- SIDEBAR BRANDING & CONTROLS ---
LOGO_PATH = Path(__file__).parent / "Pages" / "Assets" / "gb2.png"
if LOGO_PATH.exists():
    st.logo(str(LOGO_PATH), size="large")

# Toggle de confidentialité dans la sidebar
st.sidebar.divider()
st.sidebar.markdown("### 🔒 Sécurité & Confidentialité")
privacy_enabled = st.sidebar.toggle(
    "Masquer données sensibles",
    key="masquer_donnees_sensibles",
    help="Anonymise les noms, codes et numéros de lots sur l'ensemble des pages de l'application.",
)
if privacy_enabled:
    st.sidebar.info("🛡️ Mode anonymisé activé")

st.sidebar.divider()
st.sidebar.caption("🏢 **CPTCOPRO** v2.0")
st.sidebar.caption("Made with ❤️ by [Therealcorwin](https://github.com/Therealcorwin)")

# --- RUN NAVIGATION ---
menus.run()
