"""Generation des brouillons de relance pour coproprietaires en debit."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cptcopro.utils.paths import get_db_path
from cptcopro.Database import (
	get_relance_config,
	list_relances_due,
	upsert_relance_destinataire,
	save_relance_draft,
)
from cptcopro.utils.relance_mailer import (
	generate_relance_draft_with_llm,
	build_email_message,
	save_draft_to_imap,
)


DB_PATH = get_db_path()


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


st.title("Relances et Notifications")
st.caption("Genere des brouillons email pour les coproprietaires actuellement en debit.")

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

edited = st.data_editor(
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
	for row in edited.to_dict("records"):
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


st.subheader("Coproprietaires dus pour relance")
due_only = due_df[due_df["due"] == 1].copy()
if due_only.empty:
	st.info("Tous les coproprietaires en alerte ont deja une relance recente.")
	st.stop()

st.dataframe(
	due_only[
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
	],
	width="stretch",
	hide_index=True,
)

selectable_codes = due_only["code_proprietaire"].astype(str).tolist()
selected_codes = st.multiselect(
	"Selectionner les coproprietaires pour generer les brouillons",
	options=selectable_codes,
	default=selectable_codes,
)

if st.button("Generer les brouillons", type="primary", disabled=not selected_codes):
	if not bool(int(cfg.get("enabled", 1) or 1)):
		st.error("Generation desactivee. Activez-la dans la page Configuration Relances.")
		st.stop()

	with st.spinner("Generation des brouillons en cours..."):
		nb_ok = 0
		nb_local = 0
		nb_imap = 0
		nb_error = 0

		for code in selected_codes:
			row = due_only[due_only["code_proprietaire"].astype(str) == str(code)]
			if row.empty:
				continue

			payload = {str(k): v for k, v in row.iloc[0].to_dict().items()}
			email_to = str(payload.get("email_to") or "").strip()
			if not email_to:
				nb_error += 1
				continue

			subject, body, provider, model = generate_relance_draft_with_llm(payload, cfg)
			status = "draft_local"
			remote_id = None
			error_message = None

			try:
				message = build_email_message(
					sender_email=str(cfg.get("sender_email") or ""),
					sender_name=str(cfg.get("sender_name") or ""),
					to_email=email_to,
					subject=subject,
					body=body,
				)
				remote_id = save_draft_to_imap(cfg, message)
				status = "draft_imap"
				nb_imap += 1
			except Exception as exc:
				status = "draft_local"
				error_message = str(exc)
				nb_local += 1

			save_relance_draft(
				str(DB_PATH),
				code_proprietaire=str(payload.get("code_proprietaire") or ""),
				nom_proprietaire=str(payload.get("nom_proprietaire") or ""),
				debit=float(payload.get("debit") or 0.0),
				email_to=email_to,
				subject=subject,
				body=body,
				llm_provider=provider,
				llm_model=model,
				status=status,
				remote_draft_id=remote_id,
				error_message=error_message,
			)
			nb_ok += 1

	_load_due_data.clear()
	st.success(
		f"Brouillons generes: {nb_ok}. "
		f"IMAP: {nb_imap}. "
		f"Local uniquement: {nb_local}. "
		f"Erreurs destinataire: {nb_error}."
	)
	st.rerun()

