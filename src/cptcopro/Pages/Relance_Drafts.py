"""Gestion complète des brouillons et suivi des relances."""

from __future__ import annotations

import io
from contextlib import suppress
from typing import Any, cast

import pandas as pd
import streamlit as st

# Charger le .env
try:
    from cptcopro.utils.paths import init_env

    init_env()
except Exception:
    with suppress(Exception):
        from dotenv import load_dotenv

        from cptcopro.utils.paths import get_env_file_path

        env_path = get_env_file_path()
        if env_path and env_path.exists():
            load_dotenv(env_path)

from cptcopro.Database import (
    get_relance_config,
    get_relance_drafts,
    get_relances_tracking_summary,
    mark_relance_draft_status,
    save_relance_draft,
)
from cptcopro.utils.relance_mailer import (
    build_email_message,
    save_draft_to_imap,
)
from cptcopro.utils.ui_components import render_header


@st.cache_data(ttl=60, show_spinner=False)
def _load_all_drafts() -> list[dict[str, Any]]:
    """Charge tous les brouillons depuis la base."""
    return cast(list[dict[str, Any]], get_relance_drafts(limit=1000))


@st.cache_data(ttl=60, show_spinner=False)
def _load_tracking_summary() -> list[dict[str, Any]]:
    """Charge la synthèse de suivi consolidée."""
    return cast(list[dict[str, Any]], get_relances_tracking_summary())


@st.cache_data(ttl=120, show_spinner=False)
def _load_config() -> dict[str, Any]:
    """Charge la configuration de relance."""
    return cast(dict[str, Any], get_relance_config())


render_header(
    "📬 Gestion des Brouillons & Suivi des Relances",
    "Consultez, modifiez et expédiez vos brouillons vers Hotmail (IMAP), ou analysez le recouvrement",
)

cfg = _load_config()

tab_drafts, tab_tracking, tab_history = st.tabs(
    [
        "📬 Brouillons & Actions en Masse",
        "📊 Tableau de Bord & Suivi",
        "📜 Journal Chronologique des Échanges",
    ]
)


