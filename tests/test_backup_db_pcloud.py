from pathlib import Path
from typing import Any

import pytest

from cptcopro.Database import Backup_DB_Pcloud as pcloud_mod


class DummyFolder:
    def __init__(self, existing=None, created_folder_id=321, content_by_id=None, root_contents=None):
        self.existing = existing
        self.created_folder_id = created_folder_id
        self.created_calls = []
        self.content_by_id = content_by_id or {}
        self.root_contents = root_contents or []

    def list_folder(self, folder_name=None):
        return self.existing

    def create(self, folder_name, parent=0):
        self.created_calls.append((folder_name, parent))
        return self.created_folder_id

    def get_content(self, folder_id=None, path=None):
        if folder_id is not None:
            return self.content_by_id.get(folder_id, [])
        return []

    def list_root(self):
        return {"contents": self.root_contents, "metadata": {"folderid": 0, "name": "/"}}


class DummyFile:
    def __init__(self, files_by_id: dict[int, dict[str, Any]]):
        self.files_by_id = files_by_id
        self.download_calls: list[tuple[int, str]] = []

    def download(self, file_id, destination="", progress_callback=None):
        self.download_calls.append((file_id, destination))
        info = self.files_by_id[file_id]
        destination_path = Path(destination)
        destination_path.mkdir(parents=True, exist_ok=True)
        target = destination_path / info["name"]
        target.write_text(info.get("content", ""), encoding="utf-8")
        return True


class DummySDK:
    def __init__(self, folder, file_obj=None, user_info=None, user_error=None):
        self.folder = folder
        self.file = file_obj or self
        self._user_info = user_info or {"email": "test@example.com"}
        self._user_error = user_error
        self.user = self

    def get_user_info(self):
        if self._user_error is not None:
            raise self._user_error
        return self._user_info

    def download(self, file_id, destination="", progress_callback=None):
        raise NotImplementedError


def test_tester_presence_token_pcloud_detects_existing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pcloud_mod, "get_project_root_dir", lambda: tmp_path)
    token_file = tmp_path / ".pcloud_credentials"
    token_file.write_text("{}", encoding="utf-8")

    assert pcloud_mod.tester_presence_token_pcloud() is True


def test_tester_token_et_connecter_pcloud_uses_existing_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    token_file = tmp_path / ".pcloud_credentials"
    token_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pcloud_mod, "get_project_root_dir", lambda: tmp_path)
    monkeypatch.setattr(pcloud_mod, "pcloud_token_path", token_file)

    expected_sdk = object()
    monkeypatch.setattr(
        pcloud_mod,
        "connecter_pcloud_via_token",
        lambda token_path: expected_sdk,
    )
    monkeypatch.setattr(
        pcloud_mod,
        "connecter_pcloud_via_oauth",
        lambda token_path, redirect_uri: pytest.fail("OAuth ne doit pas être appelé"),
    )

    assert pcloud_mod.tester_token_et_connecter_pcloud() is expected_sdk


def test_tester_token_et_connecter_pcloud_falls_back_to_oauth_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pcloud_mod, "get_project_root_dir", lambda: tmp_path)
    monkeypatch.setattr(pcloud_mod, "pcloud_token_path", tmp_path / ".pcloud_credentials")

    expected_sdk = object()
    monkeypatch.setattr(
        pcloud_mod,
        "connecter_pcloud_via_token",
        lambda token_path: pytest.fail("La connexion par token ne doit pas être appelée"),
    )
    monkeypatch.setattr(
        pcloud_mod,
        "connecter_pcloud_via_oauth",
        lambda token_path, redirect_uri: expected_sdk,
    )

    assert pcloud_mod.tester_token_et_connecter_pcloud() is expected_sdk


def test_assurer_repertoire_backup_bdd_copro_returns_existing_folder():
    existing_folder = {"name": "Backup_BDD_Copro", "folderid": 555}
    sdk = DummySDK(folder=DummyFolder(existing=existing_folder))

    result = pcloud_mod.assurer_repertoire_backup_bdd_copro(sdk)

    assert result == existing_folder
    assert sdk.folder.created_calls == []


def test_assurer_repertoire_backup_bdd_copro_creates_folder_when_missing():
    folder = DummyFolder(existing=None, created_folder_id=777)
    sdk = DummySDK(folder=folder)

    result = pcloud_mod.assurer_repertoire_backup_bdd_copro(sdk)

    assert folder.created_calls == [(pcloud_mod.PCLOUD_BACKUP_FOLDER_NAME, 0)]
    assert result == {"name": pcloud_mod.PCLOUD_BACKUP_FOLDER_NAME, "folderid": 777}


