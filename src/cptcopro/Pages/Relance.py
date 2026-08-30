"""Génération assistée par IA et templates des relances pour copropriétaires en débit."""

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
from cptcopro.utils.ui_components import render_header


DB_PATH = get_db_path()

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


render_header(
    "✉️ Assistant de Relances & Notifications",
    "Générez des messages de relance personnalisés (via IA Mistral ou modèles types) pour les impayés",
)

cfg, due_df = _load_due_data(str(DB_PATH), _db_cache_key())

is_enabled = bool(int(cfg.get("enabled", 1) or 1))
if not is_enabled:
    st.warning("⚠️ La génération de relances est actuellement désactivée dans les paramètres.")

if due_df.empty:
    st.success("🎉 Aucun copropriétaire en débit élevé à relancer pour le moment.")
    st.stop()

frequency_days = int(cfg.get("frequency_days", 14) or 14)

due_df["due"] = due_df["due"].fillna(0).astype(int)
due_df["debit"] = pd.to_numeric(due_df["debit"], errors="coerce").fillna(0.0)

tab_generation, tab_destinataires = st.tabs([
    "🎯 Copropriétaires à relancer & Rédaction",
    "👥 Carnet d'adresses des destinataires",
])

# ============================================================================
# ONGLET 1: GÉNÉRATION DES RELANCES
# ============================================================================
with tab_generation:
    due_only = due_df[due_df["due"] == 1].copy()

    # Bandeau d'information
    col_info1, col_info2 = st.columns([3, 1])
    with col_info1:
        st.info(f"⏳ **Règle active** : Une relance maximum tous les **{frequency_days} jours** par copropriétaire.")
    with col_info2:
        st.metric("Impayés à traiter", len(due_only))

    if due_only.empty:
        st.success("✅ Tous les copropriétaires en alerte ont déjà reçu une relance récente.")
    else:
        templates = _load_templates(str(DB_PATH), _db_cache_key())
        template_names = [t["name"] for t in templates]
        default_template_name = next(
            (t["name"] for t in templates if t["is_default"]), template_names[0] if template_names else ""
        )
        templates_by_name = {t["name"]: t for t in templates}

        due_cols = [
            "code_proprietaire",
            "nom_proprietaire",
            "debit",
            "type_alerte",
            "date_origin",
            "nb_relances_total",
            "last_relance_date",
            "jours_depuis_derniere_relance",
            "email_to",
        ]
        available_due_cols = [c for c in due_cols if c in due_only.columns]
        due_display = due_only[available_due_cols].copy()
        due_display.insert(0, "Generer", True)
        due_display["Template"] = default_template_name

        st.caption("Sélectionnez les comptes à relancer et choisissez le modèle de message à appliquer :")

        edited_due = st.data_editor(
            due_display,
            key="due_relances_editor",
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Generer": st.column_config.CheckboxColumn("Sélection", required=True, width="small"),
                "code_proprietaire": st.column_config.TextColumn("Code", disabled=True, width="small"),
                "nom_proprietaire": st.column_config.TextColumn("Nom du copropriétaire", disabled=True, width="medium"),
                "debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €", disabled=True, width="small"),
                "type_alerte": st.column_config.TextColumn("Type", disabled=True, width="small"),
                "date_origin": st.column_config.TextColumn("Date situation", disabled=True, width="small"),
                "nb_relances_total": st.column_config.NumberColumn("Relances faites", disabled=True, width="small"),
                "last_relance_date": st.column_config.TextColumn("Dernière relance", disabled=True, width="small"),
                "jours_depuis_derniere_relance": st.column_config.NumberColumn("Jours écoulés", disabled=True, width="small"),
                "email_to": st.column_config.TextColumn("Email destinataire", disabled=True, width="medium"),
                "Template": st.column_config.SelectboxColumn(
                    "Modèle", options=template_names, required=True, width="medium"
                ),
            },
        )

        st.divider()
        col_gen_opt, col_gen_btn = st.columns([2, 1], gap="medium")

        with col_gen_opt:
            force_llm = st.checkbox(
                "🤖 Rédiger avec l'Assistant IA (Mistral)",
                value=str(cfg.get("llm_provider") or "mistral") == "mistral",
                help="Utilise le modèle Mistral pour rédiger un message courtois, contextuel et personnalisé.",
            )

        with col_gen_btn:
            if st.button("✨ Rédiger les brouillons", type="primary", use_container_width=True, disabled=edited_due.empty):
                if not is_enabled:
                    st.error("Génération désactivée dans les paramètres.")
                    st.stop()

                rows_to_generate = edited_due[edited_due["Generer"] == True]
                if rows_to_generate.empty:
                    st.warning("Veuillez cocher au moins un copropriétaire.")
                else:
                    st.session_state.drafts_to_edit = []

                    with st.spinner("Rédaction des brouillons en cours..."):
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
                            use_llm = force_llm or (selected_template is not None and selected_template.get("generation_mode") == "llm")

                            if use_llm:
                                subject, body, provider, model = generate_relance_draft_with_llm(
                                    payload, cfg, template=selected_template
                                )
                            else:
                                subject, body = render_relance_template(selected_template or {}, payload, cfg)
                                provider, model = "template", (selected_template or {}).get("name", "Standard")

                            # Sauvegarder directement comme brouillon local
                            draft_id = save_relance_draft(
                                str(DB_PATH),
                                code_proprietaire=str(payload.get("code_proprietaire") or ""),
                                nom_proprietaire=str(payload.get("nom_proprietaire") or ""),
                                debit=float(payload.get("debit") or 0.0),
                                email_to=email_to,
                                subject=subject,
                                body=body,
                                llm_provider=provider,
                                llm_model=model,
                                status="draft_local",
                            )

                            st.session_state.drafts_to_edit.append({
                                "draft_id": draft_id,
                                "nom": payload.get("nom_proprietaire"),
                                "email": email_to,
                                "subject": subject,
                                "body": body,
                            })
                            nb_generated += 1

                    st.toast(f"✅ {nb_generated} brouillon(s) généré(s) avec succès !", icon="📬")
                    _load_due_data.clear()
                    st.success(
                        f"✅ **{nb_generated} brouillon(s) prêt(s)** ! Vous pouvez les inspecter et les envoyer depuis l'onglet ci-dessous ou la page **Brouillons & Boîte d'envoi**."
                    )


