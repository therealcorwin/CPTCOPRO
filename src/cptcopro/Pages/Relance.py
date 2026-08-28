"""Generation des brouillons de relance pour coproprietaires en debit."""

from __future__ import annotations

import os
import pandas as pd
import streamlit as st

# Charger le .env pour s'assurer que MISTRAL_API_KEY est disponible
try:
    from cptcopro.utils.paths import init_env
    init_env()
except Exception:
    try:
        from dotenv import load_dotenv
        from cptcopro.utils.paths import get_env_file_path
        env_path = get_env_file_path()
        if env_path and env_path.exists():
            load_dotenv(env_path)
    except Exception:
        pass

from cptcopro.utils.paths import get_db_path
from cptcopro.Database import (
    get_relance_config,
    list_relances_due,
    upsert_relance_destinataire,
    save_relance_draft,
    list_relance_templates,
)
from cptcopro.utils.relance_mailer import (
    generate_relance_draft_with_llm,
    render_relance_template,
    build_email_message,
    save_draft_to_imap,
)


DB_PATH = get_db_path()

# Initialiser la session pour les brouillons a editer
if "drafts_to_edit" not in st.session_state:
    st.session_state.drafts_to_edit = []


def _db_cache_key() -> int:
    try:
        return DB_PATH.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=120, show_spinner=False)
def _load_due_data(db_path: str, cache_key: int) -> tuple[dict, pd.DataFrame]:
    del cache_key
    cfg = get_relance_config(db_path)
    rows = list_relances_due(db_path)
    return cfg, pd.DataFrame(rows)


@st.cache_data(ttl=120, show_spinner=False)
def _load_templates(db_path: str, cache_key: int) -> list[dict]:
    del cache_key
    return list_relance_templates(db_path)


st.title("Relances et Notifications")
st.caption("Genere et editez des brouillons email pour les coproprietaires en debit.")

cfg, due_df = _load_due_data(str(DB_PATH), _db_cache_key())

if not bool(int(cfg.get("enabled", 1) or 1)):
    st.warning("La generation de relances est desactivee dans la configuration.")

if due_df.empty:
    st.info("Aucun coproprietaire en debit eleve a relancer pour le moment.")
    st.stop()

frequency_days = int(cfg.get("frequency_days", 14) or 14)
st.info(f"Frequence active: une relance maximum tous les {frequency_days} jours par coproprietaire.")

due_df["due"] = due_df["due"].fillna(0).astype(int)
due_df["debit"] = pd.to_numeric(due_df["debit"], errors="coerce").fillna(0.0)


# ============================================================================
# SECTION 1: GESTION DES DESTINATAIRES
# ============================================================================

st.subheader("Destinataires")

edit_df = due_df[
    [
        "code_proprietaire",
        "nom_proprietaire",
        "debit",
        "num_apt",
        "type_apt",
        "email_to",
        "contact_name",
    ]
].copy()

edited_dest = st.data_editor(
    edit_df,
    width="stretch",
    hide_index=True,
    num_rows="fixed",
    column_config={
        "code_proprietaire": st.column_config.TextColumn("Code", disabled=True),
        "nom_proprietaire": st.column_config.TextColumn("Nom", disabled=True),
        "debit": st.column_config.NumberColumn("Debit", format="%.2f EUR", disabled=True),
        "num_apt": st.column_config.TextColumn("Lot", disabled=True),
        "type_apt": st.column_config.TextColumn("Type", disabled=True),
        "email_to": st.column_config.TextColumn("Email destinataire"),
        "contact_name": st.column_config.TextColumn("Contact (optionnel)"),
    },
    key="relance_dest_editor",
)

if st.button("Enregistrer les destinataires", type="secondary"):
    nb_saved = 0
    for row in edited_dest.to_dict("records"):
        email_to = str(row.get("email_to") or "").strip()
        if not email_to:
            continue
        upsert_relance_destinataire(
            str(DB_PATH),
            code_proprietaire=str(row["code_proprietaire"]),
            email_to=email_to,
            contact_name=str(row.get("contact_name") or "").strip() or None,
        )
        nb_saved += 1
    _load_due_data.clear()
    st.success(f"{nb_saved} destinataire(s) enregistre(s).")
    st.rerun()


# ============================================================================
# SECTION 2: GENERATION DES BROUILLONS
# ============================================================================

st.subheader("Coproprietaires dus pour relance")
due_only = due_df[due_df["due"] == 1].copy()

if due_only.empty:
    st.info("Tous les coproprietaires en alerte ont deja une relance recente.")
    st.stop()

templates = _load_templates(str(DB_PATH), _db_cache_key())
template_names = [t["name"] for t in templates]
default_template_name = next(
    (t["name"] for t in templates if t["is_default"]), template_names[0] if template_names else ""
)
templates_by_name = {t["name"]: t for t in templates}

