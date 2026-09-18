"""Gestion des templates d email de relance (MariaDB).

Un template est un couple (sujet, corps) contenant des placeholders du type
`{nom_proprietaire}` remplaces par les donnees reelles du coproprietaire au
moment de la generation du brouillon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from .connection import get_db_connection, get_db_cursor

_logger = logger.bind(type_log="BDD")

DEFAULT_TEMPLATE_NAME = "Standard"
DEFAULT_TEMPLATE_SUBJECT = "Relance charges copropriete - {nom_proprietaire} ({date_origin})"
DEFAULT_TEMPLATE_BODY = (
    "Bonjour {nom_proprietaire},\n\n"
    "A la date du {date_origin}, un solde debiteur de {debit_fmt} est constate "
    "sur votre lot {num_apt} ({type_apt}).\n\n"
    "Nous vous remercions de proceder au reglement dans les meilleurs delais "
    "ou de contacter l'administration si vous constatez une anomalie.\n\n"
    "Cordialement,\n"
    "{sender_name}"
)
DEFAULT_TEMPLATE_TONE = "courtois, professionnel et ferme"

GENERATION_MODES = ("static", "llm")

TEMPLATE_PLACEHOLDERS = [
    "nom_proprietaire",
    "code_proprietaire",
    "debit",
    "debit_fmt",
    "num_apt",
    "type_apt",
    "date_origin",
    "sender_name",
    "sender_email",
    "tone_instruction",
    "frequency_days",
]


def init_relance_templates_if_missing(db_path: str | None = None) -> bool:
    """Cree un template par defaut si la table est vide."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM relance_template")
                row = cur.fetchone()
                if row and row["cnt"] > 0:
                    return False
                cur.execute(
                    """
                    INSERT INTO relance_template (
                        name, subject_template, body_template, generation_mode, tone_instruction, is_default
                    )
                    VALUES (%s, %s, %s, %s, %s, 1)
                    """,
                    (
                        DEFAULT_TEMPLATE_NAME,
                        DEFAULT_TEMPLATE_SUBJECT,
                        DEFAULT_TEMPLATE_BODY,
                        "static",
                        DEFAULT_TEMPLATE_TONE,
                    ),
                )
        _logger.info("Template de relance par defaut cree.")
        return True
    except Exception as exc:
        _logger.error(f"Erreur initialisation relance_template: {exc}")
        raise


def list_relance_templates(db_path: str | None = None) -> list[dict[str, Any]]:
    """Liste tous les templates de relance (le template par defaut en premier)."""
    init_relance_templates_if_missing()
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM relance_template ORDER BY is_default DESC, name ASC")
        return list(cur.fetchall())


