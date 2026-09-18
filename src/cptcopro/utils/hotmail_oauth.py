"""Authentification OAuth2 Microsoft pour l'acces IMAP Hotmail."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import msal

from cptcopro.utils.paths import get_data_dir, init_env

DEFAULT_CLIENT_ID_ENV = "RELANCE_MAILBOX_CLIENT_ID"
DEFAULT_AUTHORITY = "https://login.microsoftonline.com/consumers"
DEFAULT_SCOPES = [
    "https://outlook.office.com/IMAP.AccessAsUser.All",
]


def get_token_cache_path() -> Path:
    """Retourne le fichier de cache OAuth2 hors du depot Git."""
    cache_dir = get_data_dir() / "oauth"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cast(Path, cache_dir / "msal_token_cache.json")


def _load_cache(cache_path: Path) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if cache_path.exists():
        try:
            cache.deserialize(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache_path.unlink(missing_ok=True)
    return cache


def _save_cache(cache: msal.SerializableTokenCache, cache_path: Path) -> None:
    if cache.has_state_changed:
        cache_path.write_text(cache.serialize(), encoding="utf-8")


def verifier_statut_token_hotmail(
    config: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Vérifie si un token Hotmail OAuth2 valide est présent dans le cache ou renouvelable."""
    config = config or {}
    init_env()
    client_id_env = str(config.get("mailbox_client_id_env") or DEFAULT_CLIENT_ID_ENV).strip()
    client_id = os.getenv(client_id_env, "").strip()
    if not client_id:
        return False, f"Variable d'environnement client ID '{client_id_env}' non définie dans .env."

    authority = str(config.get("mailbox_oauth_authority") or DEFAULT_AUTHORITY).strip()
    scopes = list(config.get("mailbox_oauth_scopes") or DEFAULT_SCOPES)
    cache_path = Path(str(config.get("mailbox_oauth_cache_path") or get_token_cache_path()))
    if not cache_path.exists():
        return False, "Aucun token trouvé en cache (autorisation requise)."

    cache = _load_cache(cache_path)
    app = msal.PublicClientApplication(
        client_id,
        authority=authority,
        token_cache=cache,
    )
    accounts = app.get_accounts()
    if not accounts:
        return False, "Aucun compte associé dans le cache (réinitialisation nécessaire)."

    result = app.acquire_token_silent(scopes, account=accounts[0])
    if isinstance(result, dict) and result.get("access_token"):
        username = accounts[0].get("username") or "compte inconnu"
        return True, f"Token valide pour {username}"
    return False, "Token expiré ou impossible à renouveler silencieusement."


def demarrer_device_flow_microsoft(
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Initie le flux d'autorisation Device Code Microsoft et retourne les informations pour l'UI."""
    config = config or {}
    init_env()
    client_id_env = str(config.get("mailbox_client_id_env") or DEFAULT_CLIENT_ID_ENV).strip()
    client_id = os.getenv(client_id_env, "").strip()
    if not client_id:
        raise ValueError(
            f"Variable {client_id_env} absente. Renseignez l'identifiant client Azure / Microsoft dans le fichier .env."
        )

    authority = str(config.get("mailbox_oauth_authority") or DEFAULT_AUTHORITY).strip()
    scopes = list(config.get("mailbox_oauth_scopes") or DEFAULT_SCOPES)
    cache_path = Path(str(config.get("mailbox_oauth_cache_path") or get_token_cache_path()))
    cache = _load_cache(cache_path)
    app = msal.PublicClientApplication(
        client_id,
        authority=authority,
        token_cache=cache,
    )
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise RuntimeError(
            "Impossible d'initier le flux Device Code Microsoft: "
            + json.dumps(flow, ensure_ascii=False)
        )
    return cast(dict[str, Any], flow)


def valider_device_flow_microsoft(
    flow: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Attend la validation du Device Flow par l'utilisateur et persiste le token."""
    config = config or {}
    init_env()
    client_id_env = str(config.get("mailbox_client_id_env") or DEFAULT_CLIENT_ID_ENV).strip()
    client_id = os.getenv(client_id_env, "").strip()
    if not client_id:
        return False, f"Variable {client_id_env} absente."

    authority = str(config.get("mailbox_oauth_authority") or DEFAULT_AUTHORITY).strip()
    cache_path = Path(str(config.get("mailbox_oauth_cache_path") or get_token_cache_path()))
    cache = _load_cache(cache_path)
    app = msal.PublicClientApplication(
        client_id,
        authority=authority,
        token_cache=cache,
    )

    result = app.acquire_token_by_device_flow(flow)
    _save_cache(cache, cache_path)

    if isinstance(result, dict) and result.get("access_token"):
        return True, "Authentification Hotmail OAuth2 réussie et enregistrée dans le cache."

    error_desc = "Autorisation non complétée ou réponse invalide de Microsoft."
    if isinstance(result, dict):
        error_desc = (
            result.get("error_description")
            or result.get("error")
            or "Autorisation non complétée ou expirée."
        )
    return False, f"Échec de l'autorisation : {error_desc}"


def get_hotmail_access_token(
    config: dict[str, Any] | None = None,
    *,
    interactive: bool = False,
    message_callback: Callable[[str], None] | None = None,
) -> str | None:
    """Retourne un token valide depuis le cache, ou lance l'autorisation initiale.

    L'autorisation interactive est necessaire une seule fois. Les appels suivants
    utilisent le cache MSAL et renouvellent le token silencieusement.
    """
    config = config or {}
    init_env()
    client_id_env = str(config.get("mailbox_client_id_env") or DEFAULT_CLIENT_ID_ENV).strip()
    client_id = os.getenv(client_id_env, "").strip()
    if not client_id:
        return None

    authority = str(config.get("mailbox_oauth_authority") or DEFAULT_AUTHORITY).strip()
    scopes = list(config.get("mailbox_oauth_scopes") or DEFAULT_SCOPES)
    cache_path = Path(str(config.get("mailbox_oauth_cache_path") or get_token_cache_path()))
    cache = _load_cache(cache_path)
    app = msal.PublicClientApplication(
        client_id,
        authority=authority,
        token_cache=cache,
    )
    accounts = app.get_accounts()
    result = app.acquire_token_silent(scopes, account=accounts[0]) if accounts else None

    if not result and interactive:
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise RuntimeError(
                "Impossible de démarrer l'autorisation Microsoft: "
                + json.dumps(flow, ensure_ascii=False)
            )
        message = str(flow.get("message") or "Ouvrez l'URL Microsoft et saisissez le code fourni.")
        if message_callback:
            message_callback(message)
        else:
            print(message)
        result = app.acquire_token_by_device_flow(flow)

    _save_cache(cache, cache_path)
    if isinstance(result, dict) and result.get("access_token"):
        return str(result["access_token"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autorise une boite Hotmail pour les brouillons IMAP."
    )
    parser.add_argument(
        "--client-id-env",
        default=DEFAULT_CLIENT_ID_ENV,
        help="Variable contenant l'ID client de l'application Microsoft.",
    )
    args = parser.parse_args()
    os.environ.setdefault(DEFAULT_CLIENT_ID_ENV, os.getenv(args.client_id_env, ""))
    token = get_hotmail_access_token(interactive=True)
    if not token:
        print("Autorisation Microsoft non obtenue.")
        return 1
    print(f"Autorisation enregistree dans le cache: {get_token_cache_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
