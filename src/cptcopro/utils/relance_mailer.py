"""Outils pour generer et sauvegarder des brouillons de relance email."""

from __future__ import annotations

import imaplib
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from contextlib import suppress
from email.message import EmailMessage
from typing import Any

from loguru import logger

from cptcopro.utils.hotmail_oauth import get_hotmail_access_token

logger = logger.bind(type_log="RELANCE")


def _build_subject(nom_proprietaire: str, date_origin: str | None) -> str:
    date_label = date_origin or "periode en cours"
    return f"Relance charges copropriete - {nom_proprietaire} ({date_label})"


class _SafePlaceholderDict(dict[str, Any]):
    """Dict qui laisse le placeholder tel quel s'il est absent des donnees."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _build_placeholder_context(
    data: dict[str, Any],
    config: dict[str, Any],
) -> _SafePlaceholderDict:
    debit = float(data.get("debit") or 0.0)
    return _SafePlaceholderDict(
        nom_proprietaire=str(data.get("nom_proprietaire") or ""),
        code_proprietaire=str(data.get("code_proprietaire") or ""),
        debit=debit,
        debit_fmt=f"{debit:.2f} EUR",
        num_apt=str(data.get("num_apt") or "NA"),
        type_apt=str(data.get("type_apt") or "NA"),
        date_origin=str(data.get("date_origin") or ""),
        sender_name=str(config.get("sender_name") or ""),
        sender_email=str(config.get("sender_email") or ""),
        tone_instruction=str(config.get("tone_instruction") or ""),
        frequency_days=str(config.get("frequency_days") or ""),
    )


def render_relance_template(
    template: dict[str, Any],
    data: dict[str, Any],
    config: dict[str, Any],
) -> tuple[str, str]:
    """Genere (subject, body) a partir d'un template parametrable et des donnees du coproprietaire.

    Placeholders disponibles: nom_proprietaire, code_proprietaire, debit, debit_fmt,
    num_apt, type_apt, date_origin, sender_name, sender_email, tone_instruction,
    frequency_days.
    """
    context = _build_placeholder_context(data, config)
    subject = str(template.get("subject_template") or "").format_map(context)
    body = str(template.get("body_template") or "").format_map(context)
    return subject, body


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


def tester_connexion_mistral(
    api_key: str | None = None,
    model: str = "mistral-small-latest",
    api_base: str = "https://api.mistral.ai/v1",
) -> tuple[bool, str]:
    """Teste la validité de la clé API Mistral et la disponibilité du modèle."""
    key = api_key if api_key is not None else os.getenv("MISTRAL_API_KEY", "")
    key = key.strip() if key else ""
    if not key:
        return (
            False,
            "Clé API absente. Définissez MISTRAL_API_KEY dans votre fichier .env ou dans le formulaire.",
        )

    api_base_url = api_base.rstrip("/")
    if not api_base_url.lower().startswith("https://"):
        return False, f"URL API invalide : le schéma doit être https:// (reçu : '{api_base_url}')"
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 30,
        "messages": [
            {
                "role": "user",
                "content": "Réponds uniquement par 'Connexion Mistral opérationnelle.'",
            }
        ],
    }
    req = urllib.request.Request(
        url=f"{api_base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        # Schéma https:// validé avant construction de la requête
        with urllib.request.urlopen(req, timeout=15) as response:  # nosec B310
            raw = response.read().decode("utf-8")
        content = json.loads(raw)
        rep = content.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return True, f"Connexion réussie avec {model} ! Réponse: '{rep}'"
    except urllib.error.HTTPError as http_err:
        err_msg = http_err.read().decode("utf-8", errors="ignore")
        return False, f"Erreur HTTP {http_err.code} ({http_err.reason}) : {err_msg}"
    except Exception as exc:
        return False, f"Erreur de connexion Mistral : {exc}"


def generate_relance_draft_with_llm(
    data: dict[str, Any],
    config: dict[str, Any],
    template: dict[str, Any] | None = None,
) -> tuple[str, str, str, str]:
    """Génère (subject, body, provider, model) avec Mistral si possible.

    Si `template` est fourni, son `tone_instruction` prévaut sur celui de la
    configuration globale, et son `body_template` sert de guide de contenu
    (éléments à mentionner) pour l'assistant, sans être recopié tel quel.
    En absence de clé API ou en cas d'erreur, un contenu de secours est généré localement.
    """
    provider = str(config.get("llm_provider") or "mistral").lower()
    model = str(config.get("llm_model") or "mistral-small-latest")
    template_tone = str((template or {}).get("tone_instruction") or "").strip()
    tone_instruction = template_tone or str(
        config.get("tone_instruction") or "courtois, professionnel et ferme"
    )

    context = _build_placeholder_context(data, config)
    template_subject = str((template or {}).get("subject_template") or "").strip()
    if template_subject:
        subject = template_subject.format_map(context)
    else:
        subject = _build_subject(
            str(data.get("nom_proprietaire") or "copropriétaire"),
            str(data.get("date_origin") or ""),
        )

    if provider != "mistral":
        return (subject, _fallback_body(data, tone_instruction), provider, model)

    api_base = str(config.get("llm_api_base") or "https://api.mistral.ai/v1").rstrip("/")
    if not api_base.lower().startswith("https://"):
        logger.warning(
            f"URL API Mistral invalide (schéma non-https) : '{api_base}'. Utilisation du fallback."
        )
        return (subject, _fallback_body(data, tone_instruction), provider, model)
    api_key_env = str(config.get("llm_api_key_env") or "MISTRAL_API_KEY")
    api_key = os.getenv(api_key_env)
    if not api_key:
        logger.warning(
            f"Clé API '{api_key_env}' introuvable dans l'environnement. "
            "Génération du brouillon de secours local (fallback)."
        )
        return (subject, _fallback_body(data, tone_instruction), provider, model)

    try:
        temperature = float(config.get("llm_temperature") or 0.4)
    except (TypeError, ValueError):
        temperature = 0.4
    copro_nom = str(data.get("nom_proprietaire") or "")
    debit = float(data.get("debit") or 0.0)
    num_apt = str(data.get("num_apt") or "NA")
    type_apt = str(data.get("type_apt") or "NA")
    date_origin = str(data.get("date_origin") or "")

    system_prompt = (
        "Tu es un assistant de syndic de copropriété. "
        "Tu rédiges des relances de paiement en français, sans menace, conformes et factuelles."
    )
    template_body = str((template or {}).get("body_template") or "").strip()
    content_guidance = ""
    if template_body:
        rendered_guidance = template_body.format_map(context)
        content_guidance = (
            "- Structure et éléments à inclure (guide, ne pas recopier tel quel):\n"
            f"{rendered_guidance}\n"
        )
    user_prompt = (
        "Rédige un email de relance de charges de copropriété.\n"
        "Contraintes:\n"
        f"- Ton: {tone_instruction}.\n"
        "- Ne pas inventer de pénalités ni de références légales non précisées.\n"
        "- Message concis (120-220 mots), clair et actionnable.\n"
        "- Inclure une invitation à contacter le syndic en cas de désaccord.\n"
        f"{content_guidance}"
        "- Retourner uniquement le corps de mail (sans objet/sujet).\n\n"
        "Données du copropriétaire:\n"
        f"Nom: {copro_nom}\n"
        f"Code copropriétaire: {data.get('code_proprietaire', '')}\n"
        f"Lot: {num_apt} ({type_apt})\n"
        f"Date de situation: {date_origin}\n"
        f"Débit constaté: {debit:.2f} EUR\n"
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
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        # Schéma https:// validé avant construction de la requête
        with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310
            raw = response.read().decode("utf-8")
        content = json.loads(raw)
        body = content.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if body:
            logger.success(f"Brouillon généré avec succès par Mistral pour {copro_nom}.")
            return (subject, body, "mistral", model)
        else:
            logger.warning(f"Réponse vide reçue de Mistral pour {copro_nom}, utilisation fallback.")
            body = _fallback_body(data, tone_instruction)
            return (subject, body, provider, model)
    except urllib.error.HTTPError as http_err:
        err_msg = http_err.read().decode("utf-8", errors="ignore")
        logger.error(f"Erreur HTTP API Mistral ({http_err.code}): {http_err.reason} - {err_msg}")
        body = _fallback_body(data, tone_instruction)
        return (subject, body, provider, model)
    except Exception as exc:
        logger.error(f"Erreur lors de la génération avec Mistral : {exc}")
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


def _connect_and_authenticate_imap(config: dict[str, Any]) -> imaplib.IMAP4:
    """Établit la connexion IMAP et réalise l'authentification (OAuth2 ou Mot de passe)."""
    host = str(config.get("mailbox_imap_host") or "outlook.office365.com").strip()
    user = str(config.get("mailbox_imap_user") or "").strip()
    use_ssl = bool(int(config.get("mailbox_use_ssl") or 1))
    port = int(config.get("mailbox_imap_port") or 993)
    password_env = str(config.get("mailbox_password_env") or "RELANCE_MAILBOX_PASSWORD").strip()
    password = os.getenv(password_env)
    access_token_env = str(
        config.get("mailbox_access_token_env") or "RELANCE_MAILBOX_ACCESS_TOKEN"
    ).strip()
    configured_access_token = os.getenv(access_token_env)
    has_invalid_configured_token = bool(
        configured_access_token and configured_access_token.count(".") != 2
    )
    access_token = None if has_invalid_configured_token else configured_access_token
    if not access_token:
        cached_access_token = get_hotmail_access_token(config)
        if cached_access_token:
            access_token = cached_access_token

    if not host or not user:
        raise ValueError(
            "Configuration IMAP incomplète : serveur hôte ou adresse utilisateur manquante."
        )
    if not access_token and not password:
        raise ValueError(
            f"Authentification IMAP absente : aucune autorisation OAuth2 valide trouvée "
            f"et mot de passe (${password_env}) non défini. Veuillez cliquer sur 'Initialiser l'authentification Hotmail' "
            f"dans la page Configuration Relances."
        )

    client: imaplib.IMAP4 | imaplib.IMAP4_SSL
    if use_ssl:
        client = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())
    else:
        client = imaplib.IMAP4(host, port)

    auth_error = None
    if access_token:
        auth_string = f"user={user}\x01auth=Bearer {access_token}\x01\x01"
        if hasattr(client, "authenticate"):
            try:
                client.authenticate("XOAUTH2", lambda _: auth_string.encode("ascii"))
                return client
            except (imaplib.IMAP4.error, Exception) as exc:
                auth_error = RuntimeError(
                    f"Authentification OAuth2 Hotmail refusée pour {user}. Le jeton est peut-être expiré "
                    f"ou ne possède pas la permission IMAP.AccessAsUser.All."
                )
                if not password:
                    raise auth_error from exc
        else:
            auth_error = RuntimeError("Client IMAP ne supporte pas l'authentification XOAUTH2.")

    if auth_error is not None or not access_token:
        try:
            client.login(user, password or "")
            return client
        except imaplib.IMAP4.error as exc:
            if auth_error is not None:
                raise RuntimeError(
                    f"Authentification OAuth2 et mot de passe Hotmail refusées. "
                    f"OAuth2: {auth_error}. Mot de passe: utilisez un mot de passe "
                    f"d'application Microsoft ou réinitialisez OAuth2."
                ) from exc
            raise RuntimeError(
                "Authentification Hotmail refusée. Pour Hotmail/Outlook, le mot de passe habituel "
                "est bloqué par Microsoft : utilisez un mot de passe d'application ou l'authentification OAuth2."
            ) from exc

    return client


