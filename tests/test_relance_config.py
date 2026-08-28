"""Tests des fonctionnalites de relance (config, destinataires, brouillons)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cptcopro import Database as dbmod
from cptcopro.utils.relance_mailer import generate_relance_draft_with_llm, render_relance_template
from cptcopro.utils import relance_mailer


def setup_db(path: Path) -> str:
    dbmod.integrite_db(str(path))
    return str(path)


def test_relance_tables_created(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_schema.db")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        for table_name in ["relance_config", "relance_destinataire", "relance_draft", "relance_template"]:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            assert cur.fetchone() is not None, f"Table {table_name} manquante"
    finally:
        conn.close()


def test_due_frequency_logic(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_due.db")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Copro + alerte active
        cur.execute(
            "INSERT INTO coproprietaires (nom_proprietaire, code_proprietaire, num_apt, type_apt) VALUES (?, ?, ?, ?)",
            ("Dupont", "D001", "1", "3p"),
        )
        cur.execute(
            """
            INSERT INTO alertes_debit_eleve (
                id_origin, nom_proprietaire, code_proprietaire, debit, type_alerte, date_origin,
                last_detection, first_detection, occurence
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_DATE, CURRENT_DATE, ?)
            """,
            (1, "Dupont", "D001", 3000.0, "3p", "2026-01-01", 1),
        )
        conn.commit()
    finally:
        conn.close()

    dbmod.update_relance_config(db_path, frequency_days=14)

    # Sans historique -> due
    rows = dbmod.list_relances_due(db_path)
    assert len(rows) == 1
    assert rows[0]["due"] == 1

    # Brouillon recent -> non due
    dbmod.save_relance_draft(
        db_path,
        code_proprietaire="D001",
        nom_proprietaire="Dupont",
        debit=3000.0,
        email_to="dupont@example.com",
        subject="Relance",
        body="Corps",
        llm_provider="mistral",
        llm_model="mistral-small-latest",
        status="draft_local",
    )
    rows_after = dbmod.list_relances_due(db_path)
    assert len(rows_after) == 1
    assert rows_after[0]["due"] == 0


def test_destinataire_upsert_and_fetch(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_destinataire.db")

    dbmod.upsert_relance_destinataire(db_path, "D777", "copro777@example.com", "Mme Test")
    dbmod.upsert_relance_destinataire(db_path, "D777", "copro777bis@example.com", "Mme Test")

    rows = dbmod.get_relance_destinataires(db_path)
    assert len(rows) == 1
    assert rows[0]["code_proprietaire"] == "D777"
    assert rows[0]["email_to"] == "copro777bis@example.com"


def test_draft_generation_falls_back_with_invalid_llm_configuration():
    subject, body, provider, model = generate_relance_draft_with_llm(
        {
            "nom_proprietaire": "Dupont",
            "debit": 125.50,
            "date_origin": "2026-08-01",
        },
        {
            "llm_provider": "mistral",
            "llm_temperature": "invalid",
            "llm_api_base": "http://127.0.0.1:1",
            "llm_api_key_env": "MISSING_RELANCE_KEY",
        },
    )

    assert subject.startswith("Relance charges copropriete - Dupont")
    assert "125.50 EUR" in body
    assert provider == "mistral"
    assert model == "mistral-small-latest"


def test_save_draft_to_imap_uses_xoauth2_and_appends_draft(monkeypatch):
    class FakeImap:
        def __init__(self):
            self.authenticated = None
            self.appended = None

        def authenticate(self, method, callback):
            self.authenticated = (method, callback(None))

        def append(self, folder, flags, internaldate, payload):
            self.appended = (folder, flags, payload)
            return "OK", [b"(APPENDUID 1 42)"]

        def logout(self):
            return "BYE", [b""]

    fake = FakeImap()
    monkeypatch.setenv("TEST_RELANCE_TOKEN", "header.payload.signature")
    monkeypatch.setattr(relance_mailer.imaplib, "IMAP4_SSL", lambda *args, **kwargs: fake)

    message = relance_mailer.build_email_message(
        "sender@hotmail.com", "Syndic", "dest@example.com", "Sujet", "Corps"
    )
    remote_id = relance_mailer.save_draft_to_imap(
        {
            "mailbox_imap_host": "outlook.office365.com",
            "mailbox_imap_user": "sender@hotmail.com",
            "mailbox_access_token_env": "TEST_RELANCE_TOKEN",
        },
        message,
    )

    assert remote_id == "(APPENDUID 1 42)"
    assert fake.authenticated[0] == "XOAUTH2"
    assert b"auth=Bearer header.payload.signature" in fake.authenticated[1]
    assert fake.appended[0:2] == ("Drafts", "\\Draft")


def test_mark_draft_status_keeps_remote_id(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_remote_id.db")
    draft_id = dbmod.save_relance_draft(
        db_path,
        code_proprietaire="D001",
        nom_proprietaire="Dupont",
        debit=100.0,
        email_to="dupont@example.com",
        subject="Relance",
        body="Corps",
        llm_provider="manual",
        llm_model="manual",
    )

    assert dbmod.mark_relance_draft_status(
        db_path, draft_id, "draft_imap", remote_draft_id="(APPENDUID 1 7)"
    )
    draft = dbmod.get_relance_drafts(db_path)[0]
    assert draft["status"] == "draft_imap"
    assert draft["remote_draft_id"] == "(APPENDUID 1 7)"


def test_non_oauth_value_uses_password_login(monkeypatch):
    class FakeImap:
        def __init__(self):
            self.login_args = None

        def login(self, user, password):
            self.login_args = (user, password)

        def append(self, folder, flags, internaldate, payload):
            return "OK", [b"(APPENDUID 1 8)"]

        def logout(self):
            return "BYE", [b""]

    fake = FakeImap()
    monkeypatch.setenv("TEST_RELANCE_VALUE", "not-an-oauth-token")
    monkeypatch.setenv("TEST_RELANCE_PASSWORD", "app-password")
    monkeypatch.setattr(relance_mailer.imaplib, "IMAP4_SSL", lambda *args, **kwargs: fake)

    message = relance_mailer.build_email_message(
        "sender@hotmail.com", "Syndic", "dest@example.com", "Sujet", "Corps"
    )
    relance_mailer.save_draft_to_imap(
        {
            "mailbox_imap_host": "outlook.office365.com",
            "mailbox_imap_user": "sender@hotmail.com",
            "mailbox_access_token_env": "TEST_RELANCE_VALUE",
            "mailbox_password_env": "TEST_RELANCE_PASSWORD",
        },
        message,
    )

    assert fake.login_args == ("sender@hotmail.com", "app-password")


def test_cached_oauth_token_is_preferred(monkeypatch):
    monkeypatch.setattr(
        relance_mailer,
        "get_hotmail_access_token",
        lambda config: "header.payload.signature",
    )
    monkeypatch.setenv("TEST_RELANCE_PASSWORD", "app-password")

    class FakeImap:
        def __init__(self):
            self.authenticated = None

        def authenticate(self, method, callback):
            self.authenticated = (method, callback(None))

        def append(self, folder, flags, internaldate, payload):
            return "OK", [b"(APPENDUID 1 9)"]

        def logout(self):
            return "BYE", [b""]

    fake = FakeImap()
    monkeypatch.setattr(relance_mailer.imaplib, "IMAP4_SSL", lambda *args, **kwargs: fake)
    message = relance_mailer.build_email_message(
        "sender@hotmail.com", "Syndic", "dest@example.com", "Sujet", "Corps"
    )
    relance_mailer.save_draft_to_imap(
        {
            "mailbox_imap_host": "outlook.office365.com",
            "mailbox_imap_user": "sender@hotmail.com",
            "mailbox_password_env": "TEST_RELANCE_PASSWORD",
        },
        message,
    )

    assert fake.authenticated[0] == "XOAUTH2"


def test_default_template_created_on_first_access(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_template_default.db")

    templates = dbmod.list_relance_templates(db_path)
    assert len(templates) == 1
    assert templates[0]["is_default"] == 1
    assert templates[0]["generation_mode"] == "static"


def test_create_update_delete_template(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_template_crud.db")
    dbmod.list_relance_templates(db_path)  # force creation du template par defaut

    template_id = dbmod.create_relance_template(
        db_path,
        name="Rappel courtois",
        subject_template="Rappel - {nom_proprietaire}",
        body_template="Bonjour {nom_proprietaire}, merci de regler {debit_fmt}.",
    )
    templates = dbmod.list_relance_templates(db_path)
    assert len(templates) == 2  # template par defaut + nouveau

    dbmod.update_relance_template(db_path, template_id, is_default=True)
    updated = dbmod.get_relance_template(db_path, template_id)
    assert updated["is_default"] == 1

    # Un seul template par defaut a la fois
    default_templates = [t for t in dbmod.list_relance_templates(db_path) if t["is_default"]]
    assert len(default_templates) == 1

    assert dbmod.delete_relance_template(db_path, template_id) is True
    remaining = dbmod.list_relance_templates(db_path)
    assert len(remaining) == 1


def test_delete_last_template_is_refused(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_template_delete_last.db")
    templates = dbmod.list_relance_templates(db_path)
    only_id = templates[0]["template_id"]

    try:
        dbmod.delete_relance_template(db_path, only_id)
        assert False, "La suppression du dernier template aurait du echouer"
    except ValueError:
        pass


def test_create_template_rejects_invalid_generation_mode(tmp_path: Path):
    db_path = setup_db(tmp_path / "relance_template_bad_mode.db")

    try:
        dbmod.create_relance_template(
            db_path,
            name="Invalide",
            subject_template="Sujet",
            body_template="Corps",
            generation_mode="bogus",
        )
        assert False, "generation_mode invalide aurait du echouer"
    except ValueError:
        pass


def test_render_relance_template_substitutes_placeholders():
    template = {
        "subject_template": "Relance {nom_proprietaire} - lot {num_apt}",
        "body_template": "Bonjour {nom_proprietaire}, solde de {debit_fmt} au {date_origin}. {sender_name}",
    }
    data = {
        "nom_proprietaire": "Dupont",
        "num_apt": "12",
        "debit": 150.5,
        "date_origin": "2026-08-01",
    }
    config = {"sender_name": "Le syndic"}

    subject, body = render_relance_template(template, data, config)

    assert subject == "Relance Dupont - lot 12"
    assert "150.50 EUR" in body


def test_generate_with_llm_uses_template_tone_and_guidance_on_fallback():
    template = {
        "subject_template": "Relance amicale - {nom_proprietaire}",
        "body_template": "Mentionner le solde {debit_fmt} et inviter au dialogue.",
        "generation_mode": "llm",
        "tone_instruction": "tres cordial et empathique",
    }
    subject, body, provider, model = generate_relance_draft_with_llm(
        {
            "nom_proprietaire": "Martin",
            "debit": 42.0,
            "date_origin": "2026-08-01",
        },
        {
            "llm_provider": "mistral",
            "llm_api_key_env": "MISSING_RELANCE_KEY",
        },
        template=template,
    )

    assert subject == "Relance amicale - Martin"
    assert "tres cordial et empathique" in body
    assert provider == "mistral"
    assert model == "mistral-small-latest"
    assert "Le syndic" in body

