"""Gestion des paramètres et brouillons de relance copropriétaires.

Ce module centralise:
- La configuration de la fréquence et du canal de brouillon de relance
- Le mapping copropriétaire -> adresse email de destination
- Le stockage/historique des brouillons générés
- La sélection des copropriétaires débiteurs "dus" pour relance
"""

from __future__ import annotations

import sqlite3
from typing import Any

from loguru import logger

logger = logger.bind(type_log="BDD")


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


def init_relance_config_if_missing(db_path: str) -> bool:
    """Initialise la configuration de relance si absente."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM relance_config")
        count = cur.fetchone()[0]
        if count > 0:
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
                tone_instruction
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        conn.commit()
        logger.info("Configuration de relance initialisee avec les valeurs par defaut.")
        return True
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur initialisation relance_config: {exc}")
        raise
    finally:
        conn.close()


def get_relance_config(db_path: str) -> dict[str, Any]:
    """Retourne la configuration de relance (ligne unique)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM relance_config WHERE id = 1").fetchone()
        if row is None:
            init_relance_config_if_missing(db_path)
            row = conn.execute("SELECT * FROM relance_config WHERE id = 1").fetchone()

        if row is None:
            raise RuntimeError("Impossible de charger relance_config")
        return dict(row)
    finally:
        conn.close()