_IMAP_LIST_REGEX = re.compile(
    r'\((?P<flags>[^\)]*)\)\s+(?P<delimiter>NIL|"[^"]*"|\S+)\s+(?P<name>.+)$'
)


def _parse_imap_list_response(item_str: str) -> str:
    """Extrait proprement le nom d'un dossier depuis une réponse IMAP LIST selon RFC 3501."""
    item_str = item_str.strip()
    match = _IMAP_LIST_REGEX.search(item_str)
    if match:
        raw_name = match.group("name").strip()
        if raw_name.startswith('"') and raw_name.endswith('"') and len(raw_name) >= 2:
            raw_name = raw_name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        return raw_name

    # Fallback : séparation tolérante par slash ou guillemets
    parts = item_str.rsplit(' "/" ', 1)
    if len(parts) == 2:
        return parts[1].strip('" ')

    return item_str.strip('" ')


def tester_connexion_imap(config: dict[str, Any]) -> tuple[bool, str, list[str]]:
    """Teste la connexion IMAP, l'authentification et liste les dossiers distants."""
    client = None
    try:
        client = _connect_and_authenticate_imap(config)
        typ, folder_data = client.list()
        folders: list[str] = []
        if typ == "OK" and folder_data:
            for item in folder_data:
                if isinstance(item, bytes):
                    item_str = item.decode("utf-8", errors="ignore")
                    folder_name = _parse_imap_list_response(item_str)
                    if folder_name:
                        folders.append(folder_name)

        user = str(config.get("mailbox_imap_user") or "")
        return (
            True,
            f"Connexion IMAP réussie pour '{user}' ! {len(folders)} dossier(s) détecté(s).",
            folders,
        )
    except Exception as exc:
        return False, f"Échec de la connexion IMAP : {exc}", []
    finally:
        if client is not None:
            with suppress(Exception):
                client.logout()