def get_relance_template(
    *args: Any,
    template_id: int | None = None,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """Retourne un template par id, ou le template par defaut si `template_id` est None."""
    pos = list(args)
    if pos:
        if (
            pos[0] is None
            or isinstance(pos[0], Path)
            or (
                isinstance(pos[0], str)
                and ("/" in pos[0] or "\\" in pos[0] or ".sqlite" in pos[0] or ".db" in pos[0])
            )
        ):
            pos = pos[1:]
        if pos and template_id is None:
            template_id = pos[0]

    init_relance_templates_if_missing()
    with get_db_cursor() as cur:
        if template_id is not None:
            cur.execute(
                "SELECT * FROM relance_template WHERE template_id = %s",
                (int(template_id),),
            )
            row = cur.fetchone()
        else:
            cur.execute("SELECT * FROM relance_template WHERE is_default = 1 LIMIT 1")
            row = cur.fetchone()
            if row is None:
                cur.execute("SELECT * FROM relance_template ORDER BY template_id LIMIT 1")
                row = cur.fetchone()
        return dict(row) if row else None


def create_relance_template(
    *args: Any,
    name: str | None = None,
    subject_template: str | None = None,
    body_template: str | None = None,
    generation_mode: str = "static",
    tone_instruction: str = "",
    is_default: bool = False,
    db_path: str | None = None,
) -> int:
    """Cree un nouveau template et retourne son identifiant."""
    pos = list(args)
    if pos and (
        pos[0] is None
        or isinstance(pos[0], Path)
        or (
            isinstance(pos[0], str)
            and ("/" in pos[0] or "\\" in pos[0] or ".sqlite" in pos[0] or ".db" in pos[0])
        )
    ):
        pos = pos[1:]

    if pos:
        if len(pos) >= 1 and name is None:
            name = pos[0]
        if len(pos) >= 2 and subject_template is None:
            subject_template = pos[1]
        if len(pos) >= 3 and body_template is None:
            body_template = pos[2]
        if len(pos) >= 4:
            generation_mode = pos[3]
        if len(pos) >= 5:
            tone_instruction = pos[4]
        if len(pos) >= 6:
            is_default = bool(pos[5])

    nm = (name or "").strip()
    subj = subject_template or ""
    body = body_template or ""
    gen_mode = (generation_mode or "static").strip().lower()
    if not nm:
        raise ValueError("name vide")
    if not subj.strip():
        raise ValueError("subject_template vide")
    if not body.strip():
        raise ValueError("body_template vide")
    if gen_mode not in GENERATION_MODES:
        raise ValueError(f"generation_mode doit etre parmi {GENERATION_MODES}")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if is_default:
                    cur.execute("UPDATE relance_template SET is_default = 0")
                cur.execute(
                    """
                    INSERT INTO relance_template (
                        name, subject_template, body_template, generation_mode, tone_instruction, is_default
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        nm,
                        subj,
                        body,
                        gen_mode,
                        (tone_instruction or "").strip(),
                        1 if is_default else 0,
                    ),
                )
                if cur.lastrowid is None:
                    raise RuntimeError("INSERT did not return a lastrowid")
                return int(cur.lastrowid)
    except Exception as exc:
        _logger.error(f"Erreur create_relance_template: {exc}")
        raise


def update_relance_template(
    *args: Any,
    template_id: int | None = None,
    name: str | None = None,
    subject_template: str | None = None,
    body_template: str | None = None,
    generation_mode: str | None = None,
    tone_instruction: str | None = None,
    is_default: bool | None = None,
    db_path: str | None = None,
) -> bool:
    """Met a jour un template existant."""
    pos = list(args)
    if pos and (
        pos[0] is None
        or isinstance(pos[0], Path)
        or (
            isinstance(pos[0], str)
            and ("/" in pos[0] or "\\" in pos[0] or ".sqlite" in pos[0] or ".db" in pos[0])
        )
    ):
        pos = pos[1:]
    if pos and template_id is None:
        template_id = int(pos[0])

    if template_id is None:
        raise ValueError("template_id manquant")

    updates: dict[str, Any] = {}
    if name is not None:
        nm = name.strip()
        if not nm:
            raise ValueError("name vide")
        updates["name"] = nm
    if subject_template is not None:
        if not subject_template.strip():
            raise ValueError("subject_template vide")
        updates["subject_template"] = subject_template
    if body_template is not None:
        if not body_template.strip():
            raise ValueError("body_template vide")
        updates["body_template"] = body_template
    if generation_mode is not None:
        gen_mode = generation_mode.strip().lower()
        if gen_mode not in GENERATION_MODES:
            raise ValueError(f"generation_mode doit etre parmi {GENERATION_MODES}")
        updates["generation_mode"] = gen_mode
    if tone_instruction is not None:
        updates["tone_instruction"] = tone_instruction.strip()
    if is_default is not None:
        updates["is_default"] = 1 if is_default else 0

    if not updates:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if updates.get("is_default") == 1:
                    cur.execute("UPDATE relance_template SET is_default = 0")
                set_clause = ", ".join(f"{k} = %s" for k in updates)
                values = [*updates.values(), int(template_id)]
                cur.execute(
                    f"UPDATE relance_template SET {set_clause}, updated_at = CURRENT_TIMESTAMP "  # nosec B608
                    "WHERE template_id = %s",
                    values,
                )
                return bool(cur.rowcount > 0)
    except Exception as exc:
        _logger.error(f"Erreur update_relance_template: {exc}")
        raise


def delete_relance_template(
    *args: Any, template_id: int | None = None, db_path: str | None = None
) -> bool:
    """Supprime un template. Refuse de supprimer le dernier template restant."""
    pos = list(args)
    if pos and (
        pos[0] is None
        or isinstance(pos[0], Path)
        or (
            isinstance(pos[0], str)
            and ("/" in pos[0] or "\\" in pos[0] or ".sqlite" in pos[0] or ".db" in pos[0])
        )
    ):
        pos = pos[1:]
    if pos and template_id is None:
        template_id = int(pos[0])

    if template_id is None:
        raise ValueError("template_id manquant")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM relance_template")
                row = cur.fetchone()
                if row and row["cnt"] <= 1:
                    raise ValueError("Impossible de supprimer le dernier template restant")

                cur.execute(
                    "SELECT is_default FROM relance_template WHERE template_id = %s",
                    (int(template_id),),
                )
                r = cur.fetchone()
                was_default = bool(r and r["is_default"])

                cur.execute(
                    "DELETE FROM relance_template WHERE template_id = %s", (int(template_id),)
                )
                deleted = cur.rowcount > 0

                if deleted and was_default:
                    # En MariaDB : UPDATE ... ORDER BY ... LIMIT 1
                    cur.execute(
                        "UPDATE relance_template SET is_default = 1 ORDER BY template_id ASC LIMIT 1"
                    )
                return bool(deleted)
    except Exception as exc:
        _logger.error(f"Erreur delete_relance_template: {exc}")
        raise
