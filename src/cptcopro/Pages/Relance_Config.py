"""Configuration des relances email (fréquence, messagerie Hotmail/IMAP, LLM Mistral)."""

from __future__ import annotations

import os
from typing import Any, cast

import streamlit as st

from cptcopro.Database import (
    DEFAULT_RELANCE_CONFIG,
    get_relance_config,
    init_relance_config_if_missing,
    update_relance_config,
)
from cptcopro.utils.hotmail_oauth import (
    demarrer_device_flow_microsoft,
    valider_device_flow_microsoft,
    verifier_statut_token_hotmail,
)
from cptcopro.utils.paths import init_env
from cptcopro.utils.relance_mailer import (
    tester_connexion_imap,
    tester_connexion_mistral,
)
from cptcopro.utils.ui_components import render_header

init_env()


@st.cache_data(ttl=120, show_spinner=False)
def _load_relance_config() -> dict[str, Any]:
    init_relance_config_if_missing()
    return cast(dict[str, Any], get_relance_config())


render_header(
    "⚙️ Configuration des Relances & IA",
    "Paramètres du serveur IMAP Hotmail/Outlook (OAuth2), fréquence et modèle Mistral AI",
)

cfg = _load_relance_config()

enabled = bool(int(cfg.get("enabled", 1)))
frequency_days = int(cfg.get("frequency_days", 14) or 14)

tab_rules, tab_mailbox, tab_llm = st.tabs(
    [
        "📋 Règles de relance",
        "📬 Boîte mail & OAuth2 (Hotmail)",
        "🤖 Modèle IA (Mistral)",
    ]
)

# ============================================================================
# ONGLET 1: RÈGLES DE RELANCE
# ============================================================================
with tab_rules:
    st.subheader("Paramètres de fréquence et signature")

    with st.form("relance_rules_form"):
        enabled_new = st.toggle(
            "Activer la génération de relances",
            value=enabled,
            help="Si désactivé, la page Relance reste consultable mais ne génère pas de brouillons.",
        )
        frequency_new = st.number_input(
            "Délai minimal entre deux relances pour un même copropriétaire (en jours)",
            min_value=1,
            max_value=365,
            value=frequency_days,
            step=1,
        )

        col_exp1, col_exp2 = st.columns(2, gap="medium")
        with col_exp1:
            sender_name_new = st.text_input(
                "Nom de l'expéditeur (signature)",
                value=str(cfg.get("sender_name") or DEFAULT_RELANCE_CONFIG["sender_name"]),
            )
        with col_exp2:
            sender_email_new = st.text_input(
                "Email de l'expéditeur",
                value=str(cfg.get("sender_email") or ""),
                help="Adresse email utilisée pour signer les courriers.",
            )

        submitted_rules = st.form_submit_button(
            "💾 Enregistrer les règles", type="primary", use_container_width=True
        )
        if submitted_rules:
            update_relance_config(
                enabled=1 if enabled_new else 0,
                frequency_days=int(frequency_new),
                sender_name=sender_name_new.strip(),
                sender_email=sender_email_new.strip(),
            )
            _load_relance_config.clear()
            st.toast("Règles de relance enregistrées !", icon="💾")
            st.rerun()