def save_draft_to_imap(config: dict[str, Any], message: EmailMessage) -> str:
    """Enregistre un brouillon dans le dossier Drafts/Brouillons IMAP et retourne un identifiant."""
    folder = str(config.get("mailbox_drafts_folder") or "Drafts").strip()
    client = _connect_and_authenticate_imap(config)

    try:
        internaldate = imaplib.Time2Internaldate(time.time())
        # Tenter d'abord le dossier configuré, puis les dossiers alternatifs courants (Drafts / Brouillons)
        candidate_folders = [folder]
        for alt in ["Drafts", "Brouillons", "Draft", "INBOX.Drafts", "INBOX.Brouillons"]:
            if alt not in candidate_folders:
                candidate_folders.append(alt)

        last_error = None
        for candidate in candidate_folders:
            try:
                typ, response = client.append(
                    candidate, "\\Draft", internaldate, message.as_bytes()
                )
                if typ == "OK":
                    logger.success(
                        f"Brouillon déposé avec succès dans le dossier IMAP '{candidate}'."
                    )
                    if response and response[0]:
                        return response[0].decode("utf-8", errors="ignore")
                    return "imap-append-ok"
                else:
                    details = (
                        response[0].decode("utf-8", errors="ignore")
                        if response and response[0]
                        else ""
                    )
                    last_error = f"Réponse APPEND IMAP sur '{candidate}': {details}"
            except Exception as e:
                last_error = str(e)
                continue

        raise RuntimeError(
            f"Échec APPEND IMAP vers les dossiers ({', '.join(candidate_folders)}): {last_error}"
        )
    finally:
        with suppress(Exception):
            client.logout()


