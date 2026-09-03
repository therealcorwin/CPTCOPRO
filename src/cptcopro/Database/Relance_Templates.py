"""Gestion des templates d'email de relance (sujet + corps parametrables).

Un template est un couple (sujet, corps) contenant des placeholders du type
`{nom_proprietaire}` remplaces par les donnees reelles du coproprietaire au
moment de la generation du brouillon (voir `utils.relance_mailer.render_relance_template`).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from loguru import logger

logger = logger.bind(type_log="BDD")


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

# 'static': substitution directe des placeholders. 'llm': le sujet/corps servent
# de guide de contenu et de ton pour la generation par l'assistant IA.
GENERATION_MODES = ("static", "llm")

# Placeholders disponibles pour la redaction d'un template (documentation UI).
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


def init_relance_templates_if_missing(db_path: str) -> bool:
    """Cree un template par defaut si la table est vide."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM relance_template")
        if cur.fetchone()[0] > 0:
            return False
        cur.execute(
            """
            INSERT INTO relance_template (
                name, subject_template, body_template, generation_mode, tone_instruction, is_default
            )
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                DEFAULT_TEMPLATE_NAME,
                DEFAULT_TEMPLATE_SUBJECT,
                DEFAULT_TEMPLATE_BODY,
                "static",
                DEFAULT_TEMPLATE_TONE,
            ),
        )
        conn.commit()
        logger.info("Template de relance par defaut cree.")
        return True
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur initialisation relance_template: {exc}")
        raise
    finally:
        conn.close()


def list_relance_templates(db_path: str) -> list[dict[str, Any]]:
    """Liste tous les templates de relance (le template par defaut en premier)."""
    init_relance_templates_if_missing(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM relance_template ORDER BY is_default DESC, name ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_relance_template(db_path: str, template_id: int | None = None) -> dict[str, Any] | None:
    """Retourne un template par id, ou le template par defaut si `template_id` est None."""
    init_relance_templates_if_missing(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if template_id is not None:
            row = conn.execute(
                "SELECT * FROM relance_template WHERE template_id = ?",
                (int(template_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM relance_template WHERE is_default = 1 LIMIT 1"
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM relance_template ORDER BY template_id LIMIT 1"
                ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_relance_template(
    db_path: str,
    name: str,
    subject_template: str,
    body_template: str,
    generation_mode: str = "static",
    tone_instruction: str = "",
    is_default: bool = False,
) -> int:
    """Cree un nouveau template et retourne son identifiant."""
    name = (name or "").strip()
    subject_template = subject_template or ""
    body_template = body_template or ""
    generation_mode = (generation_mode or "static").strip().lower()
    if not name:
        raise ValueError("name vide")
    if not subject_template.strip():
        raise ValueError("subject_template vide")
    if not body_template.strip():
        raise ValueError("body_template vide")
    if generation_mode not in GENERATION_MODES:
        raise ValueError(f"generation_mode doit etre parmi {GENERATION_MODES}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        if is_default:
            cur.execute("UPDATE relance_template SET is_default = 0")
        cur.execute(
            """
            INSERT INTO relance_template (
                name, subject_template, body_template, generation_mode, tone_instruction, is_default
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                subject_template,
                body_template,
                generation_mode,
                (tone_instruction or "").strip(),
                1 if is_default else 0,
            ),
        )
        conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("INSERT did not return a lastrowid")
        return int(cur.lastrowid)
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur create_relance_template: {exc}")
        raise
    finally:
        conn.close()


def update_relance_template(
    db_path: str,
    template_id: int,
    name: str | None = None,
    subject_template: str | None = None,
    body_template: str | None = None,
    generation_mode: str | None = None,
    tone_instruction: str | None = None,
    is_default: bool | None = None,
) -> bool:
    """Met a jour un template existant (mise a jour partielle)."""
    updates: dict[str, Any] = {}
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("name vide")
        updates["name"] = name
    if subject_template is not None:
        if not subject_template.strip():
            raise ValueError("subject_template vide")
        updates["subject_template"] = subject_template
    if body_template is not None:
        if not body_template.strip():
            raise ValueError("body_template vide")
        updates["body_template"] = body_template
    if generation_mode is not None:
        generation_mode = generation_mode.strip().lower()
        if generation_mode not in GENERATION_MODES:
            raise ValueError(f"generation_mode doit etre parmi {GENERATION_MODES}")
        updates["generation_mode"] = generation_mode
    if tone_instruction is not None:
        updates["tone_instruction"] = tone_instruction.strip()
    if is_default is not None:
        updates["is_default"] = 1 if is_default else 0

    if not updates:
        return False

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        if updates.get("is_default") == 1:
            cur.execute("UPDATE relance_template SET is_default = 0")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = [*updates.values(), int(template_id)]
        cur.execute(
            f"UPDATE relance_template SET {set_clause}, updated_at = CURRENT_TIMESTAMP "  # nosec B608 — set_clause = ", ".join(f"{k} = ?" for k in updates) : clés dict interne, valeurs via "?"
            "WHERE template_id = ?",
            values,
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur update_relance_template: {exc}")
        raise
    finally:
        conn.close()


def delete_relance_template(db_path: str, template_id: int) -> bool:
    """Supprime un template. Refuse de supprimer le dernier template restant."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM relance_template")
        if cur.fetchone()[0] <= 1:
            raise ValueError("Impossible de supprimer le dernier template restant")

        cur.execute(
            "SELECT is_default FROM relance_template WHERE template_id = ?",
            (int(template_id),),
        )
        row = cur.fetchone()
        was_default = bool(row and row[0])

        cur.execute("DELETE FROM relance_template WHERE template_id = ?", (int(template_id),))
        deleted = cur.rowcount > 0

        if deleted and was_default:
            cur.execute(
                "UPDATE relance_template SET is_default = 1 "
                "WHERE template_id = (SELECT MIN(template_id) FROM relance_template)"
            )
        conn.commit()
        return deleted
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur delete_relance_template: {exc}")
        raise
    finally:
        conn.close()