# ============================================================================
# ONGLET 2: BOÎTE MAIL HOTMAIL & OAUTH2
# ============================================================================
with tab_mailbox:
    st.subheader("Connexion Hotmail / Outlook (Dépôt IMAP)")

    is_oauth_valid, oauth_status_msg = verifier_statut_token_hotmail(cfg)
    if is_oauth_valid:
        st.success(f"✅ **OAuth2 Hotmail actif** : {oauth_status_msg}")
    else:
        st.warning(f"⚠️ **OAuth2 Hotmail** : {oauth_status_msg}")

    with st.expander("🔑 Autorisation Microsoft (Device Code)", expanded=not is_oauth_valid):
        st.caption(
            "Pour déposer des brouillons dans votre compte Hotmail sans mot de passe, "
            "autorisez l'application via le protocole Device Code de Microsoft."
        )

        if "ms_device_flow" not in st.session_state:
            st.session_state.ms_device_flow = None

        col_auth1, _ = st.columns([1.5, 2])
        with col_auth1:
            if st.button(
                "🔑 Démarrer l'autorisation Microsoft", type="primary", use_container_width=True
            ):
                try:
                    flow = demarrer_device_flow_microsoft(cfg)
                    st.session_state.ms_device_flow = flow
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erreur d'initialisation : {exc}")

        if st.session_state.ms_device_flow:
            flow = st.session_state.ms_device_flow
            user_code = flow.get("user_code", "")
            verification_uri = flow.get("verification_uri", "https://microsoft.com/devicelogin")

            st.info(f"1. Copiez ce code : **`{user_code}`**")
            st.markdown(
                f"2. Ouvrez le lien : **[{verification_uri}]({verification_uri})** et collez le code."
            )
            st.caption("3. Une fois l'autorisation accordée, cliquez sur Valider :")

            col_val1, col_val2 = st.columns(2, gap="medium")
            with col_val1:
                if st.button(
                    "✓ Valider et enregistrer le jeton", type="primary", use_container_width=True
                ):
                    with st.spinner("Validation en cours..."):
                        success, msg = valider_device_flow_microsoft(flow, cfg)
                        if success:
                            st.toast("Jeton OAuth2 enregistré !", icon="✅")
                            st.session_state.ms_device_flow = None
                            _load_relance_config.clear()
                            st.rerun()
                        else:
                            st.error(msg)
            with col_val2:
                if st.button("Annuler", use_container_width=True):
                    st.session_state.ms_device_flow = None
                    st.rerun()

    with st.form("relance_imap_form"):
        col_m1, col_m2 = st.columns(2, gap="medium")
        with col_m1:
            mailbox_imap_host = st.text_input(
                "Serveur IMAP",
                value=str(cfg.get("mailbox_imap_host") or "outlook.office365.com"),
            )
            mailbox_imap_user = st.text_input(
                "Compte Hotmail / Outlook",
                value=str(cfg.get("mailbox_imap_user") or ""),
            )
        with col_m2:
            mailbox_imap_port = st.number_input(
                "Port IMAP",
                min_value=1,
                max_value=65535,
                value=int(cfg.get("mailbox_imap_port", 993) or 993),
                step=1,
            )
            mailbox_drafts_folder = st.text_input(
                "Dossier des brouillons",
                value=str(cfg.get("mailbox_drafts_folder") or "Drafts"),
                help="Nom du dossier IMAP cible (ex: Drafts ou Brouillons).",
            )

        mailbox_use_ssl = st.checkbox(
            "Activer SSL",
            value=bool(int(cfg.get("mailbox_use_ssl", 1) or 1)),
        )

        submitted_imap = st.form_submit_button(
            "💾 Enregistrer la configuration IMAP", type="primary", use_container_width=True
        )
        if submitted_imap:
            update_relance_config(
                mailbox_imap_host=mailbox_imap_host.strip(),
                mailbox_imap_port=int(mailbox_imap_port),
                mailbox_imap_user=mailbox_imap_user.strip(),
                mailbox_drafts_folder=mailbox_drafts_folder.strip() or "Drafts",
                mailbox_use_ssl=1 if mailbox_use_ssl else 0,
            )
            _load_relance_config.clear()
            st.toast("Configuration IMAP sauvegardée !", icon="💾")
            st.rerun()

    col_test_imap, _ = st.columns([1.5, 2])
    with col_test_imap:
        if st.button("📡 Tester la connexion IMAP", use_container_width=True):
            with st.spinner("Test de connexion IMAP..."):
                ok, message_imap, dossiers = tester_connexion_imap(cfg)
                if ok:
                    st.success(f"✅ {message_imap}")
                else:
                    st.error(f"❌ {message_imap}")


# ============================================================================
# ONGLET 3: MISTRAL IA
# ============================================================================
with tab_llm:
    st.subheader("Configuration du modèle d'Intelligence Artificielle")

    with st.form("relance_llm_form"):
        col_l1, col_l2 = st.columns(2, gap="medium")
        with col_l1:
            llm_provider = st.selectbox(
                "Fournisseur LLM",
                options=["mistral", "fallback"],
                index=0 if str(cfg.get("llm_provider") or "mistral") == "mistral" else 1,
            )
            llm_api_base = st.text_input(
                "URL Base API",
                value=str(cfg.get("llm_api_base") or "https://api.mistral.ai/v1"),
            )
        with col_l2:
            llm_model = st.text_input(
                "Modèle",
                value=str(cfg.get("llm_model") or "mistral-small-latest"),
            )
            llm_temperature = st.slider(
                "Température (créativité)",
                min_value=0.0,
                max_value=1.0,
                value=float(cfg.get("llm_temperature", 0.4) or 0.4),
                step=0.05,
            )

        tone_instruction = st.text_area(
            "Consigne générale de ton",
            value=str(cfg.get("tone_instruction") or "courtois, professionnel et ferme"),
            height=80,
        )

        submitted_llm = st.form_submit_button(
            "💾 Enregistrer la configuration IA", type="primary", use_container_width=True
        )
        if submitted_llm:
            update_relance_config(
                llm_provider=llm_provider,
                llm_model=llm_model.strip(),
                llm_api_base=llm_api_base.strip(),
                llm_temperature=float(llm_temperature),
                tone_instruction=tone_instruction.strip() or "courtois, professionnel et ferme",
            )
            _load_relance_config.clear()
            st.toast("Configuration IA enregistrée !", icon="🤖")
            st.rerun()

    col_mistral, _ = st.columns([1.5, 2])
    with col_mistral:
        if st.button("🧪 Tester l'API Mistral", use_container_width=True):
            with st.spinner("Test de communication avec Mistral AI..."):
                key_var = str(cfg.get("llm_api_key_env") or "MISTRAL_API_KEY")
                api_k = os.getenv(key_var)
                model_name = str(cfg.get("llm_model") or "mistral-small-latest")
                api_b = str(cfg.get("llm_api_base") or "https://api.mistral.ai/v1")
                ok_mistral, msg_mistral = tester_connexion_mistral(
                    api_k, model=model_name, api_base=api_b
                )
                if ok_mistral:
                    st.success(f"✅ {msg_mistral}")
                else:
                    st.error(f"❌ {msg_mistral}")
