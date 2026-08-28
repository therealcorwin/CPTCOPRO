"""Gestion complete des brouillons de relance.

Cette page permet de:
- Lister tous les brouillons (tous statuts)
- Filtrer par statut
- Editer un brouillon existant
- Envoyer manuellement un brouillon
- Supprimer un brouillon
"""

from __future__ import annotations

import os
import pandas as pd
import streamlit as st

# Charger le .env
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
    get_relance_drafts,
    mark_relance_draft_status,
    save_relance_draft,
)
from cptcopro.utils.relance_mailer import (
    build_email_message,
    save_draft_to_imap,
)

DB_PATH = get_db_path()


@st.cache_data(ttl=60, show_spinner=False)
def _load_all_drafts(db_path: str) -> list[dict]:
    """Charge tous les brouillons depuis la base."""
    return get_relance_drafts(db_path, limit=500)


@st.cache_data(ttl=120, show_spinner=False)
def _load_config(db_path: str) -> dict:
    """Charge la configuration de relance."""
    return get_relance_config(db_path)


st.title("Gestion des Brouillons")
st.caption("Editez, envoyez ou supprimez vos brouillons de relance.")

# Charger les donnees
cfg = _load_config(str(DB_PATH))
all_drafts = _load_all_drafts(str(DB_PATH))

if not all_drafts:
    st.info("Aucun brouillon trouve en base de donnees.")
    st.stop()

# Convertir en DataFrame
df_drafts = pd.DataFrame(all_drafts)

# Ajouter une colonne de selection pour l'edition
if "selected" not in df_drafts.columns:
    df_drafts["selected"] = False

# ============================================================================
# FILTRES
# ============================================================================

st.subheader("Filtres")

# Filtre par statut
status_options = ["Tous"] + sorted(df_drafts["status"].dropna().unique().tolist())
selected_status = st.selectbox(
    "Filtrer par statut",
    options=status_options,
    index=0,
    key="draft_status_filter",
)

# Filtre par nom
name_filter = st.text_input("Filtrer par nom", key="draft_name_filter")

# Appliquer les filtres
filtered_df = df_drafts.copy()
if selected_status != "Tous":
    filtered_df = filtered_df[filtered_df["status"] == selected_status]
if name_filter:
    filtered_df = filtered_df[
        filtered_df["nom_proprietaire"].str.contains(name_filter, case=False, na=False)
    ]

st.info(f"{len(filtered_df)} brouillon(s) sur {len(df_drafts)} total")
# ============================================================================
# TABLEAU DES BROUILLONS
# ============================================================================

st.subheader("Liste des brouillons")

# Colonnes a afficher
display_columns = [
    "selected",
    "draft_id",
    "nom_proprietaire",
    "email_to",
    "subject",
    "debit",
    "status",
    "llm_provider",
    "created_at",
]

# Renommer les colonnes pour l'affichage
column_names = {
    "selected": "S",
    "draft_id": "ID",
    "nom_proprietaire": "Nom",
    "email_to": "Email",
    "subject": "Sujet",
    "debit": "Débit",
    "status": "Statut",
    "llm_provider": "Provider",
    "created_at": "Créé le",
}

# Appliquer les noms
filtered_df_display = filtered_df[display_columns].copy()
filtered_df_display.rename(columns=column_names, inplace=True)

# Afficher le tableau avec selection
edited_df = st.data_editor(
    filtered_df_display,
    key="all_drafts_editor",
    width="stretch",
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "S": st.column_config.CheckboxColumn(required=True, width="small"),
        "ID": st.column_config.NumberColumn(disabled=True, width="small"),
        "Nom": st.column_config.TextColumn(width="medium"),
        "Email": st.column_config.TextColumn(width="medium"),
        "Sujet": st.column_config.TextColumn(width="large"),
        "Débit": st.column_config.NumberColumn(format="%.2f EUR", width="small"),
        "Statut": st.column_config.TextColumn(width="medium"),
        "Provider": st.column_config.TextColumn(width="small"),
        "Créé le": st.column_config.TextColumn(width="medium"),
    },
)

