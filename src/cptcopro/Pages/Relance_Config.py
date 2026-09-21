"""Configuration globale des relances : modèles types, fréquence, messagerie IMAP Hotmail et IA Mistral."""

from __future__ import annotations

import os
from typing import Any, cast

import streamlit as st

from cptcopro.Database import (
    DEFAULT_RELANCE_CONFIG,
    GENERATION_MODES,
    create_relance_snippet,
    create_relance_template,
    create_relance_variable,
    delete_relance_snippet,
    delete_relance_template,
    delete_relance_variable,
    get_all_template_placeholders,
    get_relance_config,
    init_relance_config_if_missing,
    init_relance_snippets_if_missing,
    list_relance_snippets,
    list_relance_templates,
    list_relance_variables,
    reset_default_relance_snippets,
    update_relance_config,
    update_relance_snippet,
    update_relance_template,
    update_relance_variable,
)
from cptcopro.utils.hotmail_oauth import (
    demarrer_device_flow_microsoft,
    valider_device_flow_microsoft,
    verifier_statut_token_hotmail,
)
from cptcopro.utils.paths import init_env
from cptcopro.utils.relance_mailer import (
    generer_corps_template_avec_mistral,
    render_relance_template,
    tester_connexion_imap,
    tester_connexion_mistral,
)
from cptcopro.utils.ui_components import render_header

init_env()

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
    "date_origin": "01/07/2026",
    "date_du_jour": "19/09/2026",
    "today": "19/09/2026",
    "contact_name": "M. Dupont",
    "type_alerte": "Débit élevé",
    "last_relance_date": "05/09/2026",
    "nb_relances_total": 1,
}


def _insert_into_body(tag: str) -> None:
    curr = str(st.session_state.get("tpl_edit_body", ""))
    if curr and not curr.endswith((" ", "\n")):
        st.session_state["tpl_edit_body"] = f"{curr} {tag}"
    else:
        st.session_state["tpl_edit_body"] = f"{curr}{tag}"
    st.toast(f"Balise {tag} ajoutée au corps !", icon="✨")
    st.rerun()


def _insert_into_subject(tag: str) -> None:
    curr = str(st.session_state.get("tpl_edit_subject", ""))
    if curr and not curr.endswith(" "):
        st.session_state["tpl_edit_subject"] = f"{curr} {tag}"
    else:
        st.session_state["tpl_edit_subject"] = f"{curr}{tag}"
    st.toast(f"Balise {tag} ajoutée à l'objet !", icon="✨")
    st.rerun()


def _insert_snippet_into_body(snippet: str) -> None:
    curr = str(st.session_state.get("tpl_edit_body", "")).rstrip()
    if curr:
        st.session_state["tpl_edit_body"] = f"{curr}\n\n{snippet}\n"
    else:
        st.session_state["tpl_edit_body"] = f"{snippet}\n"
    st.toast("Paragraphe type inséré dans le corps !", icon="📝")
    st.rerun()


@st.cache_data(ttl=120, show_spinner=False)
def _load_relance_config() -> dict[str, Any]:
    init_relance_config_if_missing()
    return cast(dict[str, Any], get_relance_config())


@st.cache_data(ttl=60, show_spinner=False)
def _load_templates() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], list_relance_templates())


@st.cache_data(ttl=60, show_spinner=False)
def _load_custom_variables() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], list_relance_variables())


@st.cache_data(ttl=60, show_spinner=False)
def _load_snippets() -> list[dict[str, Any]]:
    init_relance_snippets_if_missing()
    return cast(list[dict[str, Any]], list_relance_snippets())


render_header(
    "⚙️ Configuration & Modèles de Relance",
    "Gestion des modèles types, règles d'envoi, variables personnalisées, messagerie IMAP Hotmail et IA",
)

cfg = _load_relance_config()
templates = _load_templates()
custom_variables = _load_custom_variables()
snippets = _load_snippets()

enabled = bool(int(cfg.get("enabled", 1)))
frequency_days = int(cfg.get("frequency_days", 14) or 14)

tab_modeles, tab_rules, tab_integrations = st.tabs(
    [
        "📝 Modèles & Contenu",
        "📋 Règles & Fréquence",
        "🔧 Intégrations",
    ]
)


