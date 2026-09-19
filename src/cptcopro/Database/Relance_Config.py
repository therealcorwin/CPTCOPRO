"""Gestion des parametres et brouillons de relance coproprietaires (MariaDB).

Ce module centralise :
- La configuration de la frequence et du canal de brouillon de relance
- Le mapping coproprietaire -> adresse email de destination
- Le stockage/historique des brouillons generes
- La selection des coproprietaires debiteurs "dus" pour relance
- Synthese analytique optimisee via ROW_NUMBER()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from .connection import get_db_connection, get_db_cursor

_logger = logger.bind(type_log="BDD")


DEFAULT_RELANCE_CONFIG: dict[str, Any] = {
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


def init_relance_config_if_missing(db_path: str | None = None) -> bool:
    """Initialise la configuration de relance si absente."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM relance_config")
                row = cur.fetchone()
                if row and row["cnt"] > 0:
                    return False

                cur.execute(
                    """
                    INSERT INTO relance_config (
                        id,
                        enabled,
                        frequency_days,
                        sender_name,
                        sender_email,
                        mailbox_imap_host,
                        mailbox_imap_port,
                        mailbox_imap_user,
                        mailbox_drafts_folder,
                        mailbox_use_ssl,
                        mailbox_password_env,
                        mailbox_access_token_env,
                        llm_provider,
                        llm_model,
                        llm_api_base,
                        llm_api_key_env,
                        llm_temperature,
                        tone_instruction,
                        updated_at
                    )
                    VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        int(DEFAULT_RELANCE_CONFIG["enabled"]),
                        int(DEFAULT_RELANCE_CONFIG["frequency_days"]),
                        str(DEFAULT_RELANCE_CONFIG["sender_name"]),
                        str(DEFAULT_RELANCE_CONFIG["sender_email"]),
                        str(DEFAULT_RELANCE_CONFIG["mailbox_imap_host"]),
                        int(DEFAULT_RELANCE_CONFIG["mailbox_imap_port"]),
                        str(DEFAULT_RELANCE_CONFIG["mailbox_imap_user"]),
                        str(DEFAULT_RELANCE_CONFIG["mailbox_drafts_folder"]),
                        int(DEFAULT_RELANCE_CONFIG["mailbox_use_ssl"]),
                        str(DEFAULT_RELANCE_CONFIG["mailbox_password_env"]),
                        str(DEFAULT_RELANCE_CONFIG["mailbox_access_token_env"]),
                        str(DEFAULT_RELANCE_CONFIG["llm_provider"]),
                        str(DEFAULT_RELANCE_CONFIG["llm_model"]),
                        str(DEFAULT_RELANCE_CONFIG["llm_api_base"]),
                        str(DEFAULT_RELANCE_CONFIG["llm_api_key_env"]),
                        float(DEFAULT_RELANCE_CONFIG["llm_temperature"]),
                        str(DEFAULT_RELANCE_CONFIG["tone_instruction"]),
                    ),
                )
        _logger.info("Configuration de relance initialisee avec les valeurs par defaut.")
        return True
    except Exception as exc:
        _logger.error(f"Erreur initialisation relance_config: {exc}")
        raise


def get_relance_config(db_path: str | None = None) -> dict[str, Any]:
    """Retourne la configuration de relance (ligne unique)."""
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM relance_config WHERE id = 1")
        row = cur.fetchone()
        if row is None:
            init_relance_config_if_missing()
            cur.connection.commit()
            cur.execute("SELECT * FROM relance_config WHERE id = 1")
            row = cur.fetchone()

        if row is None:
            raise RuntimeError("Impossible de charger relance_config")
        return dict(row)


def update_relance_config(*args: Any, **kwargs: object) -> bool:
    """Met a jour la configuration de relance (ligne id=1)."""
    # Si db_path a ete passe en premier argument positionnel, on l'ignore
    allowed = {
        "enabled",
        "frequency_days",
        "sender_name",
        "sender_email",
        "mailbox_imap_host",
        "mailbox_imap_port",
        "mailbox_imap_user",
        "mailbox_drafts_folder",
        "mailbox_use_ssl",
        "mailbox_password_env",
        "mailbox_access_token_env",
        "llm_provider",
        "llm_model",
        "llm_api_base",
        "llm_api_key_env",
        "llm_temperature",
        "tone_instruction",
    }

    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    if "frequency_days" in updates:
        try:
            freq = int(str(updates["frequency_days"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("frequency_days doit etre un entier") from exc
        if freq <= 0:
            raise ValueError("frequency_days doit etre > 0")
        updates["frequency_days"] = freq

    if "mailbox_imap_port" in updates:
        updates["mailbox_imap_port"] = int(str(updates["mailbox_imap_port"]))

    if "llm_temperature" in updates:
        updates["llm_temperature"] = float(str(updates["llm_temperature"]))

    set_clause = ", ".join(f"{k} = %s" for k in updates.keys())
    values = list(updates.values())

    try:
        init_relance_config_if_missing()
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE relance_config SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = 1",  # nosec B608
                    values,
                )
                return bool(cur.rowcount > 0)
    except Exception as exc:
        _logger.error(f"Erreur update relance_config: {exc}")
        raise


def upsert_relance_destinataire(
    *args: Any,
    code_proprietaire: str | None = None,
    email_to: str | None = None,
    contact_name: str | None = None,
    nom_proprietaire: str | None = None,
    db_path: str | None = None,
) -> None:
    """Insere ou met a jour l'adresse email cible d'un coproprietaire (batch UPSERT MariaDB)."""
    default_contact = contact_name if contact_name is not None else nom_proprietaire
    # Extraction des parametres polymorphes (compatibilite ancien db_path positionnel)
    if len(args) >= 3:
        if "@" in str(args[1]):
            # args = (code_proprietaire, email_to, contact_name)
            code = str(args[0])
            email = str(args[1])
            contact = str(args[2]) if len(args) > 2 else default_contact
        else:
            # args = (db_path, code_proprietaire, email_to, contact_name?)
            code = str(args[1])
            email = str(args[2])
            contact = str(args[3]) if len(args) > 3 else default_contact
    elif len(args) == 2:
        if "@" in str(args[1]):
            code = str(args[0])
            email = str(args[1])
            contact = default_contact
        else:
            code = str(args[1])
            email = str(email_to or "")
            contact = default_contact
    elif len(args) == 1:
        if code_proprietaire is None:
            code = str(args[0])
            email = str(email_to or "")
            contact = default_contact
        else:
            code = str(code_proprietaire)
            email = str(email_to or "")
            contact = default_contact
    else:
        code = str(code_proprietaire or "")
        email = str(email_to or "")
        contact = default_contact

    code = (code or "").strip()
    email = (email or "").strip()
    if not code:
        raise ValueError("code_proprietaire vide")
    if not email:
        raise ValueError("email_to vide")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO relance_destinataire (code_proprietaire, email_to, contact_name, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE
                        email_to = VALUES(email_to),
                        contact_name = COALESCE(VALUES(contact_name), relance_destinataire.contact_name),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (code, email, (contact or "").strip() or None),
                )
    except Exception as exc:
        _logger.error(f"Erreur upsert relance_destinataire: {exc}")
        raise


def get_relance_destinataires(db_path: str | None = None) -> list[dict[str, Any]]:
    """Retourne les destinataires configures pour les relances."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT code_proprietaire, email_to, contact_name, updated_at
            FROM relance_destinataire
            ORDER BY code_proprietaire
            """
        )
        return list(cur.fetchall())


def get_copro_notes(code_proprietaire: str) -> str:
    """Retourne les notes internes et promesses de paiement associees a un coproprietaire."""
    code = (code_proprietaire or "").strip()
    if not code:
        return ""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT notes FROM relance_destinataire
                WHERE code_proprietaire = %s
                """,
                (code,),
            )
            row = cur.fetchone()
            if row and row.get("notes"):
                return str(row["notes"])
    except Exception as exc:
        _logger.warning(f"Erreur lecture notes coproprietaire {code}: {exc}")
    return ""


