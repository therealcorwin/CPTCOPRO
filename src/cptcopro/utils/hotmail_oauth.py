"""Authentification OAuth2 Microsoft pour l'acces IMAP Hotmail."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable

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
    return cache_dir / "msal_token_cache.json"


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
    client_id_env = str(
        config.get("mailbox_client_id_env") or DEFAULT_CLIENT_ID_ENV
    ).strip()
    client_id = os.getenv(client_id_env, "").strip()
    if not client_id:
        return None

    authority = str(config.get("mailbox_oauth_authority") or DEFAULT_AUTHORITY).strip()
    scopes = list(config.get("mailbox_oauth_scopes") or DEFAULT_SCOPES)
    cache_path = Path(
        str(config.get("mailbox_oauth_cache_path") or get_token_cache_path())
    )
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
    if result and result.get("access_token"):
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