# ============================================================================
# ONGLET 1: GESTION DES BROUILLONS & ACTIONS EN MASSE
# ============================================================================
with tab_drafts:
    all_drafts = _load_all_drafts()

    if not all_drafts:
        st.info(
            "ℹ️ Aucun brouillon trouvé en base de données. Vous pouvez en générer depuis la page **Génération des relances**."
        )
    else:
        df_drafts = pd.DataFrame(all_drafts)
        if "selected" not in df_drafts.columns:
            df_drafts["selected"] = False

        # --- Filtres ---
        col_f1, col_f2 = st.columns([1, 2], gap="medium")
        with col_f1:
            status_options = ["Tous", *sorted(df_drafts["status"].dropna().unique().tolist())]
            selected_status = st.selectbox(
                "Filtrer par statut",
                options=status_options,
                index=0,
                key="draft_status_filter",
            )
        with col_f2:
            name_filter = st.text_input(
                "Filtrer par nom ou code copropriétaire", key="draft_name_filter"
            )

        filtered_df = df_drafts.copy()
        if selected_status != "Tous":
            filtered_df = filtered_df[filtered_df["status"] == selected_status]
        if name_filter:
            filtered_df = filtered_df[
                filtered_df["nom_proprietaire"].str.contains(name_filter, case=False, na=False)
                | filtered_df["code_proprietaire"].str.contains(name_filter, case=False, na=False)
            ]

        # Gestion des sélections globales via session_state
        if "drafts_selection_action" in st.session_state:
            action = st.session_state.pop("drafts_selection_action")
            if action == "select_all":
                filtered_df["selected"] = True
            elif action == "deselect_all":
                filtered_df["selected"] = False
            elif action == "select_errors":
                filtered_df["selected"] = filtered_df["status"].isin(["draft_local", "error"])

        # --- Boutons de sélection en masse ---
        col_sel1, col_sel2, col_sel3, col_sel4 = st.columns([1.2, 1.2, 1.6, 1], gap="small")
        with col_sel1:
            if st.button("☑️ Tout cocher", use_container_width=True):
                st.session_state.drafts_selection_action = "select_all"
                st.rerun()
        with col_sel2:
            if st.button("◻️ Décocher tout", use_container_width=True):
                st.session_state.drafts_selection_action = "deselect_all"
                st.rerun()
        with col_sel3:
            if st.button("⚠️ Locaux / Erreurs uniquement", use_container_width=True):
                st.session_state.drafts_selection_action = "select_errors"
                st.rerun()
        with col_sel4:
            st.caption(f"**{len(filtered_df)} / {len(df_drafts)}** brouillon(s)")

        # --- Tableau d'édition ---
        display_columns = [
            "selected",
            "draft_id",
            "code_proprietaire",
            "nom_proprietaire",
            "email_to",
            "subject",
            "debit",
            "status",
            "llm_provider",
            "created_at",
        ]
        column_names = {
            "selected": "S",
            "draft_id": "ID",
            "code_proprietaire": "Code",
            "nom_proprietaire": "Nom",
            "email_to": "Email",
            "subject": "Sujet",
            "debit": "Débit",
            "status": "Statut",
            "llm_provider": "IA / Modèle",
            "created_at": "Créé le",
        }
        filtered_df_display = filtered_df[display_columns].copy()
        filtered_df_display.rename(columns=column_names, inplace=True)

        edited_df = st.data_editor(
            filtered_df_display,
            key=f"all_drafts_editor_{len(filtered_df)}",
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "S": st.column_config.CheckboxColumn("Sélection", required=True, width="small"),
                "ID": st.column_config.NumberColumn(disabled=True, width="small"),
                "Code": st.column_config.TextColumn(disabled=True, width="small"),
                "Nom": st.column_config.TextColumn(width="medium"),
                "Email": st.column_config.TextColumn(width="medium"),
                "Sujet": st.column_config.TextColumn(width="large"),
                "Débit": st.column_config.NumberColumn(format="%.2f €", disabled=True, width="small"),
                "Statut": st.column_config.TextColumn(disabled=True, width="medium"),
                "IA / Modèle": st.column_config.TextColumn(disabled=True, width="small"),
                "Créé le": st.column_config.DatetimeColumn(
                    "Créé le", format="DD/MM/YYYY HH:mm", disabled=True, width="medium"
                ),
            },
        )

        # --- Actions en masse ---
        st.divider()
        col_act1, col_act2, col_act3 = st.columns([2, 1.5, 1], gap="medium")

        with col_act1:
            if st.button(
                "📤 Déposer la sélection dans Hotmail (IMAP)",
                type="primary",
                use_container_width=True,
            ):
                nb_sent = 0
                nb_error = 0
                selected_rows = edited_df[edited_df["S"]]

                if selected_rows.empty:
                    st.warning("Aucun brouillon coché dans le tableau.")
                else:
                    with st.spinner(
                        f"Dépôt de {len(selected_rows)} message(s) sur le serveur IMAP..."
                    ):
                        for _, row in selected_rows.iterrows():
                            draft_id = int(row["ID"])
                            matching = filtered_df[filtered_df["draft_id"] == draft_id]
                            if matching.empty:
                                continue
                            full_draft = matching.iloc[0].to_dict()

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
                                        draft_id=draft_id,
                                        status="draft_imap",
                                        error_message=None,
                                        remote_draft_id=remote_id,
                                    )
                                    nb_sent += 1
                                except Exception as exc:
                                    mark_relance_draft_status(
                                        draft_id=draft_id,
                                        status="error",
                                        error_message=str(exc),
                                    )
                                    nb_error += 1
                            except Exception:
                                nb_error += 1

                    _load_all_drafts.clear()
                    _load_tracking_summary.clear()
                    st.toast(f"{nb_sent} brouillon(s) déposé(s) sur Hotmail !", icon="📬")
                    st.rerun()

        with col_act2:
            if st.button("🗑️ Supprimer les cochés", type="secondary", use_container_width=True):
                selected_rows = edited_df[edited_df["S"]]
                if selected_rows.empty:
                    st.warning("Aucun brouillon coché pour suppression.")
                else:
                    nb_deleted = 0
                    for _, row in selected_rows.iterrows():
                        mark_relance_draft_status(draft_id=int(row["ID"]), status="deleted")
                        nb_deleted += 1
                    _load_all_drafts.clear()
                    _load_tracking_summary.clear()
                    st.toast(f"{nb_deleted} brouillon(s) supprimé(s)", icon="🗑️")
                    st.rerun()

        with col_act3:
            if st.button("🔄 Actualiser", use_container_width=True):
                _load_all_drafts.clear()
                _load_tracking_summary.clear()
                st.rerun()

        # --- Édition unitaire détaillée ---
        st.divider()
        st.subheader("🔍 Inspection & Édition détaillée d'un brouillon")
        draft_names = filtered_df.apply(
            lambda r: (
                f"#{r['draft_id']} — {r['nom_proprietaire']} ({r.get('debit', 0.0):.2f} €) : {r.get('subject', '')[:45]}..."
            ),
            axis=1,
        ).tolist()

        if draft_names:
            selected_idx = st.selectbox(
                "Sélectionnez le brouillon à afficher :",
                options=range(len(draft_names)),
                format_func=lambda i: draft_names[i],
                key="draft_individual_select",
            )
            selected_draft = filtered_df.iloc[selected_idx].to_dict()

            with st.form(key=f"individual_edit_form_{selected_draft['draft_id']}"):
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.markdown(
                        f"**Copropriétaire :** {selected_draft['nom_proprietaire']} (`{selected_draft['code_proprietaire']}`)"
                    )
                    st.markdown(f"**Destinataire :** `{selected_draft['email_to']}`")
                with col_d2:
                    st.markdown(f"**Débit réclamé :** `{selected_draft['debit']:.2f} €`")
                    st.markdown(f"**Statut actuel :** `{selected_draft['status']}`")

                new_subject = st.text_input(
                    "Objet / Sujet", value=selected_draft.get("subject", "")
                )
                new_body = st.text_area(
                    "Corps du message", value=selected_draft.get("body", ""), height=220
                )

                col_b1, col_b2, col_b3 = st.columns([1.5, 1.5, 1], gap="medium")
                with col_b1:
                    if st.form_submit_button(
                        "💾 Sauvegarder modifications", type="primary", use_container_width=True
                    ):
                        save_relance_draft(
                            code_proprietaire=selected_draft["code_proprietaire"],
                            nom_proprietaire=selected_draft["nom_proprietaire"],
                            debit=selected_draft["debit"],
                            email_to=selected_draft["email_to"],
                            subject=new_subject,
                            body=new_body,
                            llm_provider=selected_draft.get("llm_provider", "manual"),
                            llm_model=selected_draft.get("llm_model", "manual"),
                            status=selected_draft["status"],
                            remote_draft_id=selected_draft.get("remote_draft_id"),
                            draft_id=selected_draft["draft_id"],
                        )
                        st.toast("Brouillon mis à jour !", icon="💾")
                        _load_all_drafts.clear()
                        _load_tracking_summary.clear()
                        st.rerun()

                with col_b2:
                    if st.form_submit_button(
                        "📤 Déposer sur Hotmail (IMAP)", use_container_width=True
                    ):
                        try:
                            msg = build_email_message(
                                sender_email=str(cfg.get("sender_email") or ""),
                                sender_name=str(cfg.get("sender_name") or ""),
                                to_email=selected_draft["email_to"],
                                subject=new_subject,
                                body=new_body,
                            )
                            remote_id = save_draft_to_imap(cfg, msg)
                            mark_relance_draft_status(
                                draft_id=selected_draft["draft_id"],
                                status="draft_imap",
                                remote_draft_id=remote_id,
                                error_message=None,
                            )
                            st.toast("Brouillon déposé sur Hotmail !", icon="📬")
                        except Exception as exc:
                            mark_relance_draft_status(
                                draft_id=selected_draft["draft_id"],
                                status="error",
                                error_message=str(exc),
                            )
                            st.error(f"Échec IMAP : {exc}")
                        _load_all_drafts.clear()
                        _load_tracking_summary.clear()
                        st.rerun()

                with col_b3:
                    if st.form_submit_button("🗑️ Supprimer", use_container_width=True):
                        mark_relance_draft_status(
                            draft_id=selected_draft["draft_id"], status="deleted"
                        )
                        st.toast("Brouillon supprimé", icon="🗑️")
                        _load_all_drafts.clear()
                        _load_tracking_summary.clear()
                        st.rerun()


