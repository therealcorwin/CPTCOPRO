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

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st

from cptcopro.utils.analytics import load_system_health

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

# --- Configuration des 9 pages applicatives ---
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
    title="Centre d'alertes & impayés",
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
    title="Assistant & Suivi des relances",
    icon=":material/mark_email_unread:",
)
Relance_Drafts_page = st.Page(
    "Pages/Relance_Drafts.py",
    title="Brouillons & Boîte d'envoi",
    icon=":material/drafts:",
)
Relance_Config_page = st.Page(
    "Pages/Relance_Config.py",
    title="Configuration & Paramètres",
    icon=":material/settings:",
)

Bilan_AG_page = st.Page(
    "Pages/Bilan_AG.py",
    title="Bilan AG & Rapport annuel",
    icon=":material/description:",
)

# --- NAVIGATION SETUP (5 PÔLES THÉMATIQUES - 9 PAGES) ---
menus = st.navigation(
    {
        "📊 Vue d'ensemble": [Dashboard_page],
        "💳 Finances & Charges": [Liste_Charge_page, Bilan_AG_page],
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

# --- MODALE DE SYNCHRONISATION EXTRANET ---
def _handle_sync_log_line(line: str, status_box: Any) -> None:  # noqa: ANN401
    """Affiche les messages d'étape clés dans le conteneur de statut."""
    if "HTML des charges" in line or "HTML des lots" in line:
        status_box.write("📥 Relevés HTML récupérés depuis le portail...")
    elif "Date de situation" in line:
        status_box.write("📅 Date de situation identifiée...")
    elif "lots de copropriétaires extraits" in line:
        status_box.write("🔍 Lots extraits et consolidés...")
    elif "données sauvegardées" in line:
        status_box.write("💾 Écriture MariaDB et calcul des alertes terminés...")
    elif "Sauvegarde pCloud terminée" in line:
        status_box.write("☁️ Sauvegarde distante pCloud effectuée...")


def _execute_extranet_sync(cmd: list[str]) -> None:
    """Exécute la commande de synchronisation et met à jour l'interface Streamlit."""
    with st.status(
        "Connexion au portail extranet et récupération des données...", expanded=True
    ) as status_box:
        try:
            proc = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(Path(__file__).parent.parent.parent),
            )
            output_lines: list[str] = []
            if proc.stdout:
                for line in proc.stdout:
                    cleaned = line.strip()
                    if cleaned:
                        output_lines.append(cleaned)
                        _handle_sync_log_line(cleaned, status_box)
            proc.wait()
            if proc.returncode == 0:
                status_box.update(
                    label="Synchronisation terminée avec succès !",
                    state="complete",
                    expanded=False,
                )
                st.cache_data.clear()
                st.toast("Données synchronisées avec succès !", icon="✅")
                time.sleep(1)
                st.rerun()
            else:
                status_box.update(
                    label="Échec de la synchronisation",
                    state="error",
                    expanded=True,
                )
                st.error("Une erreur est survenue pendant la collecte.")
                if output_lines:
                    st.code("\n".join(output_lines[-10:]), language="text")
        except Exception as exc:
            status_box.update(
                label=f"Erreur d'exécution : {exc}",
                state="error",
                expanded=True,
            )


@st.dialog("🌐 Synchronisation Extranet Syndic")
def dialog_sync_extranet() -> None:
    st.write(
        "Cette opération lance le scraping Playwright pour récupérer les derniers relevés "
        "de charges et de lots sur le portail du syndic, met à jour MariaDB et effectue une sauvegarde pCloud."
    )
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        auto_relance = st.checkbox(
            "Générer brouillons de relance",
            value=False,
            key="sync_opt_auto_relance",
        )
    with col_opt2:
        relance_imap = st.checkbox(
            "Déposer sur Hotmail (IMAP)",
            value=False,
            disabled=not auto_relance,
            key="sync_opt_relance_imap",
        )

    st.caption("⏱️ Durée estimée : 20 à 45 secondes.")

    if st.button("🚀 Lancer la synchronisation", type="primary", width="stretch", key="btn_start_sync_pipeline"):
        cmd = [sys.executable, "-m", "cptcopro.main", "--no-serve"]
        if auto_relance:
            cmd.append("--auto-relance-drafts")
        if auto_relance and relance_imap:
            cmd.append("--relance-imap")
        _execute_extranet_sync(cmd)


# --- SIDEBAR BRANDING & ACTIONS ---
LOGO_PATH = Path(__file__).parent / "Pages" / "Assets" / "gb2.png"
if LOGO_PATH.exists():
    st.logo(str(LOGO_PATH), size="large")

# Boutons d'actions rapides
st.sidebar.divider()
col_sync1, col_sync2 = st.sidebar.columns(2)
with col_sync1:
    if st.button(
        "🔄 Cache",
        width="stretch",
        help="Efface le cache local et recharge les données de la base",
        key="btn_refresh_cache_sidebar",
    ):
        st.cache_data.clear()
        st.toast("Cache réinitialisé !", icon="🔄")
        st.rerun()
with col_sync2:
    if st.button(
        "🌐 Extranet",
        width="stretch",
        type="primary",
        help="Récupère les derniers relevés du portail syndic via Playwright",
        key="btn_open_sync_dialog",
    ):
        dialog_sync_extranet()

# Mode confidentialité RGPD / projection
st.sidebar.toggle(
    "🔒 Masquer données sensibles",
    key=SESSION_KEY_PRIVACY,
    help="Masque les noms et données personnelles des copropriétaires (mode projection / RGPD)",
)

# Widget Santé du Système (mis en cache pour une navigation instantanée)
health = load_system_health()
with st.sidebar.expander("🩺 Santé du Système", expanded=False):
    if health["db_ok"]:
        st.markdown(f"🟢 **MariaDB** : {health['db_msg']}\n\n📅 **Dernier relevé** : `{health['max_date_str']}`")
    else:
        st.markdown(f"🔴 **MariaDB** : {health['db_msg']}")

    if health["hotmail_ok"]:
        st.markdown(f"🟢 **Hotmail OAuth2** : Connecté\n\n(`{health['hotmail_msg']}`)")
    else:
        st.markdown(f"🟠 **Hotmail OAuth2** : {health['hotmail_msg']}")

st.sidebar.caption("🏢 **CPTCOPRO** v2.0")
st.sidebar.caption("Made with ❤️ by [Therealcorwin](https://github.com/Therealcorwin)")


# --- RUN NAVIGATION ---
menus.run()
