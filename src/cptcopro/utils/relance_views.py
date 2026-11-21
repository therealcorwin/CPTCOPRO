"""Vues et composants partagés pour la gestion des relances et brouillons CPTCOPRO."""

from __future__ import annotations

import io
from contextlib import suppress
from typing import Any, cast

import pandas as pd
import streamlit as st

from cptcopro.Database import (
    get_relance_drafts,
    get_relances_tracking_summary,
    mark_relance_draft_status,
    save_relance_draft,
)
from cptcopro.utils.relance_mailer import (
    build_email_message,
    save_draft_to_imap,
)


@st.cache_data(ttl=60, show_spinner=False)
def load_all_drafts() -> list[dict[str, Any]]:
    """Charge tous les brouillons depuis la base."""
    return cast(list[dict[str, Any]], get_relance_drafts(limit=1000))


@st.cache_data(ttl=60, show_spinner=False)
def load_tracking_summary() -> list[dict[str, Any]]:
    """Charge la synthèse de suivi consolidée."""
    return cast(list[dict[str, Any]], get_relances_tracking_summary())


@st.dialog("🗑️ Confirmer la suppression des brouillons")
def dialog_confirmer_suppression_brouillons(selected_ids: list[int]) -> None:
    """Modale de confirmation pour la suppression par lot de brouillons."""
    st.write(
        f"Êtes-vous sûr de vouloir supprimer définitivement **{len(selected_ids)}** brouillon(s) sélectionné(s) ?"
    )
    st.caption("Cette action marquera ces brouillons comme supprimés en base de données.")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        if st.button("🗑️ Confirmer", type="primary", key="confirm_del_drafts_btn", width="stretch"):
            nb_deleted = 0
            for d_id in selected_ids:
                mark_relance_draft_status(draft_id=d_id, status="deleted")
                nb_deleted += 1
            if "drafts_selected_ids" in st.session_state:
                st.session_state.drafts_selected_ids.clear()
            if "drafts_editor_version" in st.session_state:
                st.session_state.drafts_editor_version += 1
            load_all_drafts.clear()
            load_tracking_summary.clear()
            st.toast(f"{nb_deleted} brouillon(s) supprimé(s)", icon="🗑️")
            st.rerun()
    with col_c2:
        if st.button("Annuler", key="cancel_del_drafts_btn", width="stretch"):
            st.rerun()


def _filter_drafts(df_drafts: pd.DataFrame) -> pd.DataFrame:
    """Filtre les brouillons par statut et par recherche textuelle."""
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
    return filtered_df


def _render_selection_bar(filtered_df: pd.DataFrame, total_count: int) -> None:
    """Boutons de sélection rapide en masse pour les brouillons."""
    col_sel1, col_sel2, col_sel3, col_sel4 = st.columns([1.2, 1.2, 1.6, 1], gap="small")
    with col_sel1:
        if st.button("☑️ Tout cocher", width="stretch", key="btn_check_all_drafts"):
            st.session_state.drafts_selected_ids = set(
                filtered_df["draft_id"].dropna().astype(int).tolist()
            )
            st.session_state.drafts_editor_version += 1
            st.rerun()
    with col_sel2:
        if st.button("◻️ Décocher tout", width="stretch", key="btn_uncheck_all_drafts"):
            st.session_state.drafts_selected_ids = set()
            st.session_state.drafts_editor_version += 1
            st.rerun()
    with col_sel3:
        if st.button("⚠️ Locaux / Erreurs uniquement", width="stretch", key="btn_check_errors_drafts"):
            st.session_state.drafts_selected_ids = set(
                filtered_df[filtered_df["status"].isin(["draft_local", "error"])]["draft_id"]
                .dropna()
                .astype(int)
                .tolist()
            )
            st.session_state.drafts_editor_version += 1
            st.rerun()
    with col_sel4:
        st.caption(f"**{len(filtered_df)} / {total_count}** brouillon(s)")


def render_drafts_management(cfg: dict[str, Any]) -> None:
    """Composant de gestion, édition et dépôt IMAP en masse des brouillons."""
    all_drafts = load_all_drafts()

    if not all_drafts:
        st.info(
            "ℹ️ Aucun brouillon trouvé en base de données. Vous pouvez en générer depuis l'onglet **À relancer & Rédaction**."
        )
        return

    df_drafts = pd.DataFrame(all_drafts)
    if "selected" not in df_drafts.columns:
        df_drafts["selected"] = False

    filtered_df = _filter_drafts(df_drafts)

    if "drafts_selected_ids" not in st.session_state:
        st.session_state.drafts_selected_ids = set()
    if "drafts_editor_version" not in st.session_state:
        st.session_state.drafts_editor_version = 0

    _render_selection_bar(filtered_df, len(df_drafts))

    filtered_df["selected"] = filtered_df["draft_id"].astype(int).isin(
        st.session_state.drafts_selected_ids
    )

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
        key=f"all_drafts_editor_{st.session_state.drafts_editor_version}",
        width="stretch",
        hide_index=True,
        num_rows="fixed",
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

    _render_mass_action_buttons(edited_df, filtered_df, cfg)

    # --- Édition unitaire détaillée ---
    st.divider()
    st.subheader("🔍 Inspection & Édition détaillée d'un brouillon")
    _render_individual_draft_editor(filtered_df, cfg)


