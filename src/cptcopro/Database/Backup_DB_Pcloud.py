from __future__ import annotations

import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pcloud_sdk import PCloudException, PCloudSDK
from pcloud_sdk.progress_utils import SimpleProgressBar

from cptcopro.utils.env_loader import get_pcloud_backup_config, get_pcloud_credentials
from cptcopro.utils.paths import get_backup_dir, get_log_path, get_project_root_dir

# Charger les credentials OAuth2 pCloud depuis le fichier .env
pcloud_credentials = get_pcloud_credentials()
PCloud_APP_KEY = pcloud_credentials["pcloud_APP_KEY"]
PCloud_APP_SECRET = pcloud_credentials["pcloud_APP_SECRET"]
PCLOUD_BACKUP_CONFIG = get_pcloud_backup_config()
PCLOUD_TOKEN_FILE_NAME = ".pcloud_credentials"
PCLOUD_BACKUP_FOLDER_NAME = str(
    PCLOUD_BACKUP_CONFIG.get("pcloud_backup_folder") or "Backup_BDD_Copro"
)
DEFAULT_REDIRECT_URI = "http://localhost:8000/callback"
PCLOUD_LOCATION_ID = int(PCLOUD_BACKUP_CONFIG["pcloud_location_id"])
_raw_backup_folder_id = str(PCLOUD_BACKUP_CONFIG.get("pcloud_backup_folder_id", "")).strip()
PCLOUD_BACKUP_FOLDER_ID = int(_raw_backup_folder_id) if _raw_backup_folder_id.isdigit() else None

# Configurer les logs avec le bon chemin
LOG_PATH = str(get_log_path("app.log"))
# Chemin complet vers le fichier de token pCloud
pcloud_token_path = get_project_root_dir() / PCLOUD_TOKEN_FILE_NAME

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | <cyan>{extra[type_log]}</cyan> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>|  "
    "<level>{message}</level>",
    level="INFO",
    colorize=True,
)
logger.add(
    LOG_PATH,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra[type_log]} |{name}: {function}: {line} |  {message}",
    level="INFO",
    rotation="10 MB",
    retention="1 month",
    compression="zip",
)
logger = logger.bind(type_log="PCLOUD")


def tester_presence_token_pcloud(token_file: Path | None = None) -> bool:
    """Teste la présence du fichier de token pCloud `.pcloud_credentials`."""
    token_path = token_file or pcloud_token_path
    exists = token_path.exists()
    logger.info("Présence du token pCloud '{}': {}", token_path, exists)
    return exists


def creer_client_pcloud(token_file: Path | None = None) -> PCloudSDK:
    """Crée un client pCloud configuré pour OAuth2 et gestion du token."""
    token_path = token_file or pcloud_token_path
    return PCloudSDK(
        app_key=PCloud_APP_KEY,
        app_secret=PCloud_APP_SECRET,
        auth_type="oauth2",
        location_id=PCLOUD_LOCATION_ID,
        token_manager=True,
        token_file=str(token_path),
    )