# ============================================================================
# ACTIONS EN MASSE
# ============================================================================

if len(filtered_df) > 0:
    st.subheader("Actions en masse")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📤 Envoyer les selectionnes", type="primary", use_container_width=True):
            nb_sent = 0
            nb_error = 0
            
            # Utiliser edited_df qui contient les modifications de l'utilisateur
            for _, row in edited_df.iterrows():
                if not row.get("S", False):  # "S" est le nom affiche pour "selected"
                    continue
                
                # Trouver le brouillon correspondant dans filtered_df
                draft_id = int(row["ID"])
                full_draft = filtered_df[filtered_df["draft_id"] == draft_id].iloc[0].to_dict()
                
                try:
                    message = build_email_message(
                        sender_email=str(cfg.get("sender_email") or ""),
                        sender_name=str(cfg.get("sender_name") or ""),
                        to_email=full_draft["email_to"],
                        subject=full_draft["subject"],
                        body=full_draft["body"],
                    )
                    
                    try:
                        remote_id = save_draft_to_imap(cfg, message)
                        mark_relance_draft_status(
                            str(DB_PATH),
                            draft_id=draft_id,
                            status="draft_imap",
                            error_message=None,
                            remote_draft_id=remote_id,
                        )
                        nb_sent += 1
                        st.success(
                            f"{full_draft['nom_proprietaire']}: brouillon déposé dans Hotmail."
                        )
                    except Exception as exc:
                        mark_relance_draft_status(
                            str(DB_PATH),
                            draft_id=draft_id,
                            status="error",
                            error_message=str(exc),
                        )
                        nb_error += 1
                        st.error(
                            f"{full_draft['nom_proprietaire']}: échec IMAP - {exc}"
                        )
                
                except Exception as e:
                    st.error(f"❌ Erreur pour {full_draft['nom_proprietaire']}: {e}")
                    nb_error += 1
            
            if nb_sent > 0 or nb_error > 0:
                st.info(
                    f"Résultat : {nb_sent} brouillon(s) déposé(s), {nb_error} erreur(s). "
                    "Consultez la colonne Statut avant de relancer un envoi."
                )
                _load_all_drafts.clear()
    
    with col2:
        if st.button("🗑️ Supprimer les selectionnes", type="secondary", use_container_width=True):
            nb_deleted = 0
            # Utiliser edited_df qui contient les modifications de l'utilisateur
            for _, row in edited_df.iterrows():
                if row.get("S", False):  # "S" est le nom affiche pour "selected"
                    draft_id = int(row["ID"])
                    mark_relance_draft_status(
                        str(DB_PATH),
                        draft_id=draft_id,
                        status="deleted",
                    )
                    nb_deleted += 1
            
            if nb_deleted > 0:
                st.success(f"✅ {nb_deleted} brouillon(s) supprime(s)")
                _load_all_drafts.clear()
                st.rerun()
    
    with col3:
        if st.button("🔄 Actualiser", use_container_width=True):
            _load_all_drafts.clear()
            st.rerun()

# ============================================================================
# EDITION INDIVIDUELLE (modal)
# ============================================================================

st.subheader("Edition individuelle")

