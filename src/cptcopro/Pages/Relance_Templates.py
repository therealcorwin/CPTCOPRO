"""Gestion des modèles d'email de relance (création, édition, aperçu)."""

from __future__ import annotations

import streamlit as st

from cptcopro.utils.paths import get_db_path
from cptcopro.Database import (
    TEMPLATE_PLACEHOLDERS,
    GENERATION_MODES,
    list_relance_templates,
    create_relance_template,
    update_relance_template,
    delete_relance_template,
    get_relance_config,
)
from cptcopro.utils.relance_mailer import render_relance_template
from cptcopro.utils.ui_components import render_header


DB_PATH = get_db_path()

_MODE_LABELS = {
    "static": "Statique (substitution directe des variables)",
    "llm": "Assistant IA Mistral (guide de contexte et de ton)",
}

_SAMPLE_DATA = {
    "nom_proprietaire": "M. Dupont Jean",
    "code_proprietaire": "D001",
    "debit": 1234.56,
    "num_apt": "12",
    "type_apt": "3p",
    "date_origin": "2026-07-01",
}


def _db_cache_key() -> int:
    try:
        return DB_PATH.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=60, show_spinner=False)
def _load_templates(db_path: str, cache_key: int) -> list[dict]:
    del cache_key
    return list_relance_templates(db_path)


@st.cache_data(ttl=120, show_spinner=False)
def _load_config(db_path: str) -> dict:
    return get_relance_config(db_path)


render_header(
    "📝 Modèles d'Emails de Relance",
    "Configurez les modèles types et les consignes de rédaction pour l'assistant IA",
)

db_path_str = str(DB_PATH)
cfg = _load_config(db_path_str)
templates = _load_templates(db_path_str, _db_cache_key())

with st.expander("ℹ️ Variables dynamiques disponibles", expanded=False):
    st.markdown("Vous pouvez insérer ces variables dans le sujet et le corps de vos messages :")
    chips = [f"`{{{p}}}`" for p in TEMPLATE_PLACEHOLDERS]
    st.markdown(" ".join(chips))
    st.caption("Exemple : `{nom_proprietaire}`, `{debit_fmt}`, `{num_apt}`, `{date_origin}`, `{sender_name}`.")

st.divider()

_NEW_TEMPLATE_KEY = "__new__"

if not templates:
    template_labels = {_NEW_TEMPLATE_KEY: "➕ Créer un nouveau modèle"}
    selected_id = _NEW_TEMPLATE_KEY
else:
    template_labels = {
        t["template_id"]: f"📄 {t['name']}" + (" (⭐ Par défaut)" if t["is_default"] else "")
        for t in templates
    }
    template_labels[_NEW_TEMPLATE_KEY] = "➕ Créer un nouveau modèle"
    selected_id = st.selectbox(
        "Sélectionnez un modèle à éditer :",
        options=list(template_labels.keys()),
        format_func=lambda tid: template_labels[tid],
        key="template_select",
    )

is_new = selected_id == _NEW_TEMPLATE_KEY
selected_template = (
    {}
    if is_new
    else next(t for t in templates if t["template_id"] == selected_id)
)

col_form, col_prev = st.columns([1.2, 1], gap="large")

with col_form:
    st.markdown(f"### {'Nouveau Modèle' if is_new else 'Édition du Modèle'}")

    with st.form("edit_template_form"):
        name = st.text_input("Nom du modèle", value=selected_template.get("name", ""))
        generation_mode = st.radio(
            "Mode de rédaction",
            options=list(GENERATION_MODES),
            format_func=lambda m: _MODE_LABELS.get(m, m),
            index=list(GENERATION_MODES).index(selected_template.get("generation_mode") or "static"),
            horizontal=True,
            key="edit_template_mode",
        )
        subject_template = st.text_input(
            "Objet du message",
            value=selected_template.get(
                "subject_template", "Relance charges copropriété - {nom_proprietaire} ({date_origin})"
            ),
        )
        body_template = st.text_area(
            "Corps du message",
            value=selected_template.get(
                "body_template",
                (
                    "Bonjour {nom_proprietaire},\n\n"
                    "À la date du {date_origin}, un solde débiteur de {debit_fmt} est constaté "
                    "sur votre lot {num_apt} ({type_apt}).\n\n"
                    "Nous vous remercions de bien vouloir régulariser cette situation.\n\n"
                    "Cordialement,\n"
                    "{sender_name}"
                ),
            ),
            height=260,
        )
        tone_instruction = st.text_input(
            "Consigne de ton (utilisé par l'IA)",
            value=str(selected_template.get("tone_instruction") or "courtois, professionnel et ferme"),
            help="Guide le style du modèle lors de la rédaction avec l'IA Mistral.",
        )
        is_default = st.checkbox(
            "Définir comme modèle par défaut",
            value=bool(selected_template.get("is_default")),
        )

        col_b1, col_b2 = st.columns(2, gap="medium")
        with col_b1:
            submitted = st.form_submit_button(
                "✨ Créer le modèle" if is_new else "💾 Enregistrer", type="primary", use_container_width=True
            )
        with col_b2:
            deleted = st.form_submit_button("🗑️ Supprimer", type="secondary", disabled=is_new, use_container_width=True)

        if submitted:
            try:
                if is_new:
                    create_relance_template(
                        db_path_str,
                        name=name,
                        subject_template=subject_template,
                        body_template=body_template,
                        generation_mode=generation_mode,
                        tone_instruction=tone_instruction,
                        is_default=is_default,
                    )
                    st.toast("Modèle créé avec succès !", icon="✨")
                else:
                    update_relance_template(
                        db_path_str,
                        template_id=selected_id,
                        name=name.strip(),
                        subject_template=subject_template,
                        body_template=body_template,
                        generation_mode=generation_mode,
                        tone_instruction=tone_instruction,
                        is_default=is_default,
                    )
                    st.toast("Modèle mis à jour !", icon="💾")
                _load_templates.clear()
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        if deleted and not is_new:
            try:
                delete_relance_template(db_path_str, selected_id)
                _load_templates.clear()
                st.toast("Modèle supprimé", icon="🗑️")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

with col_prev:
    st.markdown("### 👁️ Aperçu du rendu")
    mode_actuel = selected_template.get("generation_mode") or generation_mode
    if mode_actuel == "llm":
        st.info("🤖 **Mode Assistant IA** : Le texte ci-dessous servira de guide thématique à Mistral pour générer un message fluide et personnalisé.")
    else:
        st.caption("Exemple avec un copropriétaire fictif :")

    try:
        dummy_tpl = {
            "subject_template": subject_template,
            "body_template": body_template,
        }
        preview_sub, preview_txt = render_relance_template(dummy_tpl, _SAMPLE_DATA, cfg)
        st.text_input("Objet généré", value=preview_sub, disabled=True)
        st.text_area("Corps généré", value=preview_txt, height=260, disabled=True)
    except Exception as exc:
        st.warning(f"Aperçu indisponible : {exc}")
