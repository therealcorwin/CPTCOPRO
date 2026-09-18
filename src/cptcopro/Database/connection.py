"""Module central de gestion des connexions MariaDB (PyMySQL + DBUtils.PooledDB).

Toute la couche Database utilise exclusivement ce module.
Ne jamais appeler pymysql.connect() directement ailleurs.

Usage:
    from cptcopro.Database.connection import get_db_connection, get_db_cursor

    # Transaction complete
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO ...")
        # commit automatique a la sortie, rollback sur exception

    # Curseur direct (lecture / ecriture simple)
    with get_db_cursor() as cur:
        cur.execute("SELECT ...")
        rows = cur.fetchall()
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import TypeVar

import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB
from loguru import logger
from pymysql.constants import FIELD_TYPE
from pymysql.converters import conversions

from cptcopro.utils.env_loader import get_mariadb_config

T = TypeVar("T")

_logger = logger.bind(type_log="BDD")

# Conversions de types : convertir DECIMAL MariaDB en float pour compatibilité pandas / numpy / plotly
_DB_CONVERSIONS = conversions.copy()
_DB_CONVERSIONS[FIELD_TYPE.DECIMAL] = float
_DB_CONVERSIONS[FIELD_TYPE.NEWDECIMAL] = float

# ---------------------------------------------------------------------------
# Pool singleton — initialise une seule fois au premier appel
# ---------------------------------------------------------------------------
_pool: PooledDB | None = None

# Nombre de tentatives sur deadlock (Error 1213) avant abandon
_DEADLOCK_MAX_RETRIES = 3
_DEADLOCK_BACKOFF_BASE = 0.1  # secondes — double a chaque tentative


def _get_pool() -> PooledDB:
    """Retourne le pool singleton, en le creant si necessaire."""
    global _pool
    if _pool is None:
        cfg = get_mariadb_config()
        _pool = PooledDB(
            creator=pymysql,
            # Taille du pool
            mincached=1,
            maxcached=5,
            maxconnections=10,
            # Parametres pymysql
            host=cfg["host"],
            port=int(cfg["port"]),
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            conv=_DB_CONVERSIONS,
            # Timeouts reseau
            connect_timeout=5,
            read_timeout=30,
            write_timeout=30,
            # Reconnexion transparente : teste la connexion avant chaque emprunt.
            # Indispensable car MariaDB ferme les connexions inactives apres
            # wait_timeout (souvent 8h par defaut, parfois 30 min en prod).
            # Sans ping=1 -> OperationalError: (2006, MySQL server has gone away).
            ping=1,
        )
        _logger.success(
            f"Pool MariaDB initialise ({cfg['host']}:{cfg['port']} / {cfg['database']})"
        )
    return _pool


def init_pool() -> PooledDB:
    """Initialise et retourne le pool. Appele par @st.cache_resource dans Streamlit."""
    return _get_pool()


def close_pool() -> None:
    """Ferme proprement toutes les connexions du pool PooledDB pour éviter les connexions avortées."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None


import atexit

atexit.register(close_pool)


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------


@contextmanager
def get_db_connection() -> Generator[pymysql.connections.Connection, None, None]:
    """Context manager fournissant une connexion du pool.

    - Commit automatique a la sortie propre.
    - Rollback + reraise sur toute exception.

    Usage:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO ...")
    """
    pool = _get_pool()
    conn = pool.connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_with_retry(
    func: Callable[[pymysql.connections.Connection], T],
    max_retries: int = _DEADLOCK_MAX_RETRIES,
    backoff_base: float = _DEADLOCK_BACKOFF_BASE,
) -> T:
    """Execute une fonction dans une transaction avec retry automatique sur deadlock (Error 1213).

    Usage:
        def my_txn(conn):
            with conn.cursor() as cur:
                cur.execute(...)
        execute_with_retry(my_txn)
    """
    attempt = 0
    while True:
        try:
            with get_db_connection() as conn:
                return func(conn)
        except pymysql.err.OperationalError as exc:
            err_code = exc.args[0] if exc.args else None
            if err_code == 1213 and attempt < max_retries - 1:
                wait = backoff_base * (2**attempt)
                _logger.warning(
                    f"Deadlock detecte (tentative {attempt + 1}/{max_retries}), "
                    f"retry dans {wait:.2f}s..."
                )
                time.sleep(wait)
                attempt += 1
                continue
            raise


@contextmanager
def get_db_cursor() -> Generator[pymysql.cursors.DictCursor, None, None]:
    """Context manager fournissant un DictCursor pret a l'emploi.

    Commit automatique a la sortie propre, rollback sur exception.
    Utilise pour les operations de lecture ou d'ecriture simples en une passe.

    Usage:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM charge WHERE date = %s", (date,))
            rows = cur.fetchall()
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            yield cur


# ---------------------------------------------------------------------------
# Test de connectivite au demarrage
# ---------------------------------------------------------------------------


def verif_connexion_db() -> None:
    """Teste la connexion MariaDB au demarrage via SELECT 1.

    Appele juste apres validate_startup_env() dans main.py, avant tout
    scraping Playwright. Si MariaDB est injoignable, l'application sort
    proprement avec un message clair plutot qu'une stack trace au milieu
    d'une operation metier.

    Raises:
        RuntimeError: Si la connexion est impossible.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1")
        _logger.success("Connexion MariaDB verifiee.")
    except Exception as exc:
        _logger.critical(f"Impossible de se connecter a MariaDB : {exc}")
        raise RuntimeError("Base de donnees MariaDB inaccessible") from exc