# ============================================================================
# ONGLET 1 : MODÈLES & CONTENU
# Regroupe : éditeur de modèles + snippets (expander) + variables (expander)
# ============================================================================
with tab_modeles:

    # --- Éditeur de modèle ---
    st.subheader("Modèles de courriers de relance")

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
        {} if is_new else next(t for t in templates if t["template_id"] == selected_id)
    )

    # Synchronisation de l'état du formulaire avec le modèle sélectionné
    if st.session_state.get("last_template_edit_id") != selected_id:
        st.session_state["last_template_edit_id"] = selected_id
        st.session_state["tpl_edit_name"] = "" if is_new else str(selected_template.get("name") or "")
        st.session_state["tpl_edit_mode"] = (
            "static" if is_new else str(selected_template.get("generation_mode") or "static")
        )
        st.session_state["tpl_edit_default"] = (
            False if is_new else bool(selected_template.get("is_default", False))
        )
        st.session_state["tpl_edit_subject"] = (
            "Rappel : Régularisation de vos charges"
            if is_new
            else str(selected_template.get("subject_template") or selected_template.get("subject") or "")
        )
        st.session_state["tpl_edit_body"] = (
            ""
            if is_new
            else str(selected_template.get("body_template") or selected_template.get("body") or "")
        )
        st.session_state["tpl_edit_prompt"] = (
            ""
            if is_new
            else str(selected_template.get("tone_instruction") or selected_template.get("prompt_instructions") or "")
        )

    # Résolution du corps généré par Mistral (clé tampon, appliquée avant l'instanciation du widget)
    if "_pending_generated_body" in st.session_state:
        st.session_state["tpl_edit_body"] = st.session_state.pop("_pending_generated_body")

    tpl_title = "➕ Nouveau Modèle" if is_new else f"✏️ Édition : {selected_template.get('name', '')}"
    st.markdown(f"### {tpl_title}")

    # Métadonnées du modèle (nom, mode, défaut)
    col_name, col_mode, col_def, _ = st.columns([1.3, 2.0, 1.2, 1.5], gap="medium")
    with col_name:
        st.text_input("Nom du modèle", key="tpl_edit_name")
    with col_mode:
        st.radio(
            "Mode de rédaction",
            options=list(GENERATION_MODES),
            format_func=lambda m: _MODE_LABELS.get(m, m),
            key="tpl_edit_mode",
            horizontal=True,
        )
    with col_def:
        st.write("")
        st.write("")
        st.checkbox("⭐ Modèle par défaut", key="tpl_edit_default")

    all_placeholders = get_all_template_placeholders()
    snip_content_map = {s["snippet_id"]: s["content"] for s in snippets}

    # ── Objet — pleine largeur ─────────────────────────────────────────────
    st.markdown("##### ✉️ Objet")
    st.text_input(
        "Objet",
        key="tpl_edit_subject",
        label_visibility="collapsed",
        placeholder="Ex : Rappel règlement charges — {nom_proprietaire}",
    )

    # ── Barre d'insertion compacte — 1 ligne horizontale ──────────────────
    with st.container(border=True):
        all_var_names = [p["name"] for p in all_placeholders]
        var_label_map = {
            p["name"]: f"{p.get('category','').split()[0] if p.get('category') else ''} · {{{p['name']}}}"
            for p in all_placeholders
        }
        snip_options = {s["snippet_id"]: s["title"] for s in snippets}

        bar_c0, bar_c1, bar_c2, bar_c3, bar_c4, bar_c5 = st.columns(
            [1.1, 0.7, 2.8, 0.65, 2.4, 0.65], gap="small"
        )

        with bar_c0:
            st.caption("Insérer dans :")
            insert_target = st.radio(
                "cible",
                options=["✉️ Objet", "📄 Corps"],
                index=1,
                key="palette_insert_target",
                label_visibility="collapsed",
            )
        is_target_subject = insert_target == "✉️ Objet"

        def _palette_insert(tag: str) -> None:
            if is_target_subject:
                _insert_into_subject(tag)
            else:
                _insert_into_body(tag)

        with bar_c1:
            st.caption("Variable")
        with bar_c2:
            chosen_var = st.selectbox(
                "Variable",
                options=all_var_names,
                format_func=lambda n: var_label_map.get(n, f"{{{n}}}"),
                key="sel_any_var",
                label_visibility="collapsed",
            )
        with bar_c3:
            st.write("")
            if st.button("➕", key="btn_ins_var", width="stretch",
                         help=f"Insérer {{{chosen_var}}}"):
                _palette_insert(f"{{{chosen_var}}}")

        with bar_c4:
            if snip_options:
                chosen_snippet_id = st.selectbox(
                    "Bloc type",
                    options=list(snip_options.keys()),
                    format_func=lambda sid: f"📋 {snip_options.get(sid, '')}",
                    key="sel_snippet",
                    label_visibility="collapsed",
                )
            else:
                chosen_snippet_id = None
                st.caption("*(Aucun bloc type)*")

        with bar_c5:
            has_snip = bool(chosen_snippet_id and chosen_snippet_id in snip_content_map)
            st.write("")
            if st.button("📝", key="btn_ins_snip", width="stretch",
                         help="Insérer ce bloc dans le corps", disabled=not has_snip):
                if has_snip and chosen_snippet_id is not None:
                    _insert_snippet_into_body(snip_content_map[chosen_snippet_id])

    # ── Corps — pleine largeur ─────────────────────────────────────────────
    st.markdown("##### 📄 Corps du message")
    st.text_area(
        "Corps de l'email",
        key="tpl_edit_body",
        height=340,
        label_visibility="collapsed",
        placeholder="Rédigez votre modèle ici.\nSélectionnez une variable ci-dessus et cliquez ➕ pour l'insérer.",
    )

    st.markdown("##### 🤖 Consignes IA *(optionnel)*")
    st.text_area(
        "Consignes IA",
        key="tpl_edit_prompt",
        height=75,
        help="Instructions fournies à Mistral si ce modèle est sélectionné en mode IA.",
        label_visibility="collapsed",
        placeholder="Ex : Adoptez un ton courtois mais ferme…",
    )

    # ── Génération IA du corps ─────────────────────────────────────────────
    col_gen, col_gen_info = st.columns([1.6, 3], gap="small")
    with col_gen:
        if st.button(
            "🤖 Générer le corps avec Mistral",
            width="stretch",
            help=(
                "Demande à Mistral de rédiger un corps de modèle type basé sur "
                "le nom du modèle et les consignes IA saisies ci-dessus. "
                "Le résultat remplace le contenu actuel du Corps."
            ),
        ):
            _nm = str(st.session_state.get("tpl_edit_name") or "").strip()
            _pr = str(st.session_state.get("tpl_edit_prompt") or "").strip()
            _bd = str(st.session_state.get("tpl_edit_body") or "").strip()
            if not _nm:
                st.warning("⚠️ Renseignez d'abord le **nom du modèle** pour guider la génération.")
            else:
                with st.spinner(f"Mistral rédige le modèle « {_nm} »…"):
                    _generated, _model_used, _err = generer_corps_template_avec_mistral(
                        nom_modele=_nm,
                        tone_instruction=_pr,
                        corps_existant=_bd,
                        config=cfg,
                    )
                if _err:
                    st.error(f"❌ {_err}")
                elif _generated:
                    # Clé tampon : appliquée avant l'instanciation du widget au run suivant
                    st.session_state["_pending_generated_body"] = _generated
                    st.toast(f"Corps généré par Mistral ({_model_used}) !", icon="🤖")
                    st.rerun()
    with col_gen_info:
        st.caption(
            "💡 Mistral génère un corps complet avec les placeholders `{nom_proprietaire}`, "
            "`{debit_fmt}`, `{num_apt}`… en tenant compte du nom du modèle et de vos consignes IA."
        )


    st.write("")
    col_act_save, col_act_del, col_act_rst, _ = st.columns([2, 1.2, 1.2, 3], gap="small")
    with col_act_save:
        if st.button("💾 Enregistrer le modèle", type="primary", width="stretch"):
            nm = str(st.session_state.get("tpl_edit_name") or "").strip()
            sb = str(st.session_state.get("tpl_edit_subject") or "").strip()
            bd = str(st.session_state.get("tpl_edit_body") or "").strip()
            gm = str(st.session_state.get("tpl_edit_mode") or "static")
            df = bool(st.session_state.get("tpl_edit_default", False))
            pr = str(st.session_state.get("tpl_edit_prompt") or "").strip()

            if not nm:
                st.error("Le nom du modèle est obligatoire.")
            elif not sb:
                st.error("L'objet de l'email est obligatoire.")
            elif not bd:
                st.error("Le corps de l'email ne peut pas être vide.")
            elif is_new:
                create_relance_template(
                    name=nm,
                    subject_template=sb,
                    body_template=bd,
                    generation_mode=gm,
                    is_default=df,
                    tone_instruction=pr,
                )
                _load_templates.clear()
                st.session_state.last_template_edit_id = None
                st.toast("Modèle créé avec succès !", icon="✅")
                st.rerun()
            else:
                update_relance_template(
                    selected_id,
                    name=nm,
                    subject_template=sb,
                    body_template=bd,
                    generation_mode=gm,
                    is_default=df,
                    tone_instruction=pr,
                )
                _load_templates.clear()
                st.toast("Modèle mis à jour !", icon="💾")
                st.rerun()

    with col_act_del:
        can_delete = not is_new and not selected_template.get("is_default", False)
        if st.button("🗑️ Supprimer", disabled=not can_delete, width="stretch"):
            delete_relance_template(selected_id)
            _load_templates.clear()
            st.session_state.last_template_edit_id = None
            st.toast("Modèle supprimé.", icon="🗑️")
            st.rerun()

    with col_act_rst:
        if st.button("🔄 Réinitialiser", width="stretch",
                     help="Annule les modifications non enregistrées"):
            st.session_state.last_template_edit_id = None
            st.rerun()

    # Aperçu en temps réel
    st.divider()
    st.markdown("### 👁️ Aperçu du rendu en temps réel")
    st.caption("Simulation du courrier avec des données d'exemple réalistes (mise à jour automatique à chaque modification) :")

    tpl_preview = {
        "subject_template": str(st.session_state.get("tpl_edit_subject") or ""),
        "body_template": str(st.session_state.get("tpl_edit_body") or ""),
    }
    subj_rendu, body_rendu = render_relance_template(tpl_preview, _SAMPLE_DATA, cfg)

    with st.container(border=True):
        st.markdown(f"**✉️ Objet généré :** `{subj_rendu}`")
        st.caption("📄 Corps de l'email généré :")
        st.text_area(
            "Aperçu du corps",
            value=body_rendu,
            height=320,
            disabled=True,
            label_visibility="collapsed",
        )

    # -------------------------------------------------------------------------
    # Sous-section : Paragraphes Types (Snippets) — expander discret
    # -------------------------------------------------------------------------
    st.divider()
    with st.expander("📑 Paragraphes Types (Snippets) — blocs de texte réutilisables", expanded=False):
        st.markdown(
            "Définissez des blocs de texte réutilisables (constats d'impayé, coordonnées bancaires, "
            "invitations au dialogue, formules de signature…) pour les insérer en un clic dans vos modèles."
        )

        edit_snip_id = st.session_state.get("relance_editing_snip_id")
        snip_to_edit = (
            next((s for s in snippets if s["snippet_id"] == edit_snip_id), None)
            if edit_snip_id is not None
            else None
        )

        if snip_to_edit:
            st.info(f"✏️ **Modification du paragraphe type :** {snip_to_edit['title']}")

        with st.form("snippet_form"):
            col_sf1, col_sf2 = st.columns([1.6, 1], gap="medium")
            with col_sf1:
                snip_title_input = st.text_input(
                    "Titre du paragraphe type",
                    value=str(snip_to_edit["title"]) if snip_to_edit else "",
                    placeholder="ex: 💳 Coordonnées bancaires & Virement",
                    help="Titre distinctif affiché dans la liste déroulante lors de la rédaction d'un modèle.",
                )
                snip_desc_input = st.text_input(
                    "Description / Usage (optionnel)",
                    value=str(snip_to_edit["description"]) if snip_to_edit else "",
                    placeholder="ex: Instructions de virement bancaire pour règlement",
                    help="Courte explication du contexte ou de l'objectif de ce bloc.",
                )
            with col_sf2:
                snip_order_input = st.number_input(
                    "Ordre d'affichage dans la liste",
                    min_value=0,
                    max_value=999,
                    value=int(snip_to_edit["sort_order"]) if snip_to_edit else 10,
                    step=5,
                    help="Les blocs avec un nombre plus petit apparaîtront en premier.",
                )

            snip_content_input = st.text_area(
                "Contenu du paragraphe",
                value=str(snip_to_edit["content"]) if snip_to_edit else "",
                placeholder="Saisissez ici le texte du bloc. Vous pouvez inclure des variables comme {nom_proprietaire}, {debit_fmt}, {iban}...",
                height=140,
                help="Ce texte sera inséré tel quel dans le corps du modèle de relance.",
            )

            col_sub_s1, col_sub_s2 = st.columns([2, 1], gap="medium")
            with col_sub_s1:
                submit_snip_label = (
                    "💾 Mettre à jour le paragraphe type"
                    if snip_to_edit
                    else "➕ Ajouter le paragraphe type"
                )
                submitted_snip = st.form_submit_button(
                    submit_snip_label, type="primary", width="stretch"
                )

            if submitted_snip:
                try:
                    if snip_to_edit:
                        update_relance_snippet(
                            int(snip_to_edit["snippet_id"]),
                            title=snip_title_input,
                            content=snip_content_input,
                            description=snip_desc_input,
                            sort_order=int(snip_order_input),
                        )
                        st.session_state.relance_editing_snip_id = None
                        _load_snippets.clear()
                        st.toast("Paragraphe type mis à jour !", icon="✅")
                        st.rerun()
                    else:
                        create_relance_snippet(
                            title=snip_title_input,
                            content=snip_content_input,
                            description=snip_desc_input,
                            sort_order=int(snip_order_input),
                        )
                        _load_snippets.clear()
                        st.toast("Paragraphe type créé avec succès !", icon="📑")
                        st.rerun()
                except ValueError as val_err:
                    st.error(f"⚠️ {val_err}")
                except Exception as exc:
                    st.error(f"❌ Erreur lors de l'enregistrement : {exc}")

        if snip_to_edit:
            if st.button("❌ Annuler la modification", key="cancel_edit_snip_btn"):
                st.session_state.relance_editing_snip_id = None
                st.rerun()

        st.divider()
        st.subheader("📋 Paragraphes types enregistrés")

        if not snippets:
            st.info(
                "💡 Aucun paragraphe type enregistré pour le moment. "
                "Remplissez le formulaire ci-dessus pour créer votre premier bloc ou cliquez ci-dessous pour restaurer les blocs standards."
            )
        else:
            for s in snippets:
                with st.container(border=True):
                    col_snip_info, col_snip_acts = st.columns([5, 1], gap="small")
                    with col_snip_info:
                        st.markdown(f"#### {s['title']}")
                        if s.get("description"):
                            st.caption(f"ℹ️ {s['description']}")
                        st.text_area(
                            "Contenu",
                            value=s["content"],
                            height=90,
                            disabled=True,
                            key=f"prev_snip_{s['snippet_id']}",
                            label_visibility="collapsed",
                        )
                    with col_snip_acts:
                        st.write("")
                        st.write("")
                        if st.button("✏️ Modifier", key=f"edit_s_{s['snippet_id']}", width="stretch"):
                            st.session_state.relance_editing_snip_id = s["snippet_id"]
                            st.rerun()
                        if st.button("🗑️ Supprimer", key=f"del_s_{s['snippet_id']}", width="stretch"):
                            delete_relance_snippet(int(s["snippet_id"]))
                            if st.session_state.get("relance_editing_snip_id") == s["snippet_id"]:
                                st.session_state.relance_editing_snip_id = None
                            _load_snippets.clear()
                            st.toast(f"Paragraphe type '{s['title']}' supprimé !", icon="🗑️")
                            st.rerun()

        st.write("")
        if st.button("🔄 Restaurer les 4 paragraphes types par défaut", help="Réinsère les blocs standards s'ils ont été supprimés"):
            inserted = reset_default_relance_snippets()
            _load_snippets.clear()
            if inserted > 0:
                st.toast(f"{inserted} paragraphe(s) par défaut restauré(s) !", icon="🔄")
            else:
                st.toast("Les paragraphes par défaut sont déjà tous présents.", icon="ℹ️")
            st.rerun()

    # -------------------------------------------------------------------------
    # Sous-section : Variables Personnalisées — expander discret
    # -------------------------------------------------------------------------
    with st.expander("🏷️ Variables Personnalisées — définissez vos propres balises dynamiques", expanded=False):
        st.markdown(
            "Définissez vos propres variables dynamiques (ex: `{iban}`, `{telephone_syndic}`, `{horaires_accueil}`) "
            "pour les insérer librement dans le sujet ou le corps de vos relances. Ces variables sont utilisables "
            "instantanément dans les **modèles types statiques** et transmises à l'**assistant IA Mistral**."
        )

        edit_var_id = st.session_state.get("relance_editing_var_id")
        var_to_edit = (
            next((v for v in custom_variables if v["var_id"] == edit_var_id), None)
            if edit_var_id is not None
            else None
        )

        if var_to_edit:
            st.info(f"✏️ **Modification de la variable :** `{{{var_to_edit['name']}}}`")

        with st.form("custom_variable_form"):
            col_vf1, col_vf2 = st.columns([1, 1], gap="medium")
            with col_vf1:
                var_name_input = st.text_input(
                    "Nom de la variable (sans accolades)",
                    value=str(var_to_edit["name"]) if var_to_edit else "",
                    placeholder="ex: iban ou telephone_syndic",
                    help="Saisissez un nom simple. Les espaces et accents sont convertis automatiquement en underscores.",
                )
                var_desc_input = st.text_input(
                    "Description / Usage (optionnel)",
                    value=str(var_to_edit["description"]) if var_to_edit else "",
                    placeholder="ex: Coordonnées bancaires pour virement direct",
                    help="Description indicative de l'usage de cette variable.",
                )
            with col_vf2:
                var_val_input = st.text_area(
                    "Valeur de remplacement",
                    value=str(var_to_edit["value"]) if var_to_edit else "",
                    placeholder="ex: FR76 3000 4000 5000 6000 7000 890",
                    height=110,
                    help="Texte exact qui viendra remplacer la variable dans vos messages.",
                )

            col_sub_v1, col_sub_v2 = st.columns([2, 1], gap="medium")
            with col_sub_v1:
                submit_btn_label = (
                    "💾 Mettre à jour la variable"
                    if var_to_edit
                    else "➕ Ajouter la variable personnalisée"
                )
                submitted_var = st.form_submit_button(
                    submit_btn_label, type="primary", width="stretch"
                )

            if submitted_var:
                try:
                    if var_to_edit:
                        update_relance_variable(
                            int(var_to_edit["var_id"]),
                            name=var_name_input,
                            value=var_val_input,
                            description=var_desc_input,
                        )
                        st.session_state.relance_editing_var_id = None
                        _load_custom_variables.clear()
                        st.toast("Variable mise à jour avec succès !", icon="✅")
                        st.rerun()
                    else:
                        create_relance_variable(
                            name=var_name_input,
                            value=var_val_input,
                            description=var_desc_input,
                        )
                        _load_custom_variables.clear()
                        st.toast("Variable créée avec succès !", icon="🏷️")
                        st.rerun()
                except ValueError as val_err:
                    st.error(f"⚠️ {val_err}")
                except Exception as exc:
                    st.error(f"❌ Erreur lors de l'enregistrement : {exc}")

        if var_to_edit:
            if st.button("❌ Annuler la modification", key="cancel_edit_var_btn"):
                st.session_state.relance_editing_var_id = None
                st.rerun()

        st.divider()
        st.subheader("📋 Vos variables personnalisées enregistrées")

        if not custom_variables:
            st.info(
                "💡 Aucune variable personnalisée active pour le moment. "
                "Remplissez le formulaire ci-dessus pour créer votre première variable (ex: `iban`, `telephone_syndic`, etc.)."
            )
        else:
            for v in custom_variables:
                c_name, c_val, c_acts = st.columns([1.5, 3, 1], gap="small")
                with c_name:
                    st.markdown(f"**`{{{v['name']}}}`**")
                    if v.get("description"):
                        st.caption(str(v["description"]))
                with c_val:
                    st.code(str(v["value"]), language=None)
                with c_acts:
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        if st.button("✏️", key=f"edit_v_{v['var_id']}", help="Modifier"):
                            st.session_state.relance_editing_var_id = v["var_id"]
                            st.rerun()
                    with col_b2:
                        if st.button("🗑️", key=f"del_v_{v['var_id']}", help="Supprimer"):
                            delete_relance_variable(int(v["var_id"]))
                            if st.session_state.get("relance_editing_var_id") == v["var_id"]:
                                st.session_state.relance_editing_var_id = None
                            _load_custom_variables.clear()
                            st.toast(f"Variable {{{v['name']}}} supprimée !", icon="🗑️")
                            st.rerun()

        st.divider()
        st.subheader("📚 Répertoire de toutes les variables disponibles")
        st.caption(
            "Vous pouvez insérer ces balises dans vos courriers (modèles et consignes de ton). "
            "Elles seront automatiquement remplacées par les données correspondantes lors de la génération."
        )

        categories: dict[str, list[dict[str, Any]]] = {}
        for p in all_placeholders:
            cat = str(p.get("category") or "Autres")
            categories.setdefault(cat, []).append(p)

        for cat_name, items in categories.items():
            with st.expander(f"📁 {cat_name} ({len(items)} variables)", expanded=False):
                for itm in items:
                    col_p1, col_p2 = st.columns([1.5, 3])
                    with col_p1:
                        st.markdown(f"**`{{{itm['name']}}}`**")
                    with col_p2:
                        st.markdown(str(itm.get("description") or "-"))


