"""Fixtures partagees pour les tests CPTCOPRO MariaDB."""

from __future__ import annotations

import os

import pytest

from cptcopro.utils.paths import init_env

init_env()

# Forcer l'utilisation de la base de test dediee pour proteger la base applicative
os.environ["MARIADB_DATABASE"] = os.getenv("MARIADB_DATABASE_TEST", "cptcopro_test")

import cptcopro.Database.connection as db_conn  # noqa: E402

# S'assurer que le pool est cree sur la base de test
db_conn._pool = None

from cptcopro.Database.connection import get_db_connection  # noqa: E402
from cptcopro.Database.Creation_BDD import creer_base_db, verif_presence_db  # noqa: E402

CLEANUP_TABLES = [
    "relance_draft",
    "relance_template",
    "relance_destinataire",
    "relance_config",
    "suivi_alertes",
    "alertes_debit_eleve",
    "charge",
    "coproprietaires",
]


@pytest.fixture(autouse=True)
def clean_db(request):
    """Nettoie les tables de donnees avant chaque test BDD et s'assure du schema."""
    module_path = str(request.fspath).replace("\\", "/")
    # Les tests unitaires purs (traitement, utils, parsing, integrity) n'ont pas besoin de réinitialiser la BDD
    needs_db = any(k in module_path for k in ("/bdd/", "/security/"))
    if not needs_db:
        yield
        return

    # Création du schéma uniquement si la table 'charge' est absente
    if not verif_presence_db():
        creer_base_db()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for table in CLEANUP_TABLES:
                cur.execute(f"DELETE FROM `{table}`")
            cur.execute("DELETE FROM `config_alerte`")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    from cptcopro.Database.Alertes_Config import init_config_alerte_if_missing
    from cptcopro.Database.Relance_Config import init_relance_config_if_missing

    init_config_alerte_if_missing()
    init_relance_config_if_missing()
    yield


def load_fixture(name: str) -> str:
    """Charge le contenu texte d'une fixture HTML depuis tests/fixtures."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", name)
    with open(path, encoding="utf-8") as f:
        return f.read()