def _render_mass_action_buttons(
    edited_df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    cfg: dict[str, Any],
) -> None:
    """Boutons d'action en masse pour les brouillons cochés."""
    st.divider()
    col_act1, col_act2, col_act3 = st.columns([2, 1.5, 1], gap="medium")

    with col_act1:
        if st.button(
            "📤 Déposer la sélection dans Hotmail (IMAP)",
            type="primary",
            width="stretch",
            key="btn_send_imap_selection",
        ):
            selected_rows = edited_df[edited_df["S"] == True]  # noqa: E712
            if selected_rows.empty:
                st.warning("Aucun brouillon coché dans le tableau.")
            else:
                _send_selected_to_imap(selected_rows, filtered_df, cfg)

    with col_act2:
        if st.button(
            "🗑️ Supprimer les cochés",
            type="secondary",
            width="stretch",
            key="btn_del_checked_drafts",
        ):
            selected_rows = edited_df[edited_df["S"] == True]  # noqa: E712
            if selected_rows.empty:
                st.warning("Aucun brouillon coché pour suppression.")
            else:
                ids_to_del = [
                    int(row["ID"])
                    for _, row in selected_rows.iterrows()
                    if not pd.isna(row.get("ID"))
                ]
                if ids_to_del:
                    dialog_confirmer_suppression_brouillons(ids_to_del)

    with col_act3:
        if st.button("🔄 Actualiser", width="stretch", key="btn_refresh_drafts_tab"):
            st.session_state.drafts_selected_ids.clear()
            st.session_state.drafts_editor_version += 1
            load_all_drafts.clear()
            load_tracking_summary.clear()
            st.rerun()


def _send_selected_to_imap(
    selected_rows: pd.DataFrame,
    filtered_df: pd.DataFrame,
    cfg: dict[str, Any],
) -> None:
    """Expédie les brouillons cochés vers le serveur IMAP Hotmail."""
    nb_sent = 0
    with st.spinner(f"Dépôt de {len(selected_rows)} message(s) sur le serveur IMAP..."):
        for _, row in selected_rows.iterrows():
            if pd.isna(row.get("ID")):
                continue
            draft_id = int(row["ID"])
            matching = filtered_df[filtered_df["draft_id"] == draft_id]
            if matching.empty:
                continue
            full_draft = matching.iloc[0].to_dict()

            with suppress(Exception):
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

    st.session_state.drafts_selected_ids.clear()
    st.session_state.drafts_editor_version += 1
    load_all_drafts.clear()
    load_tracking_summary.clear()
    st.toast(f"{nb_sent} brouillon(s) déposé(s) sur Hotmail !", icon="📬")
    st.rerun()