# ============================================================================
# ONGLET 2 : RÈGLES & FRÉQUENCE
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
            "💾 Enregistrer les règles", type="primary", width="stretch"
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
# ONGLET 3 : INTÉGRATIONS — Messagerie + IA Mistral
# ============================================================================
with tab_integrations:

    # -------------------------------------------------------------------------
    # Section A : Messagerie Hotmail / OAuth2 + IMAP
    # -------------------------------------------------------------------------
    st.subheader("📬 Messagerie Hotmail / Outlook")

    token_valide, message_token = verifier_statut_token_hotmail(cfg)
    col_stat1, col_stat2 = st.columns([2, 1], gap="medium")
    with col_stat1:
        if token_valide:
            st.success(f"🟢 **Connecté à Hotmail** via OAuth2 ({message_token})")
        else:
            st.warning(f"🟠 **Statut OAuth2** : {message_token}")

    with st.expander("🔑 Authentification Microsoft (Device Code Flow)", expanded=not token_valide):
        st.caption(
            "Ce protocole permet de connecter votre compte personnel Hotmail/Outlook sans stocker de mot de passe."
        )

        col_btn_auth, col_btn_check = st.columns(2, gap="medium")

        with col_btn_auth:
            if st.button("🔑 Démarrer l'authentification Microsoft", width="stretch"):
                flow = demarrer_device_flow_microsoft()
                if flow:
                    st.session_state["ms_device_flow"] = flow
                    st.info(f"👉 Rendez-vous sur : **{flow['verification_uri']}**")
                    st.code(flow["user_code"], language="text")
                    st.caption(
                        "Saisissez le code ci-dessus dans la page Microsoft, puis cliquez ci-contre pour valider."
                    )

        with col_btn_check:
            if "ms_device_flow" in st.session_state:
                if st.button(
                    "✅ Valider la connexion une fois approuvée",
                    type="primary",
                    width="stretch",
                ):
                    with st.spinner("Vérification auprès de Microsoft..."):
                        token_data = valider_device_flow_microsoft(st.session_state["ms_device_flow"])
                        if token_data:
                            st.session_state.pop("ms_device_flow", None)
                            st.toast("Compte Microsoft connecté avec succès !", icon="🟢")
                            st.rerun()

    with st.expander("🖧 Paramètres du serveur IMAP", expanded=False):
        with st.form("imap_settings_form"):
            col_m1, col_m2 = st.columns(2, gap="medium")
            with col_m1:
                mailbox_imap_host = st.text_input(
                    "Hôte IMAP", value=str(cfg.get("mailbox_imap_host") or "outlook.office365.com")
                )
                mailbox_imap_port = st.number_input(
                    "Port IMAP", value=int(cfg.get("mailbox_imap_port", 993) or 993), step=1
                )
            with col_m2:
                mailbox_imap_user = st.text_input(
                    "Adresse email du compte", value=str(cfg.get("mailbox_imap_user") or "")
                )
                mailbox_drafts_folder = st.text_input(
                    "Dossier des brouillons IMAP",
                    value=str(cfg.get("mailbox_drafts_folder") or "Drafts"),
                )

            mailbox_use_ssl = st.checkbox(
                "Utiliser SSL", value=bool(int(cfg.get("mailbox_use_ssl", 1) or 1))
            )

            col_imap_save, col_imap_test = st.columns([2, 1], gap="medium")
            with col_imap_save:
                submitted_imap = st.form_submit_button(
                    "💾 Enregistrer les réglages IMAP", type="primary", width="stretch"
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
            if st.button("📡 Tester la connexion IMAP", width="stretch"):
                with st.spinner("Test de connexion IMAP..."):
                    ok, message_imap, dossiers = tester_connexion_imap(cfg)
                    if ok:
                        st.success(f"✅ {message_imap}")
                    else:
                        st.error(f"❌ {message_imap}")

    st.divider()

    # -------------------------------------------------------------------------
    # Section B : Modèle IA Mistral
    # -------------------------------------------------------------------------
    st.subheader("🤖 Modèle d'Intelligence Artificielle (Mistral)")

    with st.expander("⚙️ Configuration du modèle IA", expanded=False):
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
                current_model = str(cfg.get("llm_model") or "mistral-small-latest")
                model_options = [
                    "mistral-small-latest",
                    "mistral-tiny",
                    "open-mistral-7b",
                    "mistral-medium-latest",
                    "Autre (saisie personnalisée)",
                ]
                default_index = (
                    model_options.index(current_model)
                    if current_model in model_options
                    else len(model_options) - 1
                )
                selected_model_choice = st.selectbox(
                    "Modèle Mistral",
                    options=model_options,
                    index=default_index,
                    help=(
                        "Recommandation Mistral : privilégiez un modèle léger comme 'mistral-tiny', "
                        "'open-mistral-7b' ou 'mistral-small-latest' pour respecter les quotas de taux."
                    ),
                )
                if selected_model_choice == "Autre (saisie personnalisée)":
                    llm_model = st.text_input("Nom du modèle personnalisé", value=current_model)
                else:
                    llm_model = selected_model_choice

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
                "💾 Enregistrer la configuration IA", type="primary", width="stretch"
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
            if st.button("🧪 Tester l'API Mistral", width="stretch"):
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

    st.info(
        "💡 **Gestion des quotas et limites (HTTP 429 - Rate limit exceeded)** :\n"
        "- **Limite Free tier** : Mistral impose un plafond strict de **32 requêtes par minute** tous modèles confondus.\n"
        "- **Espacement automatique** : CPTCOPRO applique automatiquement un délai de **2 secondes** entre chaque requête par lot pour rester sous ce seuil.\n"
        "- **Modèles légers préconisés** : Privilégiez `mistral-tiny`, `mistral-small-latest` ou `open-mistral-7b`.\n"
        "- **Gestion du Retry-After** : En cas de pic de charge, l'application réessaie après l'en-tête `Retry-After` ou une attente de 5 secondes.\n"
        "- **Secours garanti** : En cas de dépassement de quota ou de panne, CPTCOPRO bascule sur vos modèles types locaux pour ne jamais perdre de données."
    )
