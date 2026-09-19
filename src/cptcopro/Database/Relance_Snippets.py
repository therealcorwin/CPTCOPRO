"""Gestion des paragraphes types de relance (snippets MariaDB).

Permet à l'utilisateur de définir, modifier, supprimer et insérer des blocs
de texte prédéfinis (ex: constat d'impayé, coordonnées bancaires, signature, etc.)
directement dans les courriers de relance.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from .connection import get_db_connection, get_db_cursor

_logger = logger.bind(type_log="BDD")

DEFAULT_SNIPPETS: list[dict[str, Any]] = [
    {
        "title": "📌 Constat de solde débiteur & Lot",
        "content": (
            "À la date du {date_origin}, un solde débiteur de {debit_fmt} est constaté "
            "sur votre compte pour le lot n° {num_apt} ({type_apt})."
        ),
        "description": "Rappel factuel du solde débiteur et du lot concerné",
        "sort_order": 10,
    },
    {
        "title": "💳 Coordonnées bancaires & Virement",
        "content": (
            "Merci de bien vouloir régulariser cette somme par virement bancaire sur le compte de la copropriété :\n"
            "- Référence à indiquer : {code_proprietaire} - {nom_proprietaire}\n"
            "- Bénéficiaire : {sender_name}"
        ),
        "description": "Instructions de virement avec référence et bénéficiaire",
        "sort_order": 20,
    },
    {
        "title": "🤝 Invitation au dialogue / contestation",
        "content": (
            "Si votre règlement a été adressé récemment ou si vous constatez une anomalie sur votre relevé, "
            "nous vous prions de contacter le syndic sans délai à l'adresse {sender_email}."
        ),
        "description": "Formule cordiale en cas de paiement récent ou contestation",
        "sort_order": 30,
    },
    {
        "title": "✍️ Formule de politesse & Signature syndic",
        "content": (
            "Restant à votre entière disposition pour tout renseignement complémentaire,\n\n"
            "Cordialement,\n"
            "{sender_name}"
        ),
        "description": "Clôture standardisée et signature du syndic",
        "sort_order": 40,
    },
]


def init_relance_snippets_if_missing(db_path: str | None = None) -> None:
    """Initialise les paragraphes types par défaut si la table est vide."""
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM relance_snippet")
        row = cur.fetchone()
        if row and row["cnt"] > 0:
            return

    _logger.info("Initialisation des paragraphes types par défaut...")
    with get_db_connection() as cnx, cnx.cursor() as cur:
        for snip in DEFAULT_SNIPPETS:
            cur.execute(
                """
                INSERT IGNORE INTO relance_snippet (title, content, description, sort_order)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    snip["title"],
                    snip["content"],
                    snip.get("description", ""),
                    snip.get("sort_order", 0),
                ),
            )
        cnx.commit()
    _logger.success("Paragraphes types par défaut insérés.")


def list_relance_snippets(db_path: str | None = None) -> list[dict[str, Any]]:
    """Retourne tous les paragraphes types enregistrés, triés par sort_order puis titre."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT snippet_id, title, content, description, sort_order, created_at, updated_at
            FROM relance_snippet
            ORDER BY sort_order ASC, title ASC
            """
        )
        return list(cur.fetchall())


def get_relance_snippet(
    snippet_id_or_title: int | str,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """Récupère un paragraphe type par son identifiant numérique ou par son titre."""
    with get_db_cursor() as cur:
        if isinstance(snippet_id_or_title, int) or (
            isinstance(snippet_id_or_title, str) and snippet_id_or_title.isdigit()
        ):
            cur.execute(
                "SELECT * FROM relance_snippet WHERE snippet_id = %s",
                (int(snippet_id_or_title),),
            )
        else:
            cur.execute(
                "SELECT * FROM relance_snippet WHERE title = %s",
                (str(snippet_id_or_title).strip(),),
            )
        row = cur.fetchone()
        return dict(row) if row else None


def create_relance_snippet(
    title: str,
    content: str,
    description: str = "",
    sort_order: int = 0,
    db_path: str | None = None,
) -> int:
    """Crée un nouveau paragraphe type de relance.

    Raises:
        ValueError: Si le titre ou le contenu est vide, ou si le titre existe déjà.
    """
    clean_title = (title or "").strip()
    clean_content = (content or "").strip()
    if not clean_title:
        raise ValueError("Le titre du paragraphe type ne peut pas être vide.")
    if not clean_content:
        raise ValueError("Le contenu du paragraphe type ne peut pas être vide.")

    existing = get_relance_snippet(clean_title, db_path=db_path)
    if existing:
        raise ValueError(f"Un paragraphe type intitulé '{clean_title}' existe déjà.")

    with get_db_connection() as cnx, cnx.cursor() as cur:
        cur.execute(
            """
            INSERT INTO relance_snippet (title, content, description, sort_order)
            VALUES (%s, %s, %s, %s)
            """,
            (clean_title, clean_content, description.strip(), int(sort_order)),
        )
        snippet_id = cur.lastrowid
        cnx.commit()
        _logger.success(f"Paragraphe type '{clean_title}' créé (id={snippet_id}).")
        return int(snippet_id)


def update_relance_snippet(
    snippet_id: int,
    title: str | None = None,
    content: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
    db_path: str | None = None,
) -> bool:
    """Met à jour un paragraphe type existant."""
    existing = get_relance_snippet(snippet_id, db_path=db_path)
    if not existing:
        raise ValueError(f"Paragraphe type introuvable pour l'id {snippet_id}.")

    new_title = existing["title"] if title is None else title.strip()
    new_content = existing["content"] if content is None else content.strip()
    new_desc = existing["description"] if description is None else description.strip()
    new_order = existing["sort_order"] if sort_order is None else int(sort_order)

    if not new_title:
        raise ValueError("Le titre du paragraphe type ne peut pas être vide.")
    if not new_content:
        raise ValueError("Le contenu du paragraphe type ne peut pas être vide.")

    # Vérifier l'unicité du titre si modifié
    if new_title != existing["title"]:
        other = get_relance_snippet(new_title, db_path=db_path)
        if other and other["snippet_id"] != snippet_id:
            raise ValueError(f"Un paragraphe type intitulé '{new_title}' existe déjà.")

    with get_db_connection() as cnx, cnx.cursor() as cur:
        cur.execute(
            """
            UPDATE relance_snippet
            SET title = %s, content = %s, description = %s, sort_order = %s
            WHERE snippet_id = %s
            """,
            (new_title, new_content, new_desc, new_order, snippet_id),
        )
        cnx.commit()
        _logger.success(f"Paragraphe type id={snippet_id} mis à jour.")
        return True


def delete_relance_snippet(snippet_id: int, db_path: str | None = None) -> bool:
    """Supprime un paragraphe type par son identifiant."""
    with get_db_connection() as cnx, cnx.cursor() as cur:
        cur.execute(
            "DELETE FROM relance_snippet WHERE snippet_id = %s",
            (snippet_id,),
        )
        cnx.commit()
        _logger.success(f"Paragraphe type id={snippet_id} supprimé.")
        return True


def reset_default_relance_snippets(db_path: str | None = None) -> int:
    """Restaure les paragraphes types par défaut (insère ceux manquants)."""
    inserted = 0
    with get_db_connection() as cnx, cnx.cursor() as cur:
        for snip in DEFAULT_SNIPPETS:
            cur.execute(
                """
                INSERT IGNORE INTO relance_snippet (title, content, description, sort_order)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    snip["title"],
                    snip["content"],
                    snip.get("description", ""),
                    snip.get("sort_order", 0),
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
        cnx.commit()
    return inserted