def update_relance_config(db_path: str, **kwargs: object) -> bool:
    """Met a jour la configuration de relance (ligne id=1)."""
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

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values())

    conn = sqlite3.connect(db_path)
    try:
        init_relance_config_if_missing(db_path)
        cur = conn.cursor()
        cur.execute(
            f"UPDATE relance_config SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = 1",  # nosec B608 — set_clause = ", ".join(f"{k} = ?" for k in updates) : clés dict interne, valeurs via "?"
            values,
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur update relance_config: {exc}")
        raise
    finally:
        conn.close()


def upsert_relance_destinataire(
    db_path: str,
    code_proprietaire: str,
    email_to: str,
    contact_name: str | None = None,
) -> None:
    """Insere ou met a jour l'adresse email cible d'un coproprietaire."""
    code = (code_proprietaire or "").strip()
    email = (email_to or "").strip()
    if not code:
        raise ValueError("code_proprietaire vide")
    if not email:
        raise ValueError("email_to vide")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO relance_destinataire (code_proprietaire, email_to, contact_name, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(code_proprietaire) DO UPDATE SET
                email_to = excluded.email_to,
                contact_name = COALESCE(excluded.contact_name, relance_destinataire.contact_name),
                updated_at = CURRENT_TIMESTAMP
            """,
            (code, email, (contact_name or "").strip() or None),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur upsert relance_destinataire: {exc}")
        raise
    finally:
        conn.close()


def get_relance_destinataires(db_path: str) -> list[dict[str, Any]]:
    """Retourne les destinataires configures pour les relances."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT code_proprietaire, email_to, contact_name, updated_at
            FROM relance_destinataire
            ORDER BY code_proprietaire
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_relances_due(db_path: str) -> list[dict[str, Any]]:
    """Retourne les coproprietaires en debit eligibles a une nouvelle relance."""
    cfg = get_relance_config(db_path)
    frequency_days = int(cfg.get("frequency_days", 14) or 14)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
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
                CAST(julianday('now') - julianday(sr.last_relance_date) AS INTEGER) AS jours_depuis_derniere_relance,
                CASE
                    WHEN sr.last_relance_date IS NULL THEN 1
                    WHEN julianday('now') - julianday(sr.last_relance_date) >= ? THEN 1
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
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_relance_draft(
    db_path: str,
    code_proprietaire: str,
    nom_proprietaire: str,
    debit: float,
    email_to: str,
    subject: str,
    body: str,
    llm_provider: str,
    llm_model: str,
    status: str = "draft_local",
    remote_draft_id: str | None = None,
    error_message: str | None = None,
    draft_id: int | None = None,
) -> int:
    """Enregistre ou met a jour un brouillon de relance en base et retourne son identifiant.

    Si draft_id est fourni, fait un UPDATE, sinon un INSERT.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        if draft_id is not None:
            # Mise a jour d'un brouillon existant
            update_sent_clause = (
                ", sent_at = COALESCE(sent_at, CURRENT_TIMESTAMP)"
                if status in ("draft_imap", "sent")
                else ""
            )
            # nosec B608 — update_sent_clause est une constante SQL littérale choisie parmi 2 valeurs hardcodées, aucune entrée utilisateur
            sql_update = f"UPDATE relance_draft SET code_proprietaire = ?, nom_proprietaire = ?, debit = ?, email_to = ?, subject = ?, body = ?, llm_provider = ?, llm_model = ?, status = ?, remote_draft_id = ?, error_message = ? {update_sent_clause} WHERE draft_id = ?"  # nosec B608
            cur.execute(
                sql_update,
                (
                    (code_proprietaire or "").strip(),
                    (nom_proprietaire or "").strip(),
                    float(debit),
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
            conn.commit()
            return int(draft_id)
        else:
            # Nouveau brouillon, insertion
            sent_at_val = "CURRENT_TIMESTAMP" if status in ("draft_imap", "sent") else "NULL"
            # nosec B608 — sent_at_val vaut "CURRENT_TIMESTAMP" ou "NULL" : 2 constantes SQL hardcodées, aucune entrée utilisateur
            sql_insert = f"INSERT INTO relance_draft (code_proprietaire, nom_proprietaire, debit, email_to, subject, body, llm_provider, llm_model, status, remote_draft_id, error_message, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {sent_at_val})"  # nosec B608
            cur.execute(
                sql_insert,
                (
                    (code_proprietaire or "").strip(),
                    (nom_proprietaire or "").strip(),
                    float(debit),
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
            conn.commit()
            if cur.lastrowid is None:
                raise RuntimeError("INSERT did not return a lastrowid")
            return int(cur.lastrowid)
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur save_relance_draft: {exc}")
        raise
    finally:
        conn.close()


def get_relance_drafts(
    db_path: str,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Liste les brouillons de relance, les plus recents d'abord."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
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
            where_clauses.append("status = ?")
            params.append(status)
        else:
            where_clauses.append("status != ?")
            params.append("deleted")

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params.append(int(limit))

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_relance_draft_status(
    db_path: str,
    draft_id: int,
    status: str,
    error_message: str | None = None,
    remote_draft_id: str | None = None,
) -> bool:
    """Met a jour le statut d'un brouillon (validated/sent/draft_imap/error/etc.)."""
    status = (status or "").strip().lower()
    if not status:
        raise ValueError("status vide")

    fields = ["status = ?", "error_message = ?"]
    params: list[Any] = [status, error_message]
    if remote_draft_id is not None:
        fields.append("remote_draft_id = ?")
        params.append(remote_draft_id)

    if status == "validated":
        fields.append("validated_at = COALESCE(validated_at, CURRENT_TIMESTAMP)")
    if status in ("sent", "draft_imap"):
        fields.append("sent_at = COALESCE(sent_at, CURRENT_TIMESTAMP)")
        fields.append("validated_at = COALESCE(validated_at, CURRENT_TIMESTAMP)")

    params.append(int(draft_id))

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE relance_draft SET {', '.join(fields)} WHERE draft_id = ?",  # nosec B608 — fields = liste de chaînes SQL statiques hardcodées dans le code, aucune entrée utilisateur
            params,
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as exc:
        conn.rollback()
        logger.error(f"Erreur mark_relance_draft_status: {exc}")
        raise
    finally:
        conn.close()


def get_relances_tracking_summary(db_path: str) -> list[dict[str, Any]]:
    """Retourne la synthèse analytique du suivi des relances par copropriétaire.

    Fournit pour chaque copropriétaire :
    - Premier envoi, dernier envoi
    - Nombre de relances envoyées
    - Nombre de brouillons en cours
    - Débit actuel et statut de suivi
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
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
                    rd.code_proprietaire,
                    rd.subject AS dernier_sujet,
                    rd.status AS dernier_statut,
                    rd.llm_provider AS dernier_provider,
                    rd.debit AS dernier_debit_relance,
                    rd.created_at AS dernier_created_at
                FROM relance_draft rd
                INNER JOIN (
                    SELECT code_proprietaire, MAX(draft_id) AS max_id
                    FROM relance_draft
                    WHERE status != 'deleted'
                    GROUP BY code_proprietaire
                ) sub ON rd.draft_id = sub.max_id
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
                CAST(julianday('now') - julianday(s.last_relance_date) AS INTEGER) AS jours_depuis_derniere_relance,
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
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
