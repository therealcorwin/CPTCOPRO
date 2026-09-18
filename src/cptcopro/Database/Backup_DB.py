"""Module de sauvegarde de la base de donnees MariaDB (Dump logique Python pur).

Genere un dump SQL compresse au format .sql.gz sans dependance a mariadb-dump.
"""

from __future__ import annotations

import contextlib
import gzip
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger

from cptcopro.Database.connection import get_db_connection
from cptcopro.utils.paths import get_backup_dir

_logger = logger.bind(type_log="BACKUP")

BACKUP_TABLE_ORDER = [
    "config_alerte",
    "coproprietaires",
    "charge",
    "alertes_debit_eleve",
    "suivi_alertes",
    "relance_config",
    "relance_destinataire",
    "relance_template",
    "relance_draft",
]


def _format_sql_value(val: object) -> str:
    """Echappe et formate une valeur Python pour inclusion dans une requete SQL."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float, Decimal)):
        return str(val)
    if isinstance(val, (datetime, date)):
        return f"'{val.isoformat()}'"
    if isinstance(val, (bytes, bytearray)):
        return f"X'{val.hex()}'"

    # Echappement chaînes (guillemets simples et antislashs)
    text = str(val).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def generate_insert_statements(table: str, rows: list[dict[str, Any]]) -> str:
    """Genere les instructions SQL INSERT pour une liste de lignes."""
    if not rows:
        return f"-- Table {table}: 0 lignes\n\n"

    columns = list(rows[0].keys())
    cols_str = ", ".join(f"`{c}`" for c in columns)

    lines = [f"-- Dump de la table {table} ({len(rows)} lignes)"]
    batch_size = 200
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        value_tuples = []
        for r in batch:
            formatted_vals = [_format_sql_value(r.get(c)) for c in columns]
            value_tuples.append(f"({', '.join(formatted_vals)})")
        lines.append(
            f"INSERT INTO `{table}` ({cols_str}) VALUES\n"  # nosec B608
            + ",\n".join(value_tuples)
            + " ON DUPLICATE KEY UPDATE "
            + ", ".join(f"`{c}` = VALUES(`{c}`)" for c in columns)
            + ";"
        )
    lines.append("\n")
    return "\n".join(lines)


def backup_db(db_path: str | None = None) -> str | None:
    """Sauvegarde la base MariaDB sous forme de dump SQL compresse .sql.gz."""
    now: datetime = datetime.now()
    backup_dir: Path = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_filename = f"backup_cptcopro-{now.strftime('%d-%m-%Y-%H-%M-%S')}.sql.gz"
    backup_path = backup_dir / backup_filename

    _logger.info("Demarrage du dump logique MariaDB -> '{}'.", backup_filename)

    try:
        with gzip.open(backup_path, "wt", encoding="utf-8") as gz:
            gz.write("-- CPTCOPRO MariaDB Logical Backup\n")
            gz.write(f"-- Date: {now.isoformat()}\n")
            gz.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    for table in BACKUP_TABLE_ORDER:
                        try:
                            cur.execute(f"SELECT * FROM `{table}`")  # nosec B608  # noqa: S608
                            rows = list(cur.fetchall())
                            gz.write(generate_insert_statements(table, rows))
                            _logger.info("Table '{}' exportee: {} ligne(s).", table, len(rows))
                        except Exception as exc_tbl:
                            _logger.warning("Impossible d exporter '{}': {}", table, exc_tbl)

            gz.write("SET FOREIGN_KEY_CHECKS = 1;\n")

        size_kb = backup_path.stat().st_size / 1024
        _logger.success("Sauvegarde MariaDB terminee avec succes ({} Ko).", f"{size_kb:.1f}")
        return str(backup_path)
    except Exception as exc:
        _logger.error("Erreur lors de la sauvegarde MariaDB: {}", exc)
        if backup_path.exists():
            with contextlib.suppress(Exception):
                backup_path.unlink()
        return None
