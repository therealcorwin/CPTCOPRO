"""Gestion complète des brouillons et suivi des relances."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, cast

import streamlit as st

from cptcopro.Database import get_relance_config
from cptcopro.utils.paths import init_env
from cptcopro.utils.relance_views import (
    render_drafts_management,
    render_history_log,
    render_tracking_dashboard,
)
from cptcopro.utils.ui_components import render_header

# Charger le .env
init_env()


@st.cache_data(ttl=120, show_spinner=False)
def _load_config() -> dict[str, Any]:
    """Charge la configuration de relance."""
    return cast(dict[str, Any], get_relance_config())


render_header(
    "📬 Gestion des Brouillons & Suivi des Relances",
    "Consultez, modifiez et expédiez vos brouillons vers Hotmail (IMAP), ou analysez le recouvrement",
)

cfg = _load_config()

# Bannière OAuth2 si token Hotmail expiré
with suppress(Exception):
    from cptcopro.utils.hotmail_oauth import verifier_statut_token_hotmail

    _token_ok, _token_msg = verifier_statut_token_hotmail()
    if not _token_ok:
        st.warning(
            "📧 **Hotmail non connecté** : Le token OAuth2 est expiré ou absent. "
            "L'envoi IMAP vers Hotmail ne fonctionnera pas. "
            "🔐 Allez dans **Paramètres & Modèles → 🔧 Intégrations** pour vous authentifier.",
            icon="⚠️",
        )

tab_drafts, tab_tracking, tab_history = st.tabs(
    [
        "📬 Brouillons & Actions en Masse",
        "📊 Tableau de Bord & Suivi",
        "📜 Journal Chronologique des Échanges",
    ]
)

with tab_drafts:
    render_drafts_management(cfg)

with tab_tracking:
    render_tracking_dashboard()

with tab_history:
    render_history_log()
