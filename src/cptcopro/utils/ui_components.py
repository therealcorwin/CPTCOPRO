"""Composants et utilitaires d'interface utilisateur pour Streamlit.

Ce module centralise :
- L'injection de styles CSS cohérents
- La standardisation des en-têtes de page sécurisés contre XSS
- Le formatage des graphiques Plotly aux couleurs du thème
- Les badges de statut et alertes visuelles
"""

from __future__ import annotations

import html

import plotly.graph_objects as go
import st_yled
import st_yled.constants
import streamlit as st

from cptcopro.utils.privacy import SESSION_KEY_PRIVACY, is_privacy_enabled

_ALLOWED_BADGE_VARIANTS: set[str] = {"info", "warning", "success", "danger"}

# Configuration robuste de st-styled pour les boutons (compatible tooltip help et pill design)
_btn_selector = ".stButton button"
_btn_p_selector = ".stButton button p"
st_yled.constants.ELEMENT_STYLES.setdefault("button", {})["css"] = {
    "background_color": {_btn_selector: {"background-color": None}},
    "border_color": {_btn_selector: {"border-color": None}},
    "border_style": {_btn_selector: {"border-style": None}},
    "border_width": {_btn_selector: {"border-width": None}},
    "color": {_btn_selector: {"color": None}},
    "font_size": {_btn_p_selector: {"font-size": None}},
    "font_weight": {_btn_p_selector: {"font-weight": None}},
    "border_radius": {_btn_selector: {"border-radius": None}},
    "padding": {_btn_selector: {"padding": None}},
}


def inject_custom_css() -> None:
    """Injecte des règles CSS additionnelles pour parfaire le design de l'application."""
    custom_css = """
    <style>
    /* Amélioration de la police et des espacements */
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    /* Cartes métriques modernes avec bordure douce */
    [data-testid="stMetric"] {
        background-color: #1E293B;
        padding: 1rem 1.25rem;
        border-radius: 0.75rem;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        color: #94A3B8 !important;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #F8FAFC !important;
    }

    /* Onglets modernes */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #334155;
    }

    .stTabs [data-baseweb="tab"] {
        height: 44px;
        border-radius: 6px 6px 0 0;
        font-weight: 500;
        color: #94A3B8;
        padding: 0 16px;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1E293B !important;
        color: #38BDF8 !important;
        border-bottom: 2px solid #0284C7 !important;
    }

    /* Badges personnalisés */
    .badge-pill {
        display: inline-flex;
        align-items: center;
        padding: 0.25rem 0.6rem;
        font-size: 0.75rem;
        font-weight: 600;
        border-radius: 9999px;
    }
    .badge-info {
        background-color: rgba(2, 132, 199, 0.2);
        color: #38BDF8;
        border: 1px solid rgba(2, 132, 199, 0.4);
    }
    .badge-warning {
        background-color: rgba(245, 158, 11, 0.2);
        color: #FBBF24;
        border: 1px solid rgba(245, 158, 11, 0.4);
    }
    .badge-success {
        background-color: rgba(16, 185, 129, 0.2);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .badge-danger {
        background-color: rgba(239, 68, 68, 0.2);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
    }

    /* Bouton badge cliquable de confidentialité dans l'en-tête */
    div[data-testid="stColumn"]:last-child div.stButton,
    div[data-testid="column"]:last-child div.stButton,
    [data-testid="column"]:last-child div.stButton {
        display: flex;
        justify-content: flex-end;
    }

    /* Suppression de l'espace vide sous le menu de navigation dans la barre latérale */
    [data-testid="stSidebarUserContent"] {
        padding-top: 0 !important;
    }
    [data-testid="stSidebarNav"] {
        padding-bottom: 0 !important;
        margin-bottom: 0 !important;
    }
    </style>
    """

    st.markdown(custom_css, unsafe_allow_html=True)


def render_header(
    title: str,
    subtitle: str | None = None,
    badge_text: str | None = None,
    badge_variant: str = "info",
    show_privacy_toggle: bool = True,
) -> None:
    """Affiche un en-tête de page standardisé avec bouton badge de confidentialité persistant."""
    col_t, col_b = st.columns([0.72, 0.28])
    with col_t:
        st.title(title)
        if subtitle:
            st.caption(subtitle)
    with col_b:
        if badge_text:
            # Sécurisation : validation allowlist + échappement HTML strict
            variant = (
                badge_variant.lower()
                if badge_variant.lower() in _ALLOWED_BADGE_VARIANTS
                else "info"
            )
            safe_text = html.escape(str(badge_text), quote=True)
            st.markdown(
                f'<div style="text-align: right; padding-top: 1rem;"><span class="badge-pill badge-{variant}">{safe_text}</span></div>',
                unsafe_allow_html=True,
            )
        elif show_privacy_toggle:
            is_active = bool(st.session_state.get(SESSION_KEY_PRIVACY, False))

            def _toggle_privacy() -> None:
                st.session_state[SESSION_KEY_PRIVACY] = not bool(
                    st.session_state.get(SESSION_KEY_PRIVACY, False)
                )

            label = "🛡️ MODE PRIVÉ ACTIF" if is_active else "🔓 DONNÉES VISIBLES"
            bg_color = "#059669" if is_active else "#DC2626"
            border_color = "#10B981" if is_active else "#EF4444"
            help_text = (
                "Mode privé activé : données sensibles masquées. Cliquez pour désactiver."
                if is_active
                else "Données visibles. Cliquez pour activer le masquage des données sensibles."
            )

            st_yled.button(
                label,
                key="_header_privacy_btn",
                background_color=bg_color,
                color="#FFFFFF",
                border_color=border_color,
                border_radius="9999px",
                padding="4px 14px",
                font_weight="700",
                on_click=_toggle_privacy,
                help=help_text,
                use_container_width=False,
            )
        elif is_privacy_enabled():
            st.markdown(
                '<div style="text-align: right; padding-top: 1rem;"><span class="badge-pill badge-warning">🔒 Mode confidentiel</span></div>',
                unsafe_allow_html=True,
            )


def apply_plotly_theme(fig: go.Figure) -> go.Figure:
    """Harmonise un graphique Plotly avec le thème sombre Slate de l'application."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(30, 41, 59, 0.5)",
        font=dict(family="sans-serif", color="#F8FAFC", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)",
            bordercolor="#334155",
            borderwidth=1,
        ),
        xaxis=dict(gridcolor="#334155", zerolinecolor="#475569"),
        yaxis=dict(gridcolor="#334155", zerolinecolor="#475569"),
    )
    return fig
