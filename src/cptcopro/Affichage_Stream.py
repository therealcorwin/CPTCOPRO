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
import streamlit as st
from pathlib import Path

# --- Configuration de la page ---
st.set_page_config(
    page_title="Suivi Charges Copropriétaires",
    layout="wide"
)

# --- COnfiguration de la navigation ---
Dashboard_page = st.Page(
    "Pages/Dashboard.py",
    title="Dashboard Suivi Charges",
    icon=":material/account_circle:",
    default=True,
)
Liste_Charge_page = st.Page(
    "Pages/Liste_Charge.py",
    title="Suivi détaillé des charges",
    icon=":material/bar_chart:",
)
Liste_Copro_page = st.Page(
    "Pages/Liste_Copro.py",
    title="Liste des copropriétaires",
    icon=":material/smart_toy:",
)
Courbe_Charge_Corpo_page = st.Page(
    "Pages/Courbe_Charge_Copro.py",
    title="Analyse des débits",
    icon=":material/trending_up:",
)

Alerte_page = st.Page(
    "Pages/Alerte.py",
    title="Alertes",
    icon=":material/warning:",
)

Stat_Alerte_page = st.Page(
    "Pages/Stat_Alerte.py",
    title="Statistiques Alertes",
    icon=":material/area_chart:",
)

Config_Alertes_page = st.Page(
    "Pages/Config_Alertes.py",
    title="Configuration Alertes",
    icon=":material/settings:",
)
Recherche_Copro_page = st.Page(
    "Pages/Rechercher_Copro.py",
    title="Recherche Info Copropriétaires",
    icon=":material/search:",
)

# --- NAVIGATION SETUP [WITH SECTIONS]---
menus = st.navigation(
    {
        "Dashboard Général": [Dashboard_page],
        "Suivi des Charges": [Liste_Charge_page, Courbe_Charge_Corpo_page],
        "Suivi Alerte": [Alerte_page, Stat_Alerte_page,Config_Alertes_page],
        "Liste des Copropriétaires": [Liste_Copro_page],
        "Recherche Info Copropriétaires": [Recherche_Copro_page],
    }
)

# --- SHARED ON ALL PAGES ---
# Construire un chemin absolu vers l'image du logo
# pour éviter les problèmes de chemin relatif.
LOGO_PATH = Path(__file__).parent / "Pages" / "Assets" / "gb2.png"
st.logo(str(LOGO_PATH), size="large")
st.sidebar.markdown("Made with ❤️ by [Therealcorwin](https://github.com/Therealcorwin)")

# --- RUN NAVIGATION ---
menus.run()
