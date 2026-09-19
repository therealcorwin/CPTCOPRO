"""Gestion des variables de personnalisation des relances (MariaDB).

Permet à l'utilisateur de définir, modifier et supprimer des variables personnalisées
(ex: {iban}, {telephone_syndic}, {horaires_syndic}, etc.) injectées dynamiquement
dans les modèles d'emails statiques et les prompts de l'assistant IA Mistral.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from .connection import get_db_connection, get_db_cursor

_logger = logger.bind(type_log="BDD")

# Variables système protégées (issues de la comptabilité et de la configuration globale)
SYSTEM_VARIABLE_NAMES: frozenset[str] = frozenset({
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
    "date_du_jour",
    "today",
    "contact_name",
    "type_alerte",
    "first_relance_date",
    "last_relance_date",
    "nb_relances_total",
    "jours_depuis_derniere_relance",
})


def normalize_variable_name(raw_name: str) -> str:
    """Nettoie et valide un nom de variable pour en faire un identifiant valide.

    Exemples :
        "{iban}" -> "iban"
        "IBAN FR" -> "iban_fr"
        "Téléphone Syndic" -> "telephone_syndic"
    """
    if not raw_name:
        raise ValueError("Le nom de la variable ne peut pas être vide.")

    # Retrait des accolades { } éventuelles
    cleaned = raw_name.strip().strip("{}").strip().lower()

    # Remplacement des espaces, tirets et séparateurs par des underscores
    cleaned = re.sub(r"[\s\-\.\/]+", "_", cleaned)

    # Suppression des accents et caractères non autorisés
    accents_map = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
    }
    for acc, rep in accents_map.items():
        cleaned = cleaned.replace(acc, rep)

    # Ne garder que lettres minuscules, chiffres et underscores
    cleaned = re.sub(r"[^a-z0-9_]", "", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")

    if not cleaned:
        raise ValueError(
            f"Nom de variable invalide après nettoyage : '{raw_name}'. "
            "Le nom doit contenir au moins une lettre ou un chiffre."
        )

    if cleaned[0].isdigit():
        cleaned = f"var_{cleaned}"

    if len(cleaned) > 64:
        cleaned = cleaned[:64]

    return cleaned


def list_relance_variables(db_path: str | None = None) -> list[dict[str, Any]]:
    """Retourne toutes les variables personnalisées définies en base."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT var_id, name, value, description, created_at, updated_at
            FROM relance_variable
            ORDER BY name ASC
            """
        )
        return list(cur.fetchall())


def get_relance_variable(
    var_id_or_name: int | str,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """Récupère une variable par son identifiant numérique ou par son nom."""
    with get_db_cursor() as cur:
        if isinstance(var_id_or_name, int) or (
            isinstance(var_id_or_name, str) and var_id_or_name.isdigit()
        ):
            cur.execute(
                "SELECT * FROM relance_variable WHERE var_id = %s",
                (int(var_id_or_name),),
            )
        else:
            norm_name = normalize_variable_name(str(var_id_or_name))
            cur.execute(
                "SELECT * FROM relance_variable WHERE name = %s",
                (norm_name,),
            )
        row = cur.fetchone()
        return dict(row) if row else None


def create_relance_variable(
    name: str,
    value: str,
    description: str = "",
    db_path: str | None = None,
) -> int:
    """Crée une nouvelle variable personnalisée et retourne son var_id."""
    norm_name = normalize_variable_name(name)

    if norm_name in SYSTEM_VARIABLE_NAMES:
        raise ValueError(
            f"Le nom '{norm_name}' est réservé par le système et ne peut pas être redéfini."
        )

    val = str(value or "").strip()
    if not val:
        raise ValueError("La valeur de la variable ne peut pas être vide.")

    desc = str(description or "").strip()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO relance_variable (name, value, description)
                    VALUES (%s, %s, %s)
                    """,
                    (norm_name, val, desc),
                )
                if cur.lastrowid is None:
                    raise RuntimeError("Échec de création de la variable (aucun identifiant retourné).")
                _logger.info(f"Variable personnalisée créée : {{{norm_name}}}")
                return int(cur.lastrowid)
    except Exception as exc:
        _logger.error(f"Erreur create_relance_variable pour '{norm_name}': {exc}")
        raise


def update_relance_variable(
    var_id: int,
    name: str | None = None,
    value: str | None = None,
    description: str | None = None,
    db_path: str | None = None,
) -> bool:
    """Met à jour une variable personnalisée existante."""
    existing = get_relance_variable(var_id)
    if not existing:
        raise ValueError(f"Variable introuvable pour var_id={var_id}")

    new_name = existing["name"]
    if name is not None:
        new_name = normalize_variable_name(name)
        if new_name in SYSTEM_VARIABLE_NAMES:
            raise ValueError(f"Le nom '{new_name}' est réservé par le système.")

    new_value = existing["value"] if value is None else str(value).strip()
    if not new_value:
        raise ValueError("La valeur de la variable ne peut pas être vide.")

    new_desc = existing["description"] if description is None else str(description).strip()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE relance_variable
                SET name = %s, value = %s, description = %s
                WHERE var_id = %s
                """,
                (new_name, new_value, new_desc, int(var_id)),
            )
            _logger.info(f"Variable personnalisée mise à jour : {{{new_name}}} (ID {var_id})")
            return cur.rowcount > 0


def delete_relance_variable(var_id: int, db_path: str | None = None) -> bool:
    """Supprime une variable personnalisée par son identifiant."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM relance_variable WHERE var_id = %s",
                (int(var_id),),
            )
            deleted = cur.rowcount > 0
            if deleted:
                _logger.info(f"Variable personnalisée supprimée (ID {var_id})")
            return deleted


def get_custom_variables_dict(db_path: str | None = None) -> dict[str, str]:
    """Retourne un dictionnaire {name: value} de toutes les variables personnalisées."""
    try:
        rows = list_relance_variables(db_path=db_path)
        return {str(row["name"]): str(row["value"]) for row in rows}
    except Exception as exc:
        _logger.debug(f"Erreur get_custom_variables_dict (fallback dictionnaire vide) : {exc}")
        return {}