due_display = due_only[
    [
        "code_proprietaire",
        "nom_proprietaire",
        "debit",
        "type_alerte",
        "date_origin",
        "last_relance_date",
        "jours_depuis_derniere_relance",
        "email_to",
    ]
].copy()
due_display.insert(0, "Generer", True)
due_display["Template"] = default_template_name

st.caption(
    "Cochez les coproprietaires a traiter et choisissez le template a appliquer pour chacun "
    "(generation en masse)."
)
edited_due = st.data_editor(
    due_display,
    key="due_relances_editor",
    width="stretch",
    hide_index=True,
    num_rows="fixed",
    column_config={
        "Generer": st.column_config.CheckboxColumn(required=True, width="small"),
        "code_proprietaire": st.column_config.TextColumn("Code", disabled=True),
        "nom_proprietaire": st.column_config.TextColumn("Nom", disabled=True),
        "debit": st.column_config.NumberColumn("Debit", format="%.2f EUR", disabled=True),
        "type_alerte": st.column_config.TextColumn("Type", disabled=True),
        "date_origin": st.column_config.TextColumn("Date situation", disabled=True),
        "last_relance_date": st.column_config.TextColumn("Derniere relance", disabled=True),
        "jours_depuis_derniere_relance": st.column_config.NumberColumn("Jours ecoules", disabled=True),
        "email_to": st.column_config.TextColumn("Email", disabled=True),
        "Template": st.column_config.SelectboxColumn(
            "Template", options=template_names, required=True, width="medium"
        ),
    },
)

if st.button("Generer les brouillons", type="primary", disabled=edited_due.empty):
    if not bool(int(cfg.get("enabled", 1) or 1)):
        st.error("Generation desactivee. Activez-la dans la page Configuration Relances.")
        st.stop()

    rows_to_generate = edited_due[edited_due["Generer"] == True]  # noqa: E712
    if rows_to_generate.empty:
        st.warning("Aucun coproprietaire coche pour la generation.")
        st.stop()

    # Reinitialiser la liste d'edition
    st.session_state.drafts_to_edit = []

    with st.spinner("Generation des brouillons en cours..."):
        nb_generated = 0

        for _, edited_row in rows_to_generate.iterrows():
            code = str(edited_row["code_proprietaire"])
            row = due_only[due_only["code_proprietaire"].astype(str) == code]
            if row.empty:
                continue

            payload = {str(k): v for k, v in row.iloc[0].to_dict().items()}
            email_to = str(payload.get("email_to") or "").strip()
            if not email_to:
                continue

            selected_template = templates_by_name.get(str(edited_row["Template"]))
            if selected_template is not None and (selected_template.get("generation_mode") or "static") == "static":
                subject, body = render_relance_template(selected_template, payload, cfg)
                provider, model = "template", selected_template["name"]
            else:
                # Generation via LLM, guidee par le template (ton + contenu) s'il est fourni
                subject, body, provider, model = generate_relance_draft_with_llm(
                    payload, cfg, template=selected_template
                )

            # Creer l'objet brouillon pour edition
            draft = {
                "code_proprietaire": str(payload.get("code_proprietaire") or ""),
                "nom_proprietaire": str(payload.get("nom_proprietaire") or ""),
                "email_to": email_to,
                "debit": float(payload.get("debit") or 0.0),
                "num_apt": str(payload.get("num_apt") or "NA"),
                "type_apt": str(payload.get("type_apt") or "NA"),
                "date_origin": str(payload.get("date_origin") or ""),
                "subject": subject,
                "body": body,
                "provider": provider,
                "model": model,
                "selected": True,
                "status": "draft_local",
                "modified": False,
            }
            st.session_state.drafts_to_edit.append(draft)
            nb_generated += 1

    st.success(f"{nb_generated} brouillon(s) genere(s) et pret(s) pour edition !")


# ============================================================================
# SECTION 3: EDITION DES BROUILLONS
# ============================================================================