def save_copro_notes(code_proprietaire: str, notes: str) -> None:
    """Enregistre ou met a jour les notes internes pour un coproprietaire."""
    code = (code_proprietaire or "").strip()
    if not code:
        raise ValueError("code_proprietaire vide")
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Ensure notes column exists in relance_destinataire
                try:
                    cur.execute("ALTER TABLE relance_destinataire ADD COLUMN IF NOT EXISTS notes TEXT")
                except Exception as exc:
                    _logger.debug(f"ALTER TABLE relance_destinataire note column: {exc}")
                cur.execute(
                    """
                    INSERT INTO relance_destinataire (code_proprietaire, email_to, notes, updated_at)
                    VALUES (%s, '', %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE
                        notes = VALUES(notes),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (code, notes.strip()),
                )
    except Exception as exc:
        _logger.error(f"Erreur sauvegarde notes coproprietaire {code}: {exc}")
        raise


def list_relances_due(
    db_path: str | None = None,
    frequency_days: int | None = None,
) -> list[dict[str, Any]]:
    """Retourne les coproprietaires en debit eligibles a une nouvelle relance."""
    if isinstance(db_path, int) and frequency_days is None:
        frequency_days = db_path

    if frequency_days is None:
        cfg = get_relance_config()
        frequency_days = int(cfg.get("frequency_days", 14) or 14)

    with get_db_cursor() as cur:
        cur.execute(
            """
            WITH stats_relance AS (
                SELECT
                    code_proprietaire,
                    MIN(date(COALESCE(sent_at, created_at))) AS first_relance_date,
                    MAX(date(COALESCE(sent_at, created_at))) AS last_relance_date,
                    COUNT(CASE WHEN status IN ('draft_imap', 'sent', 'validated') THEN 1 END) AS nb_relances_total
                FROM relance_draft
                WHERE status IN ('draft_local', 'draft_imap', 'validated', 'sent')
                GROUP BY code_proprietaire
            )
            SELECT
                a.code_proprietaire,
                a.nom_proprietaire,
                a.debit,
                a.type_alerte,
                a.date_origin,
                COALESCE(c.num_apt, 'NA') AS num_apt,
                COALESCE(c.type_apt, 'NA') AS type_apt,
                d.email_to,
                d.contact_name,
                sr.first_relance_date,
                sr.last_relance_date,
                COALESCE(sr.nb_relances_total, 0) AS nb_relances_total,
                DATEDIFF(NOW(), sr.last_relance_date) AS jours_depuis_derniere_relance,
                CASE
                    WHEN sr.last_relance_date IS NULL THEN 1
                    WHEN DATEDIFF(NOW(), sr.last_relance_date) >= %s THEN 1
                    ELSE 0
                END AS due
            FROM alertes_debit_eleve a
            LEFT JOIN coproprietaires c
                ON c.code_proprietaire = a.code_proprietaire
            LEFT JOIN relance_destinataire d
                ON d.code_proprietaire = a.code_proprietaire
            LEFT JOIN stats_relance sr
                ON sr.code_proprietaire = a.code_proprietaire
            ORDER BY a.debit DESC, a.nom_proprietaire ASC
            """,
            (frequency_days,),
        )
        return list(cur.fetchall())


def save_relance_draft(
    *args: Any,
    code_proprietaire: str | None = None,
    nom_proprietaire: str | None = None,
    debit: float | None = None,
    email_to: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    status: str = "draft_local",
    remote_draft_id: str | None = None,
    error_message: str | None = None,
    draft_id: int | None = None,
    db_path: str | None = None,
) -> int:
    """Enregistre ou met a jour un brouillon de relance en base et retourne son identifiant."""
    # Polymorphisme : detection du 1er argument db_path
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
        elif len(pos) >= 9 and isinstance(pos[4], (int, float)):
            pos = pos[1:]

        if len(pos) >= 1 and code_proprietaire is None:
            code_proprietaire = pos[0]
        if len(pos) >= 2 and nom_proprietaire is None:
            nom_proprietaire = pos[1]
        if len(pos) >= 3 and debit is None:
            debit = pos[2]
        if len(pos) >= 4 and email_to is None:
            email_to = pos[3]
        if len(pos) >= 5 and subject is None:
            subject = pos[4]
        if len(pos) >= 6 and body is None:
            body = pos[5]
        if len(pos) >= 7 and llm_provider is None:
            llm_provider = pos[6]
        if len(pos) >= 8 and llm_model is None:
            llm_model = pos[7]
        if len(pos) >= 9:
            status = pos[8]
        if len(pos) >= 10:
            remote_draft_id = pos[9]
        if len(pos) >= 11:
            error_message = pos[10]
        if len(pos) >= 12:
            draft_id = pos[11]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if draft_id is not None:
                    update_sent_clause = (
                        ", sent_at = COALESCE(sent_at, CURRENT_TIMESTAMP)"
                        if status in ("draft_imap", "sent")
                        else ""
                    )
                    sql_update = f"""
                        UPDATE relance_draft
                        SET code_proprietaire = %s, nom_proprietaire = %s, debit = %s,
                            email_to = %s, subject = %s, body = %s, llm_provider = %s,
                            llm_model = %s, status = %s, remote_draft_id = %s,
                            error_message = %s {update_sent_clause}
                        WHERE draft_id = %s
                    """  # nosec B608
                    cur.execute(
                        sql_update,
                        (
                            (code_proprietaire or "").strip(),
                            (nom_proprietaire or "").strip(),
                            float(debit or 0.0),
                            (email_to or "").strip(),
                            subject,
                            body,
                            llm_provider,
                            llm_model,
                            status,
                            remote_draft_id,
                            error_message,
                            int(draft_id),
                        ),
                    )
                    return int(draft_id)
                else:
                    sent_at_val = (
                        "CURRENT_TIMESTAMP" if status in ("draft_imap", "sent") else "NULL"
                    )
                    sql_insert = f"""
                        INSERT INTO relance_draft (
                            code_proprietaire, nom_proprietaire, debit, email_to,
                            subject, body, llm_provider, llm_model, status,
                            remote_draft_id, error_message, sent_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, {sent_at_val})
                    """  # nosec B608
                    cur.execute(
                        sql_insert,
                        (
                            (code_proprietaire or "").strip(),
                            (nom_proprietaire or "").strip(),
                            float(debit or 0.0),
                            (email_to or "").strip(),
                            subject,
                            body,
                            llm_provider,
                            llm_model,
                            status,
                            remote_draft_id,
                            error_message,
                        ),
                    )
                    if cur.lastrowid is None:
                        raise RuntimeError("INSERT did not return a lastrowid")
                    return int(cur.lastrowid)
    except Exception as exc:
        _logger.error(f"Erreur save_relance_draft: {exc}")
        raise


def get_relance_drafts(
    *args: Any,
    status: str | None = None,
    code_proprietaire: str | None = None,
    limit: int = 200,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Liste les brouillons de relance, les plus recents d'abord."""
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
        if pos and status is None and isinstance(pos[0], (str, type(None))):
            status = pos[0]
            if len(pos) > 1 and isinstance(pos[1], int):
                limit = pos[1]

    with get_db_cursor() as cur:
        query = """
            SELECT
                draft_id,
                code_proprietaire,
                nom_proprietaire,
                debit,
                email_to,
                subject,
                body,
                llm_provider,
                llm_model,
                status,
                remote_draft_id,
                error_message,
                created_at,
                validated_at,
                sent_at
            FROM relance_draft
        """
        params: list[Any] = []
        where_clauses = []
        if status:
            where_clauses.append("status = %s")
            params.append(status)
        else:
            where_clauses.append("status != %s")
            params.append("deleted")

        if code_proprietaire:
            where_clauses.append("code_proprietaire = %s")
            params.append(code_proprietaire.strip())

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        # MariaDB trie DATETIME nativement, datetime(created_at) est inutile
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(int(limit))

        cur.execute(query, params)
        return list(cur.fetchall())


def mark_relance_draft_status(
    *args: Any,
    draft_id: int | None = None,
    status: str | None = None,
    error_message: str | None = None,
    remote_draft_id: str | None = None,
    db_path: str | None = None,
) -> bool:
    """Met a jour le statut d'un brouillon."""
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
        elif len(pos) > 1 and not isinstance(pos[0], int) and isinstance(pos[1], int):
            pos = pos[1:]
        if pos and draft_id is None:
            draft_id = int(pos[0])
            if len(pos) > 1 and status is None:
                status = str(pos[1])
            if len(pos) > 2 and error_message is None:
                error_message = pos[2]
            if len(pos) > 3 and remote_draft_id is None:
                remote_draft_id = pos[3]

    stat = (status or "").strip().lower()
    if not stat:
        raise ValueError("status vide")
    if draft_id is None:
        raise ValueError("draft_id manquant")

    fields = ["status = %s", "error_message = %s"]
    params: list[Any] = [stat, error_message]
    if remote_draft_id is not None:
        fields.append("remote_draft_id = %s")
        params.append(remote_draft_id)

    if stat == "validated":
        fields.append("validated_at = COALESCE(validated_at, CURRENT_TIMESTAMP)")
    if stat in ("sent", "draft_imap"):
        fields.append("sent_at = COALESCE(sent_at, CURRENT_TIMESTAMP)")
        fields.append("validated_at = COALESCE(validated_at, CURRENT_TIMESTAMP)")

    params.append(int(draft_id))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE relance_draft SET {', '.join(fields)} WHERE draft_id = %s",  # nosec B608
                    params,
                )
                return bool(cur.rowcount > 0)
    except Exception as exc:
        _logger.error(f"Erreur mark_relance_draft_status: {exc}")
        raise


