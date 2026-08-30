"""Administration et contrôle des brouillons de relance."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cptcopro.utils.paths import get_db_path
from cptcopro.Database import get_relance_drafts, mark_relance_draft_status
from cptcopro.utils.ui_components import render_header


DB_PATH = get_db_path()


def _db_cache_key() -> int:
    try:
        return DB_PATH.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=60, show_spinner=False)
def _load_drafts(db_path: str, status: str | None, limit: int, cache_key: int) -> pd.DataFrame:
    del cache_key
    rows = get_relance_drafts(db_path, status=status, limit=limit)
    return pd.DataFrame(rows)


render_header(
    "🛡️ Administration des Relances",
    "Consultez et contrôlez les statuts des brouillons avant expédition manuelle",
)

col_f1, col_f2 = st.columns([2, 1], gap="medium")
with col_f1:
    status_filter = st.selectbox(
        "Filtrer par statut :",
        options=["tous", "draft_imap", "draft_local", "validated", "sent", "error"],
        format_func=lambda s: "Tous" if s == "tous" else s,
    )
with col_f2:
    limit = st.slider("Nombre max", min_value=20, max_value=500, value=150, step=10)

status = None if status_filter == "tous" else status_filter
df = _load_drafts(str(DB_PATH), status, int(limit), _db_cache_key())

if df.empty:
    st.info("ℹ️ Aucun brouillon ne correspond à ce filtre.")
    st.stop()

st.dataframe(
    df[
        [
            "draft_id",
            "created_at",
            "code_proprietaire",
            "nom_proprietaire",
            "debit",
            "email_to",
            "status",
            "llm_model",
            "remote_draft_id",
        ]
    ],
    width="stretch",
    hide_index=True,
    column_config={
        "draft_id": st.column_config.NumberColumn("ID", width="small"),
        "created_at": st.column_config.TextColumn("Créé le", width="medium"),
        "code_proprietaire": st.column_config.TextColumn("Code", width="small"),
        "nom_proprietaire": st.column_config.TextColumn("Copropriétaire", width="medium"),
        "debit": st.column_config.NumberColumn("Débit (€)", format="%.2f €", width="small"),
        "email_to": st.column_config.TextColumn("Email", width="medium"),
        "status": st.column_config.TextColumn("Statut", width="small"),
        "llm_model": st.column_config.TextColumn("Modèle IA", width="small"),
        "remote_draft_id": st.column_config.TextColumn("ID IMAP", width="small"),
    },
)

st.divider()

draft_ids = df["draft_id"].astype(int).tolist()
selected_draft_id = st.selectbox("Sélectionnez un brouillon à inspecter :", options=draft_ids)
selected = df[df["draft_id"] == selected_draft_id].iloc[0].to_dict()

st.markdown(f"**Objet :** {selected.get('subject', '')}")
st.text_area("Contenu du message", value=str(selected.get("body") or ""), height=200, disabled=True)
if selected.get("error_message"):
    st.warning(f"⚠️ Erreur enregistrée : {selected.get('error_message')}")

col1, col2 = st.columns(2, gap="medium")
with col1:
    if st.button("✓ Marquer comme Validé", type="primary", use_container_width=True):
        mark_relance_draft_status(str(DB_PATH), int(selected_draft_id), "validated")
        _load_drafts.clear()
        st.toast("Brouillon marqué comme validé", icon="✅")
        st.rerun()
with col2:
    if st.button("📬 Marquer comme Envoyé", use_container_width=True):
        mark_relance_draft_status(str(DB_PATH), int(selected_draft_id), "sent")
        _load_drafts.clear()
        st.toast("Brouillon marqué comme envoyé", icon="📬")
        st.rerun()