# ============================================================================
# ONGLET 2: CARNET D'ADRESSES DESTINATAIRES
# ============================================================================
with tab_destinataires:
    st.subheader("Gestion des adresses emails des copropriétaires")
    st.caption("Renseignez ou mettez à jour les emails de notification. Ces informations sont conservées en base locale.")

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
            "code_proprietaire": st.column_config.TextColumn("Code", disabled=True, width="small"),
            "nom_proprietaire": st.column_config.TextColumn("Nom", disabled=True, width="medium"),
            "debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €", disabled=True, width="small"),
            "num_apt": st.column_config.TextColumn("Lot", disabled=True, width="small"),
            "type_apt": st.column_config.TextColumn("Type", disabled=True, width="small"),
            "email_to": st.column_config.TextColumn("Email de notification (modifiable)", width="large"),
            "contact_name": st.column_config.TextColumn("Nom du contact (optionnel)", width="medium"),
        },
        key="relance_dest_editor",
    )

    col_btn_dest, _ = st.columns([1.5, 3])
    with col_btn_dest:
        if st.button("💾 Enregistrer le carnet d'adresses", type="primary", use_container_width=True):
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
            st.toast(f"{nb_saved} adresse(s) enregistrée(s)", icon="💾")
            st.success(f"✅ {nb_saved} destinataire(s) enregistré(s) avec succès.")
            st.rerun()
