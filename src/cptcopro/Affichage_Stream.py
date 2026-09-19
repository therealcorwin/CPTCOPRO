"""Application Streamlit pour la visualisation des données de copropriété.

Ce module définit l'application web Streamlit avec navigation multi-pages
pour visualiser et analyser les données des copropriétaires.

Pages disponibles (8 pages unifiées):
    - Dashboard: Vue d'ensemble et KPIs du suivi des charges
    - Liste_Charge: Suivi financier détaillé et comparateur multi-courbes
    - Rechercher_Copro: Espace Copropriétaires (Annuaire & Fiche 360° individuelle)
    - Alerte: Centre d'Alertes (actives, répartition par lot, historique, seuils)
    - Statistiques_Avancees: Analyses avancées & Balance Âgée (Aging Balance)
    - Relance: Assistant de génération des relances (IA Mistral / Modèles)
    - Relance_Drafts: Boîte d'envoi, brouillons et suivi d'efficacité
    - Relance_Config: Paramètres des relances, modèles types et OAuth2 Hotmail

Usage:
    Lancé automatiquement via streamlit_launcher ou manuellement:
    $ streamlit run src/cptcopro/Affichage_Stream.py
"""

from pathlib import Path

import streamlit as st

# Charger les variables d'environnement
try:
    from cptcopro.utils.env_loader import load_env_file

    load_env_file()
except ImportError:
    pass

try:
    from cptcopro.utils.ui_components import inject_custom_css
except ImportError:

    def inject_custom_css() -> None:
        pass


try:
    from cptcopro.utils.privacy import SESSION_KEY_PRIVACY
except ImportError:
    SESSION_KEY_PRIVACY = "masquer_donnees_sensibles"


if SESSION_KEY_PRIVACY not in st.session_state:
    st.session_state[SESSION_KEY_PRIVACY] = False


# --- Configuration de la page ---
st.set_page_config(
    page_title="CPTCOPRO - Suivi des Copropriétaires",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Injecter les styles CSS globaux
inject_custom_css()

# Initialisation et vérification du pool MariaDB
try:
    from cptcopro.Database.connection import init_pool, verif_connexion_db

    @st.cache_resource
    def _init_db_pool() -> object:
        pool = init_pool()
        verif_connexion_db()
        return pool

    _init_db_pool()
except Exception as exc:
    st.error(f"Erreur de connexion à la base de données MariaDB : {exc}")

# --- Configuration des 8 pages applicatives ---
Dashboard_page = st.Page(
    "Pages/Dashboard.py",
    title="Tableau de bord",
    icon=":material/dashboard:",
    default=True,
)

# Pôle Finances & Charges
Liste_Charge_page = st.Page(
    "Pages/Liste_Charge.py",
    title="Suivi des charges & débits",
    icon=":material/table_chart:",
)

# Pôle Copropriétaires
Recherche_Copro_page = st.Page(
    "Pages/Rechercher_Copro.py",
    title="Espace copropriétaires & 360°",
    icon=":material/group:",
)

# Pôle Risques & Alertes
Alerte_page = st.Page(
    "Pages/Alerte.py",
    title="Centre d'alertes & seuils",
    icon=":material/warning:",
)
Statistiques_Avancees_page = st.Page(
    "Pages/Statistiques_Avancees.py",
    title="Analyses & Balance âgée",
    icon=":material/insights:",
)

# Pôle Recouvrement & Relances
Relance_page = st.Page(
    "Pages/Relance.py",
    title="Assistant de relances",
    icon=":material/mark_email_unread:",
)
Relance_Drafts_page = st.Page(
    "Pages/Relance_Drafts.py",
    title="Brouillons & Boîte d'envoi",
    icon=":material/drafts:",
)
Relance_Config_page = st.Page(
    "Pages/Relance_Config.py",
    title="Paramètres & Modèles",
    icon=":material/settings:",
)

# --- NAVIGATION SETUP (5 PÔLES THÉMATIQUES - 8 PAGES) ---
menus = st.navigation(
    {
        "📊 Vue d'ensemble": [Dashboard_page],
        "💳 Finances & Charges": [Liste_Charge_page],
        "👥 Copropriétaires": [Recherche_Copro_page],
        "🚨 Risques & Alertes": [
            Alerte_page,
            Statistiques_Avancees_page,
        ],
        "✉️ Recouvrement & Relances": [
            Relance_page,
            Relance_Drafts_page,
            Relance_Config_page,
        ],
    },
    expanded=True,
)

# --- SIDEBAR BRANDING & ACTIONS ---
LOGO_PATH = Path(__file__).parent / "Pages" / "Assets" / "gb2.png"
if LOGO_PATH.exists():
    st.logo(str(LOGO_PATH), size="large")

# Bouton de rafraîchissement rapide du cache
st.sidebar.divider()
if st.sidebar.button(
    "🔄 Rafraîchir les données",
    use_container_width=True,
    help="Efface le cache local et recharge les données actualisées de la base",
):
    st.cache_data.clear()
    st.toast("Cache réinitialisé !", icon="🔄")
    st.rerun()

# Widget Santé du Système
with st.sidebar.expander("🩺 Santé du Système", expanded=False):
    try:
        from cptcopro.Database.connection import get_db_cursor

        with get_db_cursor() as cur:
            cur.execute("SELECT MAX(date) AS max_date FROM charge")
            row = cur.fetchone()
            max_d = row["max_date"] if row else None
            max_d_str = (
                max_d.strftime("%d/%m/%Y")
                if max_d and hasattr(max_d, "strftime")
                else (str(max_d) if max_d else "N/A")
            )
        st.markdown(f"🟢 **MariaDB** : Connecté\n\n📅 **Dernier relevé** : `{max_d_str}`")
    except Exception as err:
        st.markdown(f"🔴 **MariaDB** : Déconnecté (`{err}`)")

    try:
        from cptcopro.utils.hotmail_oauth import verifier_statut_token_hotmail

        token_ok, msg_token = verifier_statut_token_hotmail()
        if token_ok:
            st.markdown(f"🟢 **Hotmail OAuth2** : Connecté\n\n(`{msg_token}`)")
        else:
            st.markdown("🟠 **Hotmail OAuth2** : Déconnecté")
    except Exception as exc:
        st.markdown(f"⚪ **Hotmail OAuth2** : Non vérifié (`{exc}`)")

st.sidebar.caption("🏢 **CPTCOPRO** v2.0")
st.sidebar.caption("Made with ❤️ by [Therealcorwin](https://github.com/Therealcorwin)")


# --- RUN NAVIGATION ---
menus.run()
