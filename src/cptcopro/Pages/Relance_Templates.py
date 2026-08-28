"""Gestion des templates d'email de relance (creation, edition, apercu)."""

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


DB_PATH = get_db_path()

_MODE_LABELS = {
    "static": "Statique (substitution directe des placeholders)",
    "llm": "Assistant IA (le sujet/corps servent de guide de contenu et de ton)",
}

_SAMPLE_DATA = {
    "nom_proprietaire": "Dupont Jean",
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


st.title("Templates de Relance")
st.caption(
    "Creez et parametrez les modeles d'email utilises pour generer les brouillons de relance."
)

db_path_str = str(DB_PATH)
cfg = _load_config(db_path_str)
templates = _load_templates(db_path_str, _db_cache_key())

st.subheader("Placeholders disponibles")
st.code(", ".join("{" + p + "}" for p in TEMPLATE_PLACEHOLDERS), language=None)
st.caption(
    "Utilisez ces placeholders dans le sujet et le corps du template. "
    "Ils seront remplaces par les donnees reelles du coproprietaire lors de la generation."
)

st.divider()
st.subheader("Templates existants")

_NEW_TEMPLATE_KEY = "__new__"

if not templates:
    template_labels = {_NEW_TEMPLATE_KEY: "Nouveau template"}
    selected_id = _NEW_TEMPLATE_KEY
else:
    template_labels = {
        t["template_id"]: f"{t['name']}" + (" (par defaut)" if t["is_default"] else "")
        for t in templates
    }
    template_labels[_NEW_TEMPLATE_KEY] = "Nouveau template"
    selected_id = st.selectbox(
        "Selectionner un template a consulter/editer, ou creer un nouveau",
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

with st.form("edit_template_form"):
    name = st.text_input("Nom du template", value=selected_template.get("name", ""))
    generation_mode = st.radio(
        "Mode de generation",
        options=list(GENERATION_MODES),
        format_func=lambda m: _MODE_LABELS.get(m, m),
        index=list(GENERATION_MODES).index(selected_template.get("generation_mode") or "static"),
        horizontal=True,
        key="edit_template_mode",
    )
    subject_template = st.text_input(
        "Sujet",
        value=selected_template.get(
            "subject_template", "Relance charges copropriete - {nom_proprietaire} ({date_origin})"
        ),
    )
    body_template = st.text_area(
        "Corps",
        value=selected_template.get(
            "body_template",
            (
                "Bonjour {nom_proprietaire},\n\n"
                "A la date du {date_origin}, un solde debiteur de {debit_fmt} est constate "
                "sur votre lot {num_apt} ({type_apt}).\n\n"
                "Cordialement,\n"
                "{sender_name}"
            ),
        ),
        height=280,
    )
    tone_instruction = st.text_input(
        "Ton a appliquer",
        value=str(selected_template.get("tone_instruction") or "courtois, professionnel et ferme"),
        help="Utilise pour guider le ton du message, notamment en mode assistant IA.",
    )
    is_default = st.checkbox(
        "Definir comme template par defaut",
        value=bool(selected_template.get("is_default")),
    )

    col1, col2 = st.columns(2)
    with col1:
        submitted = st.form_submit_button(
            "Creer le template" if is_new else "Enregistrer", type="primary"
        )
    with col2:
        deleted = st.form_submit_button("Supprimer", type="secondary", disabled=is_new)

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
                st.success("Template cree.")
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
                st.success("Template mis a jour.")
            _load_templates.clear()
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    if deleted and not is_new:
        try:
            delete_relance_template(db_path_str, selected_id)
            _load_templates.clear()
            st.success("Template supprime.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

if not is_new:
    st.markdown("**Apercu avec donnees d'exemple**")
    if (selected_template.get("generation_mode") or "static") == "llm":
        st.caption(
            "Mode assistant IA: le contenu final sera redige par l'IA en suivant ce guide et ce ton, "
            "il ne sera pas recopie tel quel."
        )
    try:
        preview_subject, preview_body = render_relance_template(
            selected_template, _SAMPLE_DATA, cfg
        )
        st.text_input("Sujet genere", value=preview_subject, disabled=True)
        st.text_area("Corps genere", value=preview_body, height=200, disabled=True)
    except Exception as exc:
        st.warning(f"Impossible de generer l'apercu: {exc}")