def get_relances_tracking_summary(db_path: str | None = None) -> list[dict[str, Any]]:
    """Synthese analytique du suivi des relances avec optimisation ROW_NUMBER()."""
    with get_db_cursor() as cur:
        query = """
            WITH stats_envoyes AS (
                SELECT
                    code_proprietaire,
                    MIN(date(COALESCE(sent_at, created_at))) AS first_relance_date,
                    MAX(date(COALESCE(sent_at, created_at))) AS last_relance_date,
                    COUNT(CASE WHEN status IN ('draft_imap', 'sent', 'validated') THEN 1 END) AS nb_relances_envoyees,
                    COUNT(CASE WHEN status = 'draft_local' THEN 1 END) AS nb_brouillons_locaux,
                    COUNT(CASE WHEN status = 'error' THEN 1 END) AS nb_erreurs,
                    COUNT(*) AS nb_total_brouillons
                FROM relance_draft
                WHERE status != 'deleted'
                GROUP BY code_proprietaire
            ),
            last_draft AS (
                SELECT
                    code_proprietaire,
                    dernier_sujet,
                    dernier_statut,
                    dernier_provider,
                    dernier_debit_relance,
                    dernier_created_at
                FROM (
                    SELECT
                        code_proprietaire,
                        subject AS dernier_sujet,
                        status AS dernier_statut,
                        llm_provider AS dernier_provider,
                        debit AS dernier_debit_relance,
                        created_at AS dernier_created_at,
                        ROW_NUMBER() OVER (PARTITION BY code_proprietaire ORDER BY draft_id DESC) AS rn
                    FROM relance_draft
                    WHERE status != 'deleted'
                ) ranked
                WHERE rn = 1
            )
            SELECT
                COALESCE(c.code_proprietaire, s.code_proprietaire, a.code_proprietaire) AS code_proprietaire,
                COALESCE(a.nom_proprietaire, c.nom_proprietaire, 'Inconnu') AS nom_proprietaire,
                COALESCE(c.num_apt, 'NA') AS num_apt,
                COALESCE(c.type_apt, 'NA') AS type_apt,
                COALESCE(d.email_to, '') AS email_to,
                COALESCE(a.debit, 0.0) AS debit_actuel,
                a.date_origin AS date_situation,
                COALESCE(s.nb_relances_envoyees, 0) AS nb_relances_envoyees,
                COALESCE(s.nb_brouillons_locaux, 0) AS nb_brouillons_locaux,
                COALESCE(s.nb_erreurs, 0) AS nb_erreurs,
                COALESCE(s.nb_total_brouillons, 0) AS nb_total_brouillons,
                s.first_relance_date,
                s.last_relance_date,
                DATEDIFF(NOW(), s.last_relance_date) AS jours_depuis_derniere_relance,
                ld.dernier_sujet,
                ld.dernier_statut,
                ld.dernier_provider,
                ld.dernier_debit_relance
            FROM (
                SELECT DISTINCT code_proprietaire FROM relance_draft WHERE status != 'deleted'
                UNION
                SELECT DISTINCT code_proprietaire FROM alertes_debit_eleve
            ) base
            LEFT JOIN coproprietaires c ON c.code_proprietaire = base.code_proprietaire
            LEFT JOIN alertes_debit_eleve a ON a.code_proprietaire = base.code_proprietaire
            LEFT JOIN relance_destinataire d ON d.code_proprietaire = base.code_proprietaire
            LEFT JOIN stats_envoyes s ON s.code_proprietaire = base.code_proprietaire
            LEFT JOIN last_draft ld ON ld.code_proprietaire = base.code_proprietaire
            ORDER BY
                CASE WHEN a.debit IS NOT NULL AND a.debit > 0 THEN 0 ELSE 1 END,
                COALESCE(a.debit, 0.0) DESC,
                COALESCE(s.nb_relances_envoyees, 0) DESC
        """
        cur.execute(query)
        return list(cur.fetchall())