# ============================================================================
# ONGLET 2: TABLEAU DE BORD & SUIVI DES RELANCES
# ============================================================================
with tab_tracking:
    st.subheader("Synthèse chronologique du recouvrement")
    st.caption(
        "Visualisez les dates clés : premier envoi, dernier envoi, volume de relances et statut d'apurement."
    )

    tracking_data = _load_tracking_summary()

    if not tracking_data:
        st.info("Aucune donnée de relance ou alerte détectée pour le suivi.")
    else:
        df_track = pd.DataFrame(tracking_data)

        # KPIs globaux
        total_copros = len(df_track)
        copros_relances = len(df_track[df_track["nb_relances_envoyees"] > 0])
        total_relances_envoyees = int(df_track["nb_relances_envoyees"].sum())
        total_debit_sous_relance = float(
            df_track[df_track["nb_relances_envoyees"] > 0]["debit_actuel"].sum()
        )

        kpi1, kpi2, kpi3, kpi4 = st.columns(4, gap="medium")
        with kpi1:
            st.metric("Copropriétaires suivis", total_copros)
        with kpi2:
            st.metric("Comptes déjà relancés", f"{copros_relances} / {total_copros}")
        with kpi3:
            st.metric("Total relances envoyées", total_relances_envoyees)
        with kpi4:
            st.metric("Débit total relancé", f"{total_debit_sous_relance:,.2f} €".replace(",", " "))

        st.divider()

        # Filtres
        col_t1, col_t2 = st.columns([2, 2], gap="medium")
        with col_t1:
            track_search = st.text_input(
                "Rechercher un copropriétaire (Nom ou Code)", key="track_search"
            )
        with col_t2:
            statut_filter = st.selectbox(
                "Filtrer par historique de relance",
                options=[
                    "Tous",
                    "Déjà relancés (au moins 1 fois)",
                    "Jamais relancés",
                    "Relancés multiples (>= 2 fois)",
                ],
                key="track_status_filter",
            )

        df_track_filtered = df_track.copy()
        if track_search:
            df_track_filtered = df_track_filtered[
                df_track_filtered["nom_proprietaire"].str.contains(
                    track_search, case=False, na=False
                )
                | df_track_filtered["code_proprietaire"].str.contains(
                    track_search, case=False, na=False
                )
            ]

        if statut_filter == "Déjà relancés (au moins 1 fois)":
            df_track_filtered = df_track_filtered[df_track_filtered["nb_relances_envoyees"] >= 1]
        elif statut_filter == "Jamais relancés":
            df_track_filtered = df_track_filtered[df_track_filtered["nb_relances_envoyees"] == 0]
        elif statut_filter == "Relancés multiples (>= 2 fois)":
            df_track_filtered = df_track_filtered[df_track_filtered["nb_relances_envoyees"] >= 2]

        def _compute_statut_label(row: pd.Series) -> str:
            nb = int(row.get("nb_relances_envoyees", 0) or 0)
            debit = float(row.get("debit_actuel", 0.0) or 0.0)
            jours = row.get("jours_depuis_derniere_relance")

            if debit <= 0:
                return "✅ Solde régularisé"
            if nb == 0:
                return "⏳ En attente 1ère relance"
            if nb == 1:
                return f"1ère relance ({jours}j)" if pd.notna(jours) else "1ère relance"
            if nb >= 3:
                return f"⚠️ Relance N°{nb} ({jours}j)" if pd.notna(jours) else f"⚠️ Relance N°{nb}"
            return f"Relance N°{nb} ({jours}j)" if pd.notna(jours) else f"Relance N°{nb}"

        df_track_filtered["Statut Suivi"] = df_track_filtered.apply(_compute_statut_label, axis=1)

        display_track_cols = [
            "code_proprietaire",
            "nom_proprietaire",
            "num_apt",
            "type_apt",
            "debit_actuel",
            "Statut Suivi",
            "nb_relances_envoyees",
            "first_relance_date",
            "last_relance_date",
            "jours_depuis_derniere_relance",
            "dernier_sujet",
        ]

        df_track_display = df_track_filtered[display_track_cols].copy()
        df_track_display.rename(
            columns={
                "code_proprietaire": "Code",
                "nom_proprietaire": "Nom",
                "num_apt": "Lot",
                "type_apt": "Type",
                "debit_actuel": "Débit actuel",
                "nb_relances_envoyees": "Nb relances",
                "first_relance_date": "1er envoi",
                "last_relance_date": "Dernier envoi",
                "jours_depuis_derniere_relance": "Jours écoulés",
                "dernier_sujet": "Dernier objet",
            },
            inplace=True,
        )

        st.dataframe(
            df_track_display,
            width="stretch",
            hide_index=True,
            column_config={
                "Code": st.column_config.TextColumn(width="small"),
                "Nom": st.column_config.TextColumn(width="medium"),
                "Lot": st.column_config.TextColumn(width="small"),
                "Type": st.column_config.TextColumn(width="small"),
                "Débit actuel": st.column_config.NumberColumn(format="%.2f €", width="small"),
                "Statut Suivi": st.column_config.TextColumn(width="medium"),
                "Nb relances": st.column_config.NumberColumn(width="small"),
                "1er envoi": st.column_config.TextColumn(width="small"),
                "Dernier envoi": st.column_config.TextColumn(width="small"),
                "Jours écoulés": st.column_config.NumberColumn(width="small"),
                "Dernier objet": st.column_config.TextColumn(width="large"),
            },
        )

        col_exp, _ = st.columns([1.5, 3])
        with col_exp:
            csv_buffer = io.StringIO()
            df_track_display.to_csv(csv_buffer, index=False, sep=";")
            st.download_button(
                label="📥 Télécharger le rapport de suivi (CSV)",
                data=csv_buffer.getvalue().encode("utf-8-sig"),
                file_name="suivi_relances_coproprietaires.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ============================================================================
# ONGLET 3: JOURNAL CHRONOLOGIQUE DES ÉCHANGES
# ============================================================================
with tab_history:
    st.subheader("Journal chronologique de toutes les relances")
    st.caption("Consultez l'historique complet de chaque message avec le texte exact rédigé.")

    all_drafts_hist = _load_all_drafts()
    if not all_drafts_hist:
        st.info("Aucun historique disponible.")
    else:
        df_hist = pd.DataFrame(all_drafts_hist)

        col_h1, col_h2 = st.columns([2, 1], gap="medium")
        with col_h1:
            search_hist = st.text_input("Filtrer l'historique par nom ou objet", key="hist_search")
        with col_h2:
            status_hist_filter = st.selectbox(
                "Statut",
                options=["Tous", "draft_imap", "draft_local", "sent", "error"],
                key="hist_status_filter",
            )

        if search_hist:
            df_hist = df_hist[
                df_hist["nom_proprietaire"].str.contains(search_hist, case=False, na=False)
                | df_hist["subject"].str.contains(search_hist, case=False, na=False)
            ]
        if status_hist_filter != "Tous":
            df_hist = df_hist[df_hist["status"] == status_hist_filter]

        for _, row in df_hist.iterrows():
            sent_label = row.get("sent_at") or row.get("created_at")
            status_icon = (
                "✓ (Hotmail)"
                if row["status"] in ("draft_imap", "sent")
                else ("⚠️ (Erreur)" if row["status"] == "error" else "📝 (Brouillon)")
            )
            expander_title = f"{status_icon} [{sent_label}] {row['nom_proprietaire']} ({row.get('debit', 0):.2f} €) : {row.get('subject', '')}"

            with st.expander(expander_title, expanded=False):
                col_i1, col_i2, col_i3 = st.columns(3)
                with col_i1:
                    st.write(f"**Destinataire :** `{row.get('email_to', '')}`")
                    st.write(f"**Code copro :** `{row.get('code_proprietaire', '')}`")
                with col_i2:
                    st.write(f"**Statut :** `{row.get('status', '')}`")
                    st.write(
                        f"**IA / Provider :** `{row.get('llm_provider', '')} ({row.get('llm_model', '')})`"
                    )
                with col_i3:
                    st.write(f"**Date création :** `{row.get('created_at', '')}`")
                    st.write(f"**Date envoi IMAP :** `{row.get('sent_at', 'Non envoyé')}`")

                st.markdown("**Sujet :** " + str(row.get("subject", "")))
                st.text_area(
                    "Contenu de l'email",
                    value=str(row.get("body", "")),
                    height=160,
                    disabled=True,
                    key=f"hist_body_{row['draft_id']}",
                )
                if row.get("error_message"):
                    st.error(f"Détail erreur : {row['error_message']}")
