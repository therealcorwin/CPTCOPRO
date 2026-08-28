"""Configuration des relances email (frequence, mailbox, LLM)."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

try:
	from cptcopro.utils.paths import get_db_path
	from cptcopro.Database import (
		DEFAULT_RELANCE_CONFIG,
		get_relance_config,
		update_relance_config,
		init_relance_config_if_missing,
	)

	DB_PATH = get_db_path()
except ImportError:
	DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"
	DEFAULT_RELANCE_CONFIG = {
		"enabled": 1,
		"frequency_days": 14,
		"sender_name": "Syndic de copropriete",
		"sender_email": "",
		"mailbox_imap_host": "",
		"mailbox_imap_port": 993,
		"mailbox_imap_user": "",
		"mailbox_drafts_folder": "Drafts",
		"mailbox_use_ssl": 1,
		"mailbox_password_env": "RELANCE_MAILBOX_PASSWORD",
		"mailbox_access_token_env": "RELANCE_MAILBOX_ACCESS_TOKEN",
		"llm_provider": "mistral",
		"llm_model": "mistral-small-latest",
		"llm_api_base": "https://api.mistral.ai/v1",
		"llm_api_key_env": "MISTRAL_API_KEY",
		"llm_temperature": 0.4,
		"tone_instruction": "courtois, professionnel et ferme",
	}

	def init_relance_config_if_missing(db_path: str) -> bool:
		return False

	def get_relance_config(db_path: str) -> dict:
		del db_path
		return DEFAULT_RELANCE_CONFIG.copy()

	def update_relance_config(db_path: str, **kwargs) -> bool:
		del db_path, kwargs
		return True


def _db_cache_key(db_path: Path) -> int:
	try:
		return db_path.stat().st_mtime_ns
	except OSError:
		return 0


@st.cache_data(ttl=120, show_spinner=False)
def _load_relance_config(db_path: str, cache_key: int) -> dict:
	del cache_key
	init_relance_config_if_missing(db_path)
	return get_relance_config(db_path)


st.title("Configuration des Relances Email")
st.caption("Parametrez la frequence des relances, la boite mail dediee et le modele LLM.")

db_path_str = str(DB_PATH)
cfg = _load_relance_config(db_path_str, _db_cache_key(DB_PATH))

enabled = bool(int(cfg.get("enabled", 1)))
frequency_days = int(cfg.get("frequency_days", 14) or 14)

st.subheader("Regles de relance")
with st.form("relance_rules_form"):
	enabled_new = st.checkbox(
		"Activer la generation de relances",
		value=enabled,
		help="Si desactive, la page Relance reste consultable mais ne genere pas de brouillons.",
	)
	frequency_new = st.number_input(
		"Frequence minimale entre deux relances (jours)",
		min_value=1,
		max_value=365,
		value=frequency_days,
		step=1,
	)

	sender_name_new = st.text_input(
		"Nom expediteur",
		value=str(cfg.get("sender_name") or DEFAULT_RELANCE_CONFIG["sender_name"]),
	)
	sender_email_new = st.text_input(
		"Email expediteur",
		value=str(cfg.get("sender_email") or ""),
		help="Adresse de la boite mail dediee aux relances.",
	)

	submitted_rules = st.form_submit_button("Enregistrer regles", type="primary")
	if submitted_rules:
		update_relance_config(
			db_path_str,
			enabled=1 if enabled_new else 0,
			frequency_days=int(frequency_new),
			sender_name=sender_name_new.strip(),
			sender_email=sender_email_new.strip(),
		)
		_load_relance_config.clear()
		st.success("Regles de relance enregistrees.")
		st.rerun()


st.subheader("Boite mail dediee (brouillons IMAP)")
with st.form("relance_imap_form"):
	mailbox_imap_host = st.text_input(
		"Serveur IMAP",
		value=str(cfg.get("mailbox_imap_host") or "outlook.office365.com"),
		placeholder="outlook.office365.com",
	)
	mailbox_imap_port = st.number_input(
		"Port IMAP",
		min_value=1,
		max_value=65535,
		value=int(cfg.get("mailbox_imap_port", 993) or 993),
		step=1,
	)
	mailbox_imap_user = st.text_input(
		"Utilisateur IMAP",
		value=str(cfg.get("mailbox_imap_user") or ""),
		placeholder="adresse@hotmail.com",
	)
	mailbox_drafts_folder = st.text_input(
		"Dossier brouillons",
		value=str(cfg.get("mailbox_drafts_folder") or "Drafts"),
	)
	mailbox_use_ssl = st.checkbox(
		"Utiliser SSL",
		value=bool(int(cfg.get("mailbox_use_ssl", 1) or 1)),
	)
	mailbox_password_env = st.text_input(
		"Variable d'environnement pour le mot de passe IMAP",
		value=str(cfg.get("mailbox_password_env") or "RELANCE_MAILBOX_PASSWORD"),
		help="La valeur du mot de passe n'est jamais stockee en base.",
	)
	mailbox_access_token_env = st.text_input(
		"Variable d'environnement du jeton OAuth2 (optionnel)",
		value=str(cfg.get("mailbox_access_token_env") or "RELANCE_MAILBOX_ACCESS_TOKEN"),
		help="Pour Hotmail, le jeton OAuth2 est prioritaire sur le mot de passe et n'est jamais stocke en base.",
	)

	submitted_imap = st.form_submit_button("Enregistrer configuration IMAP", type="primary")
	if submitted_imap:
		update_relance_config(
			db_path_str,
			mailbox_imap_host=mailbox_imap_host.strip(),
			mailbox_imap_port=int(mailbox_imap_port),
			mailbox_imap_user=mailbox_imap_user.strip(),
			mailbox_drafts_folder=mailbox_drafts_folder.strip() or "Drafts",
			mailbox_use_ssl=1 if mailbox_use_ssl else 0,
			mailbox_password_env=mailbox_password_env.strip() or "RELANCE_MAILBOX_PASSWORD",
			mailbox_access_token_env=mailbox_access_token_env.strip() or "RELANCE_MAILBOX_ACCESS_TOKEN",
		)
		_load_relance_config.clear()
		st.success("Configuration IMAP enregistree.")
		st.rerun()

password_env_name = str(cfg.get("mailbox_password_env") or "RELANCE_MAILBOX_PASSWORD")
if os.getenv(password_env_name):
	st.info(f"Mot de passe IMAP detecte dans ${password_env_name}.")
else:
	st.warning(
		f"Mot de passe IMAP non detecte dans ${password_env_name}. "
		"Les brouillons seront enregistres en base locale uniquement."
	)


st.subheader("Generation LLM")
with st.form("relance_llm_form"):
	llm_provider = st.selectbox(
		"Provider",
		options=["mistral", "fallback"],
		index=0 if str(cfg.get("llm_provider") or "mistral") == "mistral" else 1,
	)
	llm_model = st.text_input(
		"Modele",
		value=str(cfg.get("llm_model") or "mistral-small-latest"),
	)
	llm_api_base = st.text_input(
		"Base URL API",
		value=str(cfg.get("llm_api_base") or "https://api.mistral.ai/v1"),
	)
	llm_api_key_env = st.text_input(
		"Variable d'environnement cle API",
		value=str(cfg.get("llm_api_key_env") or "MISTRAL_API_KEY"),
	)
	llm_temperature = st.slider(
		"Temperature",
		min_value=0.0,
		max_value=1.2,
		value=float(cfg.get("llm_temperature", 0.4) or 0.4),
		step=0.05,
	)
	tone_instruction = st.text_area(
		"Instructions de ton",
		value=str(cfg.get("tone_instruction") or "courtois, professionnel et ferme"),
		height=100,
	)

	submitted_llm = st.form_submit_button("Enregistrer configuration LLM", type="primary")
	if submitted_llm:
		update_relance_config(
			db_path_str,
			llm_provider=llm_provider,
			llm_model=llm_model.strip(),
			llm_api_base=llm_api_base.strip(),
			llm_api_key_env=llm_api_key_env.strip() or "MISTRAL_API_KEY",
			llm_temperature=float(llm_temperature),
			tone_instruction=tone_instruction.strip() or "courtois, professionnel et ferme",
		)
		_load_relance_config.clear()
		st.success("Configuration LLM enregistree.")
		st.rerun()

if os.getenv(str(cfg.get("llm_api_key_env") or "MISTRAL_API_KEY")):
	st.info("Cle API LLM detectee dans l'environnement.")
else:
	st.warning("Cle API LLM absente: la generation utilisera un modele de texte local (fallback).")

