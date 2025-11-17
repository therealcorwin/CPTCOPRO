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
Recherche_Copro_page = st.Page(
    "Pages/Rechercher_Copro.py",
    title="Recherche Info Copropriétaires",
    icon=":material/search:",
)# --- NAVIGATION SETUP [WITHOUT SECTIONS] ---
# pg = st.navigation(pages=[about_page, project_1_page, project_2_page])

# --- NAVIGATION SETUP [WITH SECTIONS]---
menus = st.navigation(
    {
        "Dashboard Général": [Dashboard_page],
        "Suivi des Charges": [Liste_Charge_page, Courbe_Charge_Corpo_page, Alerte_page],
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
