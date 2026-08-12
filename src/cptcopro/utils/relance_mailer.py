"""Outils pour generer et sauvegarder des brouillons de relance email."""

from __future__ import annotations

import json
import os
import ssl
import time
import imaplib
import urllib.request
import urllib.error
from email.message import EmailMessage
from typing import Any


def _build_subject(nom_proprietaire: str, date_origin: str | None) -> str:
    date_label = date_origin or "periode en cours"
    return f"Relance charges copropriete - {nom_proprietaire} ({date_label})"


def _fallback_body(data: dict[str, Any], tone_instruction: str) -> str:
    nom = data.get("nom_proprietaire") or "Madame, Monsieur"
    debit = float(data.get("debit") or 0.0)
    date_origin = data.get("date_origin") or "la derniere situation"
    return (
        f"Bonjour {nom},\n\n"
        "Nous vous contactons concernant votre compte coproprietaire.\n"
        f"A la date du {date_origin}, un solde debiteur de {debit:.2f} EUR est constate.\n\n"
        "Nous vous remercions de proceder au reglement dans les meilleurs delais "
        "ou de contacter l'administration si vous constatez une anomalie.\n\n"
        f"Ton attendu: {tone_instruction}.\n\n"
        "Cordialement,\n"
        "Le syndic"
    )


def generate_relance_draft_with_llm(
    data: dict[str, Any],
    config: dict[str, Any],
) -> tuple[str, str, str, str]:
    """Genere (subject, body, provider, model) avec Mistral si possible.

    En absence de cle API, un contenu de secours est genere localement.
    """
    provider = str(config.get("llm_provider") or "mistral").lower()
    model = str(config.get("llm_model") or "mistral-small-latest")
    tone_instruction = str(
        config.get("tone_instruction") or "courtois, professionnel et ferme"
    )
    subject = _build_subject(
        str(data.get("nom_proprietaire") or "coproprietaire"),
        str(data.get("date_origin") or ""),
    )

    if provider != "mistral":
        return (subject, _fallback_body(data, tone_instruction), provider, model)

    api_base = str(config.get("llm_api_base") or "https://api.mistral.ai/v1").rstrip("/")
    api_key_env = str(config.get("llm_api_key_env") or "MISTRAL_API_KEY")
    api_key = os.getenv(api_key_env)
    if not api_key:
        return (subject, _fallback_body(data, tone_instruction), provider, model)

    temperature = float(config.get("llm_temperature") or 0.4)
    copro_nom = str(data.get("nom_proprietaire") or "")
    debit = float(data.get("debit") or 0.0)
    num_apt = str(data.get("num_apt") or "NA")
    type_apt = str(data.get("type_apt") or "NA")
    date_origin = str(data.get("date_origin") or "")

    system_prompt = (
        "Tu es un assistant de syndic. "
        "Tu rediges des relances de paiement en francais, sans menace, conforme et factuelle."
    )
    user_prompt = (
        "Redige un email de relance de charges de copropriete.\\n"
        "Contraintes:\\n"
        f"- Ton: {tone_instruction}.\\n"
        "- Ne pas inventer de penalites ni de references legales.\\n"
        "- Message concis (120-220 mots), clair et actionnable.\\n"
        "- Inclure une invitation a contacter le syndic en cas de desaccord.\\n"
        "- Retourner uniquement le corps de mail (sans sujet).\\n\\n"
        "Donnees coproprietaire:\\n"
        f"Nom: {copro_nom}\\n"
        f"Code copro: {data.get('code_proprietaire', '')}\\n"
        f"Lot: {num_apt} ({type_apt})\\n"
        f"Date situation: {date_origin}\\n"
        f"Debit constate: {debit:.2f} EUR\\n"
    )

    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = urllib.request.Request(
        url=f"{api_base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
        content = json.loads(raw)
        body = (
            content.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not body:
            body = _fallback_body(data, tone_instruction)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, ValueError):
        body = _fallback_body(data, tone_instruction)

    return (subject, body, provider, model)


def build_email_message(
    sender_email: str,
    sender_name: str,
    to_email: str,
    subject: str,
    body: str,
) -> EmailMessage:
    """Construit un email RFC822 pret a etre stocke en brouillon."""
    msg = EmailMessage()
    from_header = sender_email.strip()
    if sender_name.strip():
        from_header = f"{sender_name.strip()} <{sender_email.strip()}>"
    msg["From"] = from_header
    msg["To"] = to_email.strip()
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def save_draft_to_imap(config: dict[str, Any], message: EmailMessage) -> str:
    """Enregistre un brouillon dans le dossier Drafts IMAP et retourne un identifiant."""
    host = str(config.get("mailbox_imap_host") or "").strip()
    user = str(config.get("mailbox_imap_user") or "").strip()
    folder = str(config.get("mailbox_drafts_folder") or "Drafts").strip()
    use_ssl = bool(int(config.get("mailbox_use_ssl") or 1))
    port = int(config.get("mailbox_imap_port") or 993)
    password_env = str(config.get("mailbox_password_env") or "RELANCE_MAILBOX_PASSWORD").strip()
    password = os.getenv(password_env)

    if not host or not user:
        raise ValueError("Configuration IMAP incomplete (host/user manquant)")
    if not password:
        raise ValueError(f"Mot de passe IMAP absent dans la variable env {password_env}")

    if use_ssl:
        client = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())
    else:
        client = imaplib.IMAP4(host, port)

    try:
        client.login(user, password)
        internaldate = imaplib.Time2Internaldate(time.time())
        typ, response = client.append(folder, "\\Draft", internaldate, message.as_bytes())
        if typ != "OK":
            details = response[0].decode("utf-8") if response and response[0] else ""
            raise RuntimeError(f"Echec APPEND IMAP vers {folder}: {details}")

        if response and response[0]:
            return response[0].decode("utf-8", errors="ignore")
        return "imap-append-ok"
    finally:
        try:
            client.logout()
        except Exception:
            pass