def test_lister_fichiers_et_dossiers_pcloud_trie_dossiers_puis_fichiers():
    existing_folder = {
        "name": pcloud_mod.PCLOUD_BACKUP_FOLDER_NAME,
        "folderid": 555,
    }
    folder = DummyFolder(
        existing=existing_folder,
        content_by_id={
            555: [
                {"name": "zeta.sqlite", "isfolder": False},
                {"name": "B_folder", "isfolder": True},
                {"name": "alpha.sqlite", "isfolder": False},
                {"name": "a_folder", "isfolder": True},
            ]
        },
    )
    sdk = DummySDK(folder=folder)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pcloud_mod, "PCLOUD_BACKUP_FOLDER_ID", None)

    result = pcloud_mod.lister_fichiers_et_dossiers_pcloud(sdk)
    monkeypatch.undo()

    assert [item["name"] for item in result] == [
        "a_folder",
        "B_folder",
        "alpha.sqlite",
        "zeta.sqlite",
    ]
    assert [item["entry_type"] for item in result] == [
        "folder",
        "folder",
        "file",
        "file",
    ]


def test_lister_fichiers_et_dossiers_pcloud_leve_si_dossier_introuvable():
    sdk = DummySDK(folder=DummyFolder(existing=None))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pcloud_mod, "PCLOUD_BACKUP_FOLDER_ID", None)

    with pytest.raises(RuntimeError, match="introuvable"):
        pcloud_mod.lister_fichiers_et_dossiers_pcloud(sdk)
    monkeypatch.undo()


def test_lister_fichiers_et_dossiers_pcloud_supporte_payload_metadata():
    existing_folder = {
        "name": pcloud_mod.PCLOUD_BACKUP_FOLDER_NAME,
        "folderid": 555,
    }
    folder = DummyFolder(
        existing=existing_folder,
        content_by_id={
            555: [
                {"name": "B.txt", "isfolder": False},
                {"name": "a.txt", "isfolder": False},
            ]
        },
    )
    sdk = DummySDK(folder=folder)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pcloud_mod, "PCLOUD_BACKUP_FOLDER_ID", None)

    result = pcloud_mod.lister_fichiers_et_dossiers_pcloud(sdk)
    monkeypatch.undo()

    assert [item["name"] for item in result] == ["a.txt", "B.txt"]
    assert [item["entry_type"] for item in result] == ["file", "file"]


def test_lister_fichiers_et_dossiers_pcloud_utilise_fallback_folder_id():
    existing_folder = None
    folder = DummyFolder(
        existing=existing_folder,
        content_by_id={123: [{"name": "doc.txt", "isfolder": False}]},
    )
    sdk = DummySDK(folder=folder)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pcloud_mod, "PCLOUD_BACKUP_FOLDER_ID", None)

    result = pcloud_mod.lister_fichiers_et_dossiers_pcloud(
        sdk,
        folder_name="inexistant",
        folder_id=123,
    )
    monkeypatch.undo()

    assert [item["name"] for item in result] == ["doc.txt"]


def test_lister_fichiers_et_dossiers_pcloud_liste_racine_via_list_root():
    folder = DummyFolder(
        root_contents=[
            {"name": "Photos", "isfolder": True},
            {"name": "a.txt", "isfolder": False},
            {"name": "Z.txt", "isfolder": False},
        ]
    )
    sdk = DummySDK(folder=folder)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pcloud_mod, "PCLOUD_BACKUP_FOLDER_ID", None)

    result = pcloud_mod.lister_fichiers_et_dossiers_pcloud(
        sdk,
        folder_name="/",
        folder_id=None,
    )
    monkeypatch.undo()

    assert [item["name"] for item in result] == ["Photos", "a.txt", "Z.txt"]


def test_lister_fichiers_et_dossiers_pcloud_lit_contenu_reel_depuis_folder_id():
    # Reproduit le comportement réel du SDK: list_folder("nom") renvoie un
    # item dossier sans "contents", il faut appeler get_content(folder_id=...).
    existing_folder = {
        "name": pcloud_mod.PCLOUD_BACKUP_FOLDER_NAME,
        "folderid": 999,
        "isfolder": True,
    }
    folder = DummyFolder(
        existing=existing_folder,
        content_by_id={
            999: [
                {"name": "zeta.sqlite", "isfolder": False},
                {"name": "alpha.sqlite", "isfolder": False},
            ]
        },
    )
    sdk = DummySDK(folder=folder)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pcloud_mod, "PCLOUD_BACKUP_FOLDER_ID", None)

    result = pcloud_mod.lister_fichiers_et_dossiers_pcloud(sdk)
    monkeypatch.undo()

    assert [item["name"] for item in result] == ["alpha.sqlite", "zeta.sqlite"]
    assert [item["entry_type"] for item in result] == ["file", "file"]


