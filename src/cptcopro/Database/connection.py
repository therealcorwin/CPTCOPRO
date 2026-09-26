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
from typing import Any, TypeVar

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


class DatabaseConnectionError(RuntimeError):
    """Exception levée lorsque la base de données MariaDB est inaccessible."""


def _diagnose_db_error(exc: Exception, cfg: dict[str, Any]) -> str:
    """Analyse l'exception reçue et produit un message clair et actionnable."""
    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", "3306")
    database = cfg.get("database", "")
    user = cfg.get("user", "")

    err_code = None
    if isinstance(exc, pymysql.err.MySQLError) and exc.args:
        err_code = exc.args[0]
    elif hasattr(exc, "__cause__") and isinstance(exc.__cause__, pymysql.err.MySQLError) and exc.__cause__.args:
        err_code = exc.__cause__.args[0]

    err_str = str(exc)

    if err_code == 2003 or "10061" in err_str or "connection refused" in err_str.lower():
        return (
            f"Le serveur MariaDB est injoignable sur {host}:{port} "
            "(connexion refusée : service arrêté ou hôte/port inaccessible)."
        )
    if err_code == 1045 or "access denied" in err_str.lower():
        return (
            f"Authentification refusée pour l'utilisateur '{user}' sur {host}:{port}. "
            "Vérifiez l'utilisateur et le mot de passe dans le fichier .env."
        )
    if err_code == 1049 or "unknown database" in err_str.lower():
        return (
            f"La base de données '{database}' n'existe pas sur le serveur MariaDB ({host}:{port})."
        )
    if "timed out" in err_str.lower() or "timeout" in err_str.lower():
        return (
            f"Délai d'attente dépassé lors de la connexion au serveur MariaDB ({host}:{port})."
        )

    return f"Échec de connexion au serveur MariaDB ({host}:{port}/{database}) : {exc}"


def _get_pool() -> PooledDB:
    """Retourne le pool singleton, en le creant si necessaire."""
    global _pool
    if _pool is None:
        cfg = get_mariadb_config()
        try:
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
        except Exception as exc:
            _pool = None
            diag = _diagnose_db_error(exc, cfg)
            _logger.critical(f"ÉCHEC CRITIQUE DE CONNEXION BDD : {diag}")
            _logger.critical(
                "Action requise : vérifiez que le service MariaDB est démarré et que la configuration dans .env est correcte."
            )
            raise DatabaseConnectionError(
                f"Base de donnees MariaDB inaccessible : {diag}"
            ) from exc
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

    Appele au demarrage avant tout scraping Playwright ou traitement metier.
    Si MariaDB est injoignable, logue un message critique clair avec le diagnostic
    et leve une DatabaseConnectionError explicite.

    Raises:
        DatabaseConnectionError: Si la connexion est impossible.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1")
        _logger.success("Connexion MariaDB verifiee.")
    except DatabaseConnectionError:
        # Deja capturee et loguee au niveau CRITICAL avec diagnostic detaille
        raise
    except Exception as exc:
        cfg = get_mariadb_config()
        diag = _diagnose_db_error(exc, cfg)
        _logger.critical(f"ÉCHEC CRITIQUE DE CONNEXION BDD : {diag}")
        _logger.critical(
            "Action requise : vérifiez que le service MariaDB est démarré et que la configuration dans .env est correcte."
        )
        raise DatabaseConnectionError(
            f"Base de donnees MariaDB inaccessible : {diag}"
        ) from exc