def generer_brouillons_relances(
    deposer_imap: bool = False,
    force_llm: bool | None = None,
) -> dict[str, Any]:
    """Génère automatiquement les brouillons de relance pour tous les copropriétaires dus.

    Fonction autonome orchestrable en CLI (main.py --auto-relance-drafts) ou via tâche planifiée.

    Parameters:
        deposer_imap: Si True, dépose également chaque brouillon dans le dossier IMAP Drafts.
        force_llm: Si bool, force l'utilisation (ou non) de Mistral AI. Si None, se base sur la config et le template.

    Returns:
        Dictionnaire récapitulatif contenant:
        - total_dus: nombre total de comptes éligibles
        - generes: nombre de brouillons générés et persistés
        - deposes_imap: nombre de brouillons déposés avec succès sur IMAP
        - erreurs: liste des messages d'erreurs éventuels
        - draft_ids: liste des identifiants de brouillons créés
    """
    from cptcopro.Database import (
        get_relance_config,
        list_relance_templates,
        list_relances_due,
        mark_relance_draft_status,
        save_relance_draft,
    )

    cfg = get_relance_config()
    enabled = bool(int(cfg.get("enabled", 1)))
    if not enabled:
        logger.warning("Génération de relances désactivée dans la configuration.")
        return {
            "total_dus": 0,
            "generes": 0,
            "deposes_imap": 0,
            "erreurs": ["Relances désactivées dans la configuration"],
            "draft_ids": [],
        }

    frequency_days = int(cfg.get("frequency_days", 14) or 14)
    due_rows = list_relances_due(frequency_days)
    if not due_rows:
        logger.info("Aucun copropriétaire éligible à la relance pour le moment.")
        return {
            "total_dus": 0,
            "generes": 0,
            "deposes_imap": 0,
            "erreurs": [],
            "draft_ids": [],
        }

    templates = list_relance_templates()
    default_template = next(
        (t for t in templates if t.get("is_default")),
        templates[0] if templates else None,
    )

    results: dict[str, Any] = {
        "total_dus": len(due_rows),
        "generes": 0,
        "deposes_imap": 0,
        "erreurs": [],
        "draft_ids": [],
    }

    sender_name = str(cfg.get("sender_name") or "Syndic de copropriété")
    sender_email = str(cfg.get("sender_email") or "")

    for row in due_rows:
        code_copro = str(row.get("code_proprietaire") or "")
        try:
            email_to = str(row.get("email_to") or "").strip()
            if not email_to:
                logger.info(f"Copropriétaire {code_copro} ignoré : aucune adresse email de contact.")
                continue

            template = default_template or {}
            use_llm = (
                force_llm
                if force_llm is not None
                else (
                    str(cfg.get("llm_provider") or "mistral") == "mistral"
                    or template.get("generation_mode") == "llm"
                )
            )

            if use_llm:
                subject, body, provider, model = generate_relance_draft_with_llm(
                    row, cfg, template=template
                )
            else:
                subject, body = render_relance_template(template, row, cfg)
                provider, model = ("template", template.get("name", "Standard"))

            draft_id = save_relance_draft(
                code_proprietaire=code_copro,
                nom_proprietaire=str(row.get("nom_proprietaire") or ""),
                debit=float(row.get("debit") or 0.0),
                email_to=email_to,
                subject=subject,
                body=body,
                llm_provider=provider,
                llm_model=model,
                status="draft_local",
            )
            results["generes"] += 1
            results["draft_ids"].append(draft_id)

            if deposer_imap:
                try:
                    msg = build_email_message(sender_email, sender_name, email_to, subject, body)
                    remote_id = save_draft_to_imap(cfg, msg)
                    mark_relance_draft_status(draft_id, "draft_imap", remote_draft_id=remote_id)
                    results["deposes_imap"] += 1
                except Exception as exc_imap:
                    mark_relance_draft_status(draft_id, "error", error_message=str(exc_imap))
                    logger.error(f"Échec dépôt IMAP pour {email_to}: {exc_imap}")
                    results["erreurs"].append(f"IMAP {email_to}: {exc_imap}")

        except Exception as exc:
            err = f"Erreur génération pour {code_copro}: {exc}"
            logger.error(err)
            results["erreurs"].append(err)

    logger.info(
        f"Génération terminée : {results['generes']}/{results['total_dus']} brouillons générés, "
        f"{results['deposes_imap']} déposés sur IMAP, {len(results['erreurs'])} erreur(s)."
    )
    return results