if st.session_state.drafts_to_edit:
    st.subheader("Edition des brouillons")
    
    # Preparer les donnees pour l'editeur
    edit_data = []
    for i, draft in enumerate(st.session_state.drafts_to_edit):
        edit_data.append({
            "#": i + 1,
            "Selectionne": draft.get("selected", True),
            "Nom": draft["nom_proprietaire"],
            "Lot": draft.get("num_apt", "NA"),
            "Email": draft["email_to"],
            "Debit": draft["debit"],
            "Sujet": draft["subject"],
            "Corps": draft["body"],
            "Modifie": "Oui" if draft.get("modified") else "Non",
        })
    
    # Afficher dans un data_editor
    edited_df = st.data_editor(
        pd.DataFrame(edit_data),
        key="drafts_editor",
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "#": st.column_config.NumberColumn(disabled=True, width="small"),
            "Selectionne": st.column_config.CheckboxColumn(required=True, width="small"),
            "Nom": st.column_config.TextColumn(disabled=True, width="medium"),
            "Lot": st.column_config.TextColumn(disabled=True, width="small"),
            "Email": st.column_config.TextColumn(disabled=True, width="medium"),
            "Debit": st.column_config.NumberColumn(format="%.2f EUR", disabled=True, width="small"),
            "Sujet": st.column_config.TextColumn(width="large"),
            "Corps": st.column_config.TextColumn(width="large"),
            "Modifie": st.column_config.TextColumn(disabled=True, width="small"),
        },
    )
    
    # Boutons d'action
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("Enregistrer les modifications", type="primary", use_container_width=True):
            nb_saved = 0
            # Appliquer les modifications et sauvegarder en base
            for i, row in edited_df.iterrows():
                if i < len(st.session_state.drafts_to_edit):
                    draft = st.session_state.drafts_to_edit[i]
                    draft["subject"] = row["Sujet"]
                    draft["body"] = row["Corps"]
                    draft["selected"] = row["Selectionne"]
                    draft["modified"] = True
                    
                    # Sauvegarder en base de donnees
                    try:
                        draft_id = draft.get("draft_id")
                        returned_draft_id = save_relance_draft(
                            str(DB_PATH),
                            code_proprietaire=draft["code_proprietaire"],
                            nom_proprietaire=draft["nom_proprietaire"],
                            debit=draft["debit"],
                            email_to=draft["email_to"],
                            subject=draft["subject"],
                            body=draft["body"],
                            llm_provider=draft.get("provider", "manual"),
                            llm_model=draft.get("model", "manual"),
                            status="draft_local",
                            remote_draft_id=draft.get("remote_draft_id"),
                            error_message=None,
                            draft_id=draft_id,
                        )
                        draft["draft_id"] = returned_draft_id
                        nb_saved += 1
                    except Exception as e:
                        st.error(f"Erreur sauvegarde de {draft['nom_proprietaire']}: {e}")
            
            if nb_saved > 0:
                st.success(f"{nb_saved} modification(s) enregistree(s) en base !")
            else:
                st.success("Modifications enregistrees (en session).")
    
    with col2:
        if st.button("Envoyer les brouillons selectionnes", type="primary", use_container_width=True):
            nb_sent = 0
            nb_saved = 0
            nb_skipped = 0

            for draft in st.session_state.drafts_to_edit:
                if not draft.get("selected", False):
                    nb_skipped += 1
                    continue

                imap_error = None
                try:
                    # Construire le message
                    message = build_email_message(
                        sender_email=str(cfg.get("sender_email") or ""),
                        sender_name=str(cfg.get("sender_name") or ""),
                        to_email=draft["email_to"],
                        subject=draft["subject"],
                        body=draft["body"],
                    )

                    # Essayer d'envoyer via IMAP
                    try:
                        remote_id = save_draft_to_imap(cfg, message)
                        status = "draft_imap"
                        nb_sent += 1
                        success_msg = "Envoye via IMAP"
                    except Exception as exc:
                        imap_error = exc
                        remote_id = None
                        status = "draft_local"
                        nb_saved += 1
                        success_msg = "Sauvegarde locale"

                    # Sauvegarder en base
                    existing_draft_id = draft.get("draft_id")
                    returned_draft_id = save_relance_draft(
                        str(DB_PATH),
                        code_proprietaire=draft["code_proprietaire"],
                        nom_proprietaire=draft["nom_proprietaire"],
                        debit=draft["debit"],
                        email_to=draft["email_to"],
                        subject=draft["subject"],
                        body=draft["body"],
                        llm_provider=draft.get("provider", "manual"),
                        llm_model=draft.get("model", "manual"),
                        status=status,
                        remote_draft_id=remote_id,
                        error_message=str(imap_error) if status == "draft_local" else None,
                        draft_id=existing_draft_id,
                    )

                    draft["draft_id"] = returned_draft_id
                    draft["status"] = status

                    st.info(f"{draft['nom_proprietaire']}: {success_msg}")

                except Exception as e:
                    st.error(f"Erreur pour {draft['nom_proprietaire']}: {e}")

            # Vider la session apres envoi
            st.session_state.drafts_to_edit = []
            _load_due_data.clear()
            st.success(f"{nb_sent} brouillon(s) envoyes via IMAP, {nb_saved} sauvegardes localement, {nb_skipped} ignores.")
    
    with col3:
        if st.button("Annuler", type="secondary", use_container_width=True):
            st.session_state.drafts_to_edit = []
            st.rerun()


# ============================================================================
# SECTION 4: ACCES A LA GESTION COMPLETE DES BROUILLONS
# ============================================================================

st.divider()
st.info("Pour gerer tous vos brouillons (y compris les anciens), allez dans la page Gestion des Brouillons.")