def connecter_pcloud_via_oauth(
    token_file: Path | None = None,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> PCloudSDK:
    """Lance un flux OAuth interactif et persiste le token pCloud."""
    sdk = creer_client_pcloud(token_file)
    auth_url = sdk.get_auth_url(redirect_uri)

    logger.info("Aucun token pCloud trouvé. Connexion OAuth requise.")
    print("Veuillez ouvrir cette URL pour autoriser l'application :")
    print(auth_url)

    authorization_code = input("Entrez le code d'autorisation pCloud : ").strip()
    if not authorization_code:
        raise ValueError("Aucun code d'autorisation pCloud fourni.")

    try:
        token_info = sdk.authenticate(
            authorization_code,
            location_id=PCLOUD_LOCATION_ID,
        )
    except PCloudException as exc:
        logger.error("Authentification pCloud échouée: {}", exc)
        raise RuntimeError("Connexion pCloud OAuth échouée.") from exc

    logger.success(
        "Authentification pCloud réussie. Location={}.",
        token_info.get("locationid"),
    )
    return sdk


def connecter_pcloud_via_token(token_file: Path | None = None) -> PCloudSDK:
    """Charge le token pCloud existant et valide la connexion."""
    sdk = creer_client_pcloud(token_file)

    try:
        user_info = sdk.user.get_user_info()
    except Exception as exc:
        logger.error("Token pCloud présent mais invalide ou expiré: {}", exc)
        raise RuntimeError(
            "Le fichier .pcloud_credentials existe mais la connexion pCloud a échoué."
        ) from exc

    logger.success(
        "Connexion pCloud établie avec le token existant pour '{}'.",
        user_info.get("email", "inconnu"),
    )
    return sdk


def tester_token_et_connecter_pcloud(
    token_file: Path | None = None,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> PCloudSDK:
    """Teste la présence du token pCloud puis lance la connexion adaptée."""
    token_path = token_file or pcloud_token_path
    if tester_presence_token_pcloud(token_path):
        try:
            return connecter_pcloud_via_token(token_path)
        except RuntimeError:
            logger.warning(
                "Fallback vers une nouvelle authentification OAuth après échec du token existant."
            )

    return connecter_pcloud_via_oauth(token_path, redirect_uri=redirect_uri)


def assurer_repertoire_backup_bdd_copro(
    sdk: PCloudSDK,
    folder_name: str = PCLOUD_BACKUP_FOLDER_NAME,
    parent_folder_id: int = 0,
) -> dict[str, Any]:
    """Teste la présence du répertoire distant et le crée s'il n'existe pas."""
    existing_folder = sdk.folder.list_folder(folder_name)
    if existing_folder is not None:
        logger.info(
            "Répertoire pCloud '{}' déjà présent (folderid={}).",
            folder_name,
            existing_folder.get("folderid"),
        )
        return dict(existing_folder)

    logger.info("Création du répertoire pCloud '{}'...", folder_name)
    try:
        created_folder_id = sdk.folder.create(folder_name, parent=parent_folder_id)
    except PCloudException as exc:
        logger.error("Impossible de créer le répertoire pCloud '{}': {}", folder_name, exc)
        raise RuntimeError(f"Création du répertoire pCloud '{folder_name}' échouée.") from exc

    created_folder = sdk.folder.list_folder(folder_name)
    if created_folder is not None:
        logger.success(
            "Répertoire pCloud '{}' créé (folderid={}).",
            folder_name,
            created_folder.get("folderid"),
        )
        return dict(created_folder)

    logger.success(
        "Répertoire pCloud '{}' créé (folderid={}).",
        folder_name,
        created_folder_id,
    )
    return {"name": folder_name, "folderid": created_folder_id}


def deconnecter_pcloud(
    sdk: PCloudSDK | None = None,
    token_file: Path | None = None,
) -> None:
    """Déconnecte le client pCloud et supprime le fichier de token local."""
    token_path = token_file or pcloud_token_path

    if sdk is None and tester_presence_token_pcloud(token_path):
        try:
            sdk = connecter_pcloud_via_token(token_path)
        except Exception as exc:
            logger.warning("Connexion pCloud impossible avant déconnexion: {}", exc)

    if sdk is not None:
        try:
            sdk.logout()
            logger.info("Déconnexion pCloud effectuée via l'API.")
        except PCloudException as exc:
            logger.warning("Déconnexion pCloud via l'API échouée (ignorée): {}", exc)
        except Exception as exc:
            logger.warning("Erreur inattendue lors de la déconnexion pCloud: {}", exc)

    if token_path.exists():
        try:
            token_path.unlink()
            logger.info("Token pCloud supprimé: {}", token_path)
        except OSError as exc:
            logger.warning("Impossible de supprimer le token pCloud '{}': {}", token_path, exc)


def lister_fichiers_et_dossiers_pcloud(
    sdk: PCloudSDK,
    folder_name: str = PCLOUD_BACKUP_FOLDER_NAME,
    folder_id: int | None = PCLOUD_BACKUP_FOLDER_ID,
    recursif: bool = True,
    dossiers_dabord: bool = True,
) -> list[dict[str, Any]]:
    """Liste et trie les éléments d'un dossier distant pCloud.

    Le tri est insensible à la casse. Par défaut, les dossiers sont renvoyés
    avant les fichiers.

    Args:
        sdk: Client pCloud authentifié.
        folder_name: Nom du dossier distant à lister.
        folder_id: Identifiant du dossier distant. S'il est fourni,
            il est utilisé en fallback si la lecture par nom échoue.
        recursif: Si True, inclut aussi le contenu des sous-dossiers.
        dossiers_dabord: Si True, place les dossiers avant les fichiers.

    Returns:
        Liste triée de métadonnées pCloud (dossiers et fichiers).

    Raises:
        RuntimeError: Si le dossier est introuvable ou si la récupération échoue.
    """
    target_folder_id: int | None = None

    try:
        # Aligné avec la doc pCloud: racine via list_root().
        if folder_id is None and str(folder_name).strip() in {"", "/"}:
            root_result = sdk.folder.list_root()
            contents: Any = root_result.get("contents", []) if isinstance(root_result, dict) else []
            target_folder_id = 0
        else:
            # Pour un dossier spécifique, la doc montre get_content(folder_id).
            target_folder_id = folder_id if isinstance(folder_id, int) and folder_id > 0 else None
            if target_folder_id is None:
                folder_meta = sdk.folder.list_folder(folder_name)
                if not isinstance(folder_meta, dict):
                    raise RuntimeError(f"Le dossier pCloud '{folder_name}' est introuvable.")
                target_folder_id = folder_meta.get("folderid")

            if not isinstance(target_folder_id, int) or target_folder_id <= 0:
                raise RuntimeError(
                    f"Impossible de déterminer le folder_id du dossier pCloud '{folder_name}'."
                )

            contents = sdk.folder.get_content(folder_id=target_folder_id)
    except PCloudException as exc:
        logger.error("Lecture du dossier pCloud '{}' échouée: {}", folder_name, exc)
        raise RuntimeError(f"Impossible de lister le dossier pCloud '{folder_name}'.") from exc
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error(
            "Erreur inattendue lors de la lecture du dossier pCloud '{}': {}",
            folder_name,
            exc,
        )
        raise RuntimeError(f"Erreur inattendue lors du listing pCloud de '{folder_name}'.") from exc

    if not isinstance(contents, list):
        logger.warning(
            "Le contenu du dossier pCloud '{}' est invalide; liste vide utilisée.",
            folder_name,
        )
        contents = []

    def _is_folder(entry: dict[str, Any]) -> bool:
        return bool(entry.get("isfolder", entry.get("is_folder", False)))

    def _entry_name(entry: dict[str, Any]) -> str:
        return str(entry.get("name", "")).casefold()

    def _format_size(size: object) -> str:
        if not isinstance(size, (int, float)):
            return "-"
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        unit_index = 0
        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1
        if unit_index == 0:
            return f"{int(value)} {units[unit_index]}"
        return f"{value:.1f} {units[unit_index]}"

    def _build_path(parent: str, name: str) -> str:
        clean_parent = parent.rstrip("/")
        clean_name = name.strip("/")
        if not clean_parent:
            return f"/{clean_name}" if clean_name else "/"
        return f"{clean_parent}/{clean_name}" if clean_name else clean_parent

    def _collect_recursive(items: list[dict[str, Any]], parent_path: str) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        valid_items = [entry for entry in items if isinstance(entry, dict)]
        folders = [entry for entry in valid_items if _is_folder(entry)]
        files = [entry for entry in valid_items if not _is_folder(entry)]
        folders.sort(key=_entry_name)
        files.sort(key=_entry_name)

        ordered_items = folders + files if dossiers_dabord else files + folders

        for entry in ordered_items:
            if not isinstance(entry, dict):
                continue

            is_folder = _is_folder(entry)
            name = str(entry.get("name", "")).strip()
            entry_path = _build_path(parent_path, name)

            normalized_entry = dict(entry)
            normalized_entry["entry_type"] = "folder" if is_folder else "file"
            normalized_entry["isfolder"] = is_folder
            normalized_entry["full_path"] = entry_path
            normalized_entry["display_size"] = "-" if is_folder else _format_size(entry.get("size"))
            normalized_entry["parent_folder"] = parent_path
            collected.append(normalized_entry)

            if recursif and is_folder:
                child_folder_id = entry.get("folderid")
                if isinstance(child_folder_id, int):
                    try:
                        child_items = sdk.folder.get_content(folder_id=child_folder_id)
                        if isinstance(child_items, list):
                            collected.extend(_collect_recursive(child_items, entry_path))
                    except Exception as exc:
                        logger.warning(
                            "Lecture du sous-dossier pCloud '{}' échouée: {}",
                            entry_path,
                            exc,
                        )
        return collected

    base_path = "/" if target_folder_id == 0 else f"/{str(folder_name).strip('/')}"
    sorted_contents = _collect_recursive(contents, base_path)

    logger.info(
        "Listing pCloud '{}' récupéré: {} élément(s).",
        folder_name,
        len(sorted_contents),
    )
    folder_count = sum(1 for item in sorted_contents if item.get("isfolder"))
    file_count = len(sorted_contents) - folder_count
    logger.info(
        "Résumé: {} dossier(s), {} fichier(s).",
        folder_count,
        file_count,
    )

    logger.info("| TYPE    | NOM                            | TAILLE   | CHEMIN |")
    logger.info("|---------|--------------------------------|----------|--------|")

    for item in sorted_contents:
        logger.info(
            "| {:<7} | {:<30} | {:<8} | {} |",
            "DOSSIER" if item.get("isfolder") else "FICHIER",
            str(item.get("name", "(sans nom)"))[:30],
            item.get("display_size", "-"),
            item.get("full_path", ""),
        )

    return sorted_contents


def _extraire_date_backup_depuis_nom(nom_fichier: str) -> datetime | None:
    """Extrait la date d'un fichier de backup pCloud nommé `<base>-DD-MM-YYYY-HH-MM.(sqlite|sql.gz)`."""
    pattern = re.compile(
        r"^(?P<base>.+)-(?P<timestamp>\d{2}-\d{2}-\d{4}-\d{2}-\d{2})(?:-\d{2})?\.(?:sqlite|sql\.gz)$",
        re.IGNORECASE,
    )
    match = pattern.match(nom_fichier.strip())
    if match is None:
        return None

    timestamp = match.group("timestamp")
    try:
        return datetime.strptime(timestamp, "%d-%m-%Y-%H-%M")
    except ValueError:
        return None


def _selectionner_backup_pcloud_plus_recent(
    elements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Sélectionne le backup (.sql.gz ou .sqlite) le plus récent parmi les éléments listés."""
    backups: list[dict[str, Any]] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        if element.get("isfolder"):
            continue

        name = str(element.get("name", "")).strip()
        if not (name.lower().endswith(".sql.gz") or name.lower().endswith(".sqlite")):
            continue

        element_copy = dict(element)
        element_copy["_backup_dt"] = _extraire_date_backup_depuis_nom(name)
        backups.append(element_copy)

    if not backups:
        raise RuntimeError("Aucun fichier de backup n'a été trouvé sur pCloud.")

    def _sort_key(element: dict[str, Any]) -> tuple[datetime, str]:
        backup_dt = element.get("_backup_dt")
        if isinstance(backup_dt, datetime):
            return backup_dt, str(element.get("name", "")).casefold()
        return datetime.min, str(element.get("name", "")).casefold()

    return max(backups, key=_sort_key)


def telecharger_dernier_backup_pcloud(
    sdk: PCloudSDK,
    folder_name: str = PCLOUD_BACKUP_FOLDER_NAME,
    local_db_name: str | None = None,
    overwrite: bool | None = None,
) -> dict[str, Any]:
    """Télécharge le backup pCloud le plus récent vers le dossier local BDD.

    Si une base locale existe déjà, l'utilisateur est invité à confirmer l'écrasement
    sauf si `overwrite` est fourni explicitement.

    Args:
        sdk: Client pCloud authentifié.
        folder_name: Nom du répertoire distant où chercher les backups.
        local_db_name: Nom du fichier de base de données locale. Par défaut,
            la valeur issue de `CPTCOPRO_DB_NAME` ou `coproprietaires.sqlite`.
        overwrite: Si True, écrase la base locale existante sans demander.
            Si False, n'écrase jamais et annule le téléchargement si la base existe.
            Si None, demande confirmation à l'utilisateur.

    Returns:
        Dictionnaire de résultat avec le backup distant choisi et le chemin local.

    Raises:
        RuntimeError: Si aucun backup n'est trouvé, si l'utilisateur refuse
            l'écrasement, ou en cas d'échec de téléchargement.
    """
    local_db_dir = get_backup_dir()
    local_db_path = local_db_dir / (local_db_name or "coproprietaires.sqlite")
    local_db_dir.mkdir(parents=True, exist_ok=True)

    if local_db_path.exists():
        if overwrite is None:
            print(f"Une base locale existe déjà: {local_db_path}")
            response = (
                input("Voulez-vous l'ecraser avec le dernier backup pCloud ? [o/N] : ")
                .strip()
                .lower()
            )
            overwrite = response in {"o", "oui", "y", "yes"}

        if not overwrite:
            logger.info("Téléchargement annulé: base locale déjà présente et écrasement refusé.")
            return {
                "downloaded": False,
                "reason": "local_exists",
                "local_path": str(local_db_path),
            }

    logger.info("Recherche du backup pCloud le plus récent dans '{}'.", folder_name)
    remote_entries = lister_fichiers_et_dossiers_pcloud(
        sdk,
        folder_name=folder_name,
        recursif=True,
        dossiers_dabord=True,
    )
    latest_backup = _selectionner_backup_pcloud_plus_recent(remote_entries)

    remote_fileid = latest_backup.get("fileid")
    remote_name = str(latest_backup.get("name", "")).strip()
    if not isinstance(remote_fileid, int):
        raise RuntimeError(
            f"Le backup pCloud '{remote_name}' ne contient pas d'identifiant de fichier valide."
        )

    logger.info(
        "Backup pCloud sélectionné: '{}' (fileid={}).",
        remote_name,
        remote_fileid,
    )

    progress_callback = SimpleProgressBar(
        title="Restauration pCloud",
        width=50,
        show_speed=True,
        show_eta=True,
    )

    with tempfile.TemporaryDirectory(prefix="pcloud_restore_", dir=str(local_db_dir)) as temp_dir:
        temp_dir_path = Path(temp_dir)
        try:
            sdk.file.download(
                remote_fileid,
                destination=str(temp_dir_path),
                progress_callback=progress_callback,
            )
        except PCloudException as exc:
            logger.error("Téléchargement pCloud échoué pour '{}': {}", remote_name, exc)
            raise RuntimeError(f"Téléchargement pCloud du backup '{remote_name}' échoué.") from exc
        except Exception as exc:
            logger.error("Erreur inattendue lors du téléchargement '{}': {}", remote_name, exc)
            raise RuntimeError(
                f"Erreur inattendue lors du téléchargement pCloud de '{remote_name}'."
            ) from exc

        downloaded_file = temp_dir_path / remote_name
        if not downloaded_file.exists():
            candidates = list(temp_dir_path.iterdir())
            if len(candidates) == 1 and candidates[0].is_file():
                downloaded_file = candidates[0]

        if not downloaded_file.exists():
            raise RuntimeError(
                f"Le fichier '{remote_name}' téléchargé depuis pCloud est introuvable dans le dossier temporaire."
            )

        if str(downloaded_file).endswith(".sql.gz"):
            import gzip

            from cptcopro.Database.connection import get_db_connection

            logger.info("Restauration du dump SQL dans MariaDB...")
            with gzip.open(downloaded_file, "rt", encoding="utf-8") as gz:
                sql_content = gz.read()
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    for stmt in sql_content.split(";"):
                        stmt_lines = [
                            line for line in stmt.splitlines() if not line.strip().startswith("--")
                        ]
                        stmt_clean = "\n".join(stmt_lines).strip()
                        if stmt_clean:
                            cur.execute(stmt_clean)
            logger.success("Dump SQL restaure dans MariaDB avec succes.")
            local_backup_path = local_db_dir / downloaded_file.name
            downloaded_file.replace(local_backup_path)
            local_db_path = local_backup_path
        else:
            if local_db_path.exists():
                try:
                    local_db_path.unlink()
                except FileNotFoundError:
                    pass

            target_sidecars = [
                local_db_path.with_name(local_db_path.name + "-wal"),
                local_db_path.with_name(local_db_path.name + "-shm"),
                local_db_path.with_name(local_db_path.name + "-journal"),
            ]

            downloaded_file.replace(local_db_path)

            for sidecar in target_sidecars:
                if sidecar.exists():
                    try:
                        sidecar.unlink()
                    except OSError:
                        logger.warning(
                            "Impossible de supprimer le fichier annexe SQLite '{}'.", sidecar
                        )

    logger.success(
        "Dernier backup pCloud téléchargé vers '{}'.",
        local_db_path,
    )
    return {
        "downloaded": True,
        "remote_fileid": remote_fileid,
        "remote_filename": remote_name,
        "local_path": str(local_db_path),
    }


def sauvegarder_bdd_pcloud(
    sdk: PCloudSDK,
    db_path: Path,
    folder_name: str = PCLOUD_BACKUP_FOLDER_NAME,
) -> dict[str, Any]:
    """Sauvegarde la base de données horodatée sur pCloud."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Base de données introuvable : {db_path}")

    # Nom horodaté
    now = datetime.now()
    timestamp = now.strftime("%d-%m-%Y-%H-%M")
    if db_path.name.endswith(".sql.gz"):
        remote_filename = f"backup_cptcopro-{timestamp}.sql.gz"
    else:
        stem = db_path.stem
        remote_filename = f"{stem}-{timestamp}.sqlite"

    local_size = db_path.stat().st_size
    logger.info(
        "Démarrage backup pCloud : '{}' → '{}' ({} octets).",
        db_path.name,
        remote_filename,
        local_size,
    )

    # Assurer l'existence du répertoire distant et récupérer son folderid
    folder_info = assurer_repertoire_backup_bdd_copro(sdk, folder_name)
    folder_id: int = folder_info.get("folderid", 0)

    # --- Barre d'avancement pCloud SDK ---
    progress_callback = SimpleProgressBar(
        title="Backup pCloud",
        width=50,
        show_speed=True,
        show_eta=True,
    )

    # --- Upload ---
    upload_result: dict[str, Any] = {}
    try:
        upload_result = sdk.file.upload(
            str(db_path),
            folder_id=folder_id,
            filename=remote_filename,
            progress_callback=progress_callback,
        )
    except PCloudException as exc:
        logger.error("Upload pCloud échoué pour '{}': {}", remote_filename, exc)
        raise RuntimeError(f"Upload pCloud de '{remote_filename}' échoué.") from exc
    except Exception as exc:
        logger.error("Erreur inattendue lors de l'upload '{}': {}", remote_filename, exc)
        raise RuntimeError(
            f"Erreur inattendue lors de l'upload pCloud de '{remote_filename}'."
        ) from exc

    # --- Contrôle d'intégrité : comparaison des tailles ---
    try:
        metadata_list = upload_result.get("metadata", [])
        if isinstance(metadata_list, list) and metadata_list:
            remote_meta = metadata_list[0]
        elif isinstance(metadata_list, dict):
            remote_meta = metadata_list
        else:
            remote_meta = upload_result

        remote_size: int | None = remote_meta.get("size")
        remote_fileid: int | None = remote_meta.get("fileid")

        if remote_size is not None and remote_size != local_size:
            raise RuntimeError(
                f"Contrôle d'intégrité échoué : taille locale={local_size}, "
                f"taille distante={remote_size}."
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.warning("Impossible de vérifier la taille distante du fichier (ignoré): {}", exc)
        remote_size = None
        remote_fileid = None

    logger.success(
        "Backup pCloud réussi : '{}' (fileid={}, {} octets).",
        remote_filename,
        remote_fileid,
        remote_size if remote_size is not None else local_size,
    )
    return upload_result


__all__ = [
    "assurer_repertoire_backup_bdd_copro",
    "connecter_pcloud_via_oauth",
    "connecter_pcloud_via_token",
    "creer_client_pcloud",
    "deconnecter_pcloud",
    "lister_fichiers_et_dossiers_pcloud",
    "sauvegarder_bdd_pcloud",
    "telecharger_dernier_backup_pcloud",
    "tester_presence_token_pcloud",
    "tester_token_et_connecter_pcloud",
]