def _render_individual_draft_editor(
    filtered_df: pd.DataFrame,
    cfg: dict[str, Any],
) -> None:
    """Formulaire d'inspection et modification détaillée d'un brouillon unique."""
    draft_names = filtered_df.apply(
        lambda r: (
            f"#{r['draft_id']} — {r['nom_proprietaire']} ({r.get('debit', 0.0):.2f} €) : {r.get('subject', '')[:45]}..."
        ),
        axis=1,
    ).tolist()

    if not draft_names:
        return

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
                "💾 Sauvegarder modifications", type="primary", width="stretch"
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
                load_all_drafts.clear()
                load_tracking_summary.clear()
                st.rerun()

        with col_b2:
            if st.form_submit_button(
                "📤 Déposer sur Hotmail (IMAP)", width="stretch"
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
                load_all_drafts.clear()
                load_tracking_summary.clear()
                st.rerun()

        with col_b3:
            if st.form_submit_button("🗑️ Supprimer", width="stretch"):
                mark_relance_draft_status(
                    draft_id=selected_draft["draft_id"], status="deleted"
                )
                st.toast("Brouillon supprimé", icon="🗑️")
                load_all_drafts.clear()
                load_tracking_summary.clear()
                st.rerun()


def _format_date_val(val: object) -> str:
    """Helper pour formater proprement une date."""
    if val is None or pd.isna(val) or val == "":
        return "-"
    if hasattr(val, "strftime"):
        return str(val.strftime("%d/%m/%Y"))
    try:
        dt = pd.to_datetime(val)
        if pd.isna(dt):
            return "-"
        return str(dt.strftime("%d/%m/%Y"))
    except Exception:
        return str(val)


def _compute_statut_label(row: pd.Series) -> str:
    """Helper pour calculer le label de suivi du recouvrement."""
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


def render_tracking_dashboard() -> None:
    """Tableau de bord de suivi chronologique du recouvrement et KPIs."""
    st.subheader("Synthèse chronologique du recouvrement")
    st.caption(
        "Visualisez les dates clés : premier envoi, dernier envoi, volume de relances et statut d'apurement."
    )

    tracking_data = load_tracking_summary()
    if not tracking_data:
        st.info("Aucune donnée de relance ou alerte détectée pour le suivi.")
        return

    df_track = pd.DataFrame(tracking_data)

    total_copros = len(df_track)
    copros_relances = len(df_track[df_track["nb_relances_envoyees"] > 0])
    total_relances_envoyees = int(df_track["nb_relances_envoyees"].sum())
    total_debit_sous_relance = float(
        df_track[df_track["nb_relances_envoyees"] > 0]["debit_actuel"].sum()
    )

    col1, col2, col3, col4 = st.columns(4, gap="medium")
    with col1:
        st.metric("Copros sous surveillance", total_copros)
    with col2:
        st.metric("Comptes ayant reçu une relance", f"{copros_relances} / {total_copros}")
    with col3:
        st.metric("Volume total de relances envoyées", total_relances_envoyees)
    with col4:
        st.metric(
            "Encours des comptes relancés",
            f"{total_debit_sous_relance:,.2f} €".replace(",", " "),
        )

    st.divider()

    col_s1, col_s2 = st.columns([1, 2], gap="medium")
    with col_s1:
        statut_options = [
            "Tous",
            "Relances en cours (débit > 0)",
            "Soldes régularisés (débit <= 0)",
            "Sans relance envoyée",
        ]
        selected_track_filter = st.selectbox(
            "Filtrer par situation", options=statut_options, key="track_filter_select"
        )
    with col_s2:
        search_track = st.text_input(
            "Filtrer par nom ou code copropriétaire", key="track_search_input"
        )

    df_track_filtered = df_track.copy()
    if selected_track_filter == "Relances en cours (débit > 0)":
        df_track_filtered = df_track_filtered[df_track_filtered["debit_actuel"] > 0]
    elif selected_track_filter == "Soldes régularisés (débit <= 0)":
        df_track_filtered = df_track_filtered[df_track_filtered["debit_actuel"] <= 0]
    elif selected_track_filter == "Sans relance envoyée":
        df_track_filtered = df_track_filtered[df_track_filtered["nb_relances_envoyees"] == 0]

    if search_track:
        df_track_filtered = df_track_filtered[
            df_track_filtered["nom_proprietaire"].str.contains(search_track, case=False, na=False)
            | df_track_filtered["code_proprietaire"].str.contains(
                search_track, case=False, na=False
            )
        ]

    df_track_filtered["Statut Suivi"] = df_track_filtered.apply(_compute_statut_label, axis=1)

    for dc in ["first_relance_date", "last_relance_date"]:
        if dc in df_track_filtered.columns:
            df_track_filtered[dc] = df_track_filtered[dc].apply(_format_date_val)

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
            width="stretch",
            key="btn_download_tracking_csv",
        )


def render_history_log() -> None:
    """Journal chronologique de toutes les relances enregistrées."""
    st.subheader("Journal chronologique de toutes les relances")
    st.caption("Consultez l'historique complet de chaque message avec le texte exact rédigé.")

    all_drafts_hist = load_all_drafts()
    if not all_drafts_hist:
        st.info("Aucun historique disponible.")
        return

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

    for idx, (_, row) in enumerate(df_hist.iterrows()):
        sent_label = row.get("sent_at") or row.get("created_at")
        status_icon = (
            "✓ (Hotmail)"
            if row["status"] in ("draft_imap", "sent")
            else ("⚠️ (Erreur)" if row["status"] == "error" else "📝 (Brouillon)")
        )
        expander_title = (
            f"{status_icon} [{sent_label}] {row['nom_proprietaire']} "
            f"({row.get('debit', 0):.2f} €) : {row.get('subject', '')}"
        )

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

            if st.button(
                "👤 Voir la fiche copro",
                key=f"fiche_{row.get('draft_id', idx)}",
                width="content",
            ):
                target = str(row.get("code_proprietaire") or row.get("nom_proprietaire") or "")
                st.session_state["target_fiche_copro"] = target
                st.switch_page("Pages/Rechercher_Copro.py")
