"""Administration des brouillons de relance."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cptcopro.utils.paths import get_db_path
from cptcopro.Database import get_relance_drafts, mark_relance_draft_status


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


st.title("Administration Relances")
st.caption("Consultez et validez les brouillons avant envoi manuel depuis la boite mail dediee.")

status_filter = st.selectbox(
	"Filtrer par statut",
	options=["tous", "draft_imap", "draft_local", "validated", "sent", "error"],
)
limit = st.slider("Nombre maximum de brouillons", min_value=20, max_value=500, value=150, step=10)

status = None if status_filter == "tous" else status_filter
df = _load_drafts(str(DB_PATH), status, int(limit), _db_cache_key())

if df.empty:
	st.info("Aucun brouillon disponible.")
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
)

draft_ids = df["draft_id"].astype(int).tolist()
selected_draft_id = st.selectbox("Brouillon a inspecter", options=draft_ids)
selected = df[df["draft_id"] == selected_draft_id].iloc[0].to_dict()

st.markdown(f"**Objet**: {selected.get('subject', '')}")
st.text_area("Contenu", value=str(selected.get("body") or ""), height=260, disabled=True)
if selected.get("error_message"):
	st.warning(f"Erreur lors de la creation: {selected.get('error_message')}")

col1, col2 = st.columns(2)
with col1:
	if st.button("Marquer comme valide", type="primary"):
		mark_relance_draft_status(str(DB_PATH), int(selected_draft_id), "validated")
		_load_drafts.clear()
		st.success("Brouillon marque comme valide.")
		st.rerun()
with col2:
	if st.button("Marquer comme envoye"):
		mark_relance_draft_status(str(DB_PATH), int(selected_draft_id), "sent")
		_load_drafts.clear()
		st.success("Brouillon marque comme envoye.")
		st.rerun()