# Selectionner un brouillon a editer
if len(filtered_df) > 0:
    draft_ids = filtered_df["draft_id"].tolist()
    draft_names = filtered_df.apply(
        lambda row: f"{row['draft_id']}: {row['nom_proprietaire']} - {row['subject'][:50]}...",
        axis=1
    ).tolist()
    
    selected_draft_idx = st.selectbox(
        "Selectionner un brouillon a editer",
        options=range(len(draft_names)),
        format_func=lambda x: draft_names[x],
        key="draft_selector",
    )
    
    if selected_draft_idx is not None:
        selected_draft = filtered_df.iloc[selected_draft_idx].to_dict()
        
        with st.expander("Details du brouillon", expanded=True):
            st.write(f"**ID:** {selected_draft['draft_id']}")
            st.write(f"**Nom:** {selected_draft['nom_proprietaire']}")
            st.write(f"**Email:** {selected_draft['email_to']}")
            st.write(f"**Débit:** {selected_draft['debit']:.2f} EUR")
            st.write(f"**Statut:** {selected_draft['status']}")
            st.write(f"**Provider:** {selected_draft['llm_provider']} / {selected_draft['llm_model']}")
            st.write(f"**Créé le:** {selected_draft['created_at']}")
            
            if selected_draft.get("error_message"):
                st.error(f"**Erreur:** {selected_draft['error_message']}")
        
        # Formulaire d'edition
        with st.form(key=f"draft_edit_form_{selected_draft_idx}"):
            new_subject = st.text_input(
                "Sujet",
                value=selected_draft.get("subject", ""),
                key=f"edit_subject_{selected_draft_idx}",
            )
            new_body = st.text_area(
                "Corps",
                value=selected_draft.get("body", ""),
                height=300,
                key=f"edit_body_{selected_draft_idx}",
            )
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.form_submit_button("💾 Enregistrer les modifications", type="primary"):
                    try:
                        save_relance_draft(
                            str(DB_PATH),
                            code_proprietaire=selected_draft["code_proprietaire"],
                            nom_proprietaire=selected_draft["nom_proprietaire"],
                            debit=selected_draft["debit"],
                            email_to=selected_draft["email_to"],
                            subject=new_subject,
                            body=new_body,
                            llm_provider=selected_draft.get("llm_provider", "manual"),
                            llm_model=selected_draft.get("llm_model", "manual"),
                            status="draft_local",
                            remote_draft_id=selected_draft.get("remote_draft_id"),
                            error_message=None,
                            draft_id=selected_draft["draft_id"],
                        )
                        st.success("Brouillon mis a jour !")
                        _load_all_drafts.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur: {e}")
            
            with col_b:
                if st.form_submit_button("📤 Envoyer ce brouillon", type="primary"):
                    try:
                        message = build_email_message(
                            sender_email=str(cfg.get("sender_email") or ""),
                            sender_name=str(cfg.get("sender_name") or ""),
                            to_email=selected_draft["email_to"],
                            subject=new_subject,
                            body=new_body,
                        )
                        
                        try:
                            remote_id = save_draft_to_imap(cfg, message)
                            mark_relance_draft_status(
                                str(DB_PATH),
                                draft_id=selected_draft["draft_id"],
                                status="sent",
                            )
                            st.success("Brouillon envoye via IMAP !")
                        except Exception as exc:
                            mark_relance_draft_status(
                                str(DB_PATH),
                                draft_id=selected_draft["draft_id"],
                                status="error",
                                error_message=str(exc),
                            )
                            st.warning("Brouillon sauvegarde localement (erreur IMAP)")
                        
                        _load_all_drafts.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur: {e}")
            
            if st.form_submit_button("🗑️ Supprimer ce brouillon", type="secondary"):
                try:
                    mark_relance_draft_status(
                        str(DB_PATH),
                        draft_id=selected_draft["draft_id"],
                        status="deleted",
                    )
                    st.success("Brouillon supprime !")
                    _load_all_drafts.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur: {e}")

# ============================================================================
# STATISTIQUES
# ============================================================================

st.divider()
st.subheader("Statistiques")

col1, col2, col3, col4 = st.columns(4)

with col1:
    total_drafts = len(df_drafts)
    st.metric("Total brouillons", total_drafts)

with col2:
    sent_count = len(df_drafts[df_drafts["status"] == "sent"])
    st.metric("Envoyes", sent_count)

with col3:
    local_count = len(df_drafts[df_drafts["status"] == "draft_local"])
    st.metric("Locaux", local_count)

with col4:
    imap_count = len(df_drafts[df_drafts["status"] == "draft_imap"])
    st.metric("Sur IMAP", imap_count)