def test_lister_fichiers_et_dossiers_pcloud_inclut_fichiers_des_sous_dossiers():
    existing_folder = {
        "name": pcloud_mod.PCLOUD_BACKUP_FOLDER_NAME,
        "folderid": 10,
    }
    folder = DummyFolder(
        existing=existing_folder,
        content_by_id={
            10: [
                {"name": "SousDossier", "isfolder": True, "folderid": 20},
            ],
            20: [
                {"name": "interne.txt", "isfolder": False, "fileid": 30},
            ],
        },
    )
    sdk = DummySDK(folder=folder)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pcloud_mod, "PCLOUD_BACKUP_FOLDER_ID", None)

    result = pcloud_mod.lister_fichiers_et_dossiers_pcloud(sdk, recursif=True)
    monkeypatch.undo()

    assert [item["name"] for item in result] == ["SousDossier", "interne.txt"]
    assert [item["entry_type"] for item in result] == ["folder", "file"]
    assert [item["full_path"] for item in result] == [
        f"/{pcloud_mod.PCLOUD_BACKUP_FOLDER_NAME}/SousDossier",
        f"/{pcloud_mod.PCLOUD_BACKUP_FOLDER_NAME}/SousDossier/interne.txt",
    ]


def test_telecharger_dernier_backup_pcloud_selectionne_le_plus_recent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local_db_path = tmp_path / "BDD" / "coproprietaires.sqlite"
    monkeypatch.setattr(pcloud_mod, "get_db_path", lambda db_name=None: local_db_path)

    remote_entries = [
        {"name": "coproprietaires-30-07-2026-21-22.sqlite", "isfolder": False, "fileid": 1},
        {"name": "coproprietaires-31-07-2026-23-32.sqlite", "isfolder": False, "fileid": 2},
        {"name": "Backup_Compte_Copro", "isfolder": True, "folderid": 10},
    ]
    folder = DummyFolder(existing={"folderid": 10})
    sdk = DummySDK(
        folder=folder,
        file_obj=DummyFile(
            {
                1: {"name": "coproprietaires-30-07-2026-21-22.sqlite", "content": "old"},
                2: {"name": "coproprietaires-31-07-2026-23-32.sqlite", "content": "new"},
            }
        ),
    )
    monkeypatch.setattr(
        pcloud_mod,
        "lister_fichiers_et_dossiers_pcloud",
        lambda sdk, folder_name, recursif=True, dossiers_dabord=True, folder_id=None: remote_entries,
    )

    result = pcloud_mod.telecharger_dernier_backup_pcloud(sdk, overwrite=True)

    assert result["downloaded"] is True
    assert result["remote_fileid"] == 2
    assert local_db_path.read_text(encoding="utf-8") == "new"
    assert sdk.file.download_calls[0][0] == 2
    assert Path(sdk.file.download_calls[0][1]).parent == local_db_path.parent
    assert Path(sdk.file.download_calls[0][1]).name.startswith("pcloud_restore_")


def test_telecharger_dernier_backup_pcloud_annule_si_base_locale_et_refus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local_db_path = tmp_path / "BDD" / "coproprietaires.sqlite"
    local_db_path.parent.mkdir(parents=True, exist_ok=True)
    local_db_path.write_text("local", encoding="utf-8")
    monkeypatch.setattr(pcloud_mod, "get_db_path", lambda db_name=None: local_db_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    sdk = DummySDK(folder=DummyFolder(existing=None), file_obj=DummyFile({}))

    result = pcloud_mod.telecharger_dernier_backup_pcloud(sdk, overwrite=None)

    assert result == {
        "downloaded": False,
        "reason": "local_exists",
        "local_path": str(local_db_path),
    }


def test_telecharger_dernier_backup_pcloud_ecrase_et_supprime_sidecars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local_db_path = tmp_path / "BDD" / "coproprietaires.sqlite"
    local_db_path.parent.mkdir(parents=True, exist_ok=True)
    local_db_path.write_text("local", encoding="utf-8")
    (local_db_path.parent / "coproprietaires.sqlite-wal").write_text("wal", encoding="utf-8")
    (local_db_path.parent / "coproprietaires.sqlite-shm").write_text("shm", encoding="utf-8")
    monkeypatch.setattr(pcloud_mod, "get_db_path", lambda db_name=None: local_db_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "o")

    remote_entries = [
        {"name": "coproprietaires-31-07-2026-23-37.sqlite", "isfolder": False, "fileid": 99},
    ]
    sdk = DummySDK(
        folder=DummyFolder(existing=None),
        file_obj=DummyFile({99: {"name": "coproprietaires-31-07-2026-23-37.sqlite", "content": "backup"}}),
    )
    monkeypatch.setattr(
        pcloud_mod,
        "lister_fichiers_et_dossiers_pcloud",
        lambda sdk, folder_name, recursif=True, dossiers_dabord=True, folder_id=None: remote_entries,
    )

    result = pcloud_mod.telecharger_dernier_backup_pcloud(sdk, overwrite=None)

    assert result["downloaded"] is True
    assert local_db_path.read_text(encoding="utf-8") == "backup"
    assert not (local_db_path.parent / "coproprietaires.sqlite-wal").exists()
    assert not (local_db_path.parent / "coproprietaires.sqlite-shm").exists()
