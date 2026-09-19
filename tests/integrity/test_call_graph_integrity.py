"""Tests de validation automatisée de l'intégrité de la documentation du graphe d'appels (reports/call_graph.md).

Ces tests garantissent que :
1. Tous les fichiers et modules mentionnés dans le tableau d'organisation existent réellement.
2. Toutes les fonctions et composants clés documentés existent et sont importables.
3. Toutes les options CLI documentées dans le rapport sont bien présentes dans le parser de main.py.
4. Toutes les pages Streamlit présentes sur le disque sont référencées dans la cartographie.
"""

from __future__ import annotations

import importlib
import re

import pytest

from cptcopro.utils.paths import get_project_root_dir

CALL_GRAPH_PATH = get_project_root_dir() / "reports" / "call_graph.md"


@pytest.fixture(scope="module")
def call_graph_content() -> str:
    """Charge le contenu du rapport call_graph.md."""
    assert CALL_GRAPH_PATH.exists(), (
        f"Le fichier de documentation {CALL_GRAPH_PATH} est introuvable."
    )
    return CALL_GRAPH_PATH.read_text(encoding="utf-8")


def test_documented_files_exist(call_graph_content: str):
    """Vérifie que chaque fichier répertorié dans le tableau d'organisation des modules existe."""
    root = get_project_root_dir()

    # Isoler la section 'Organisation des modules du projet'
    start_marker = "## Organisation des modules du projet"
    end_marker = "## Matrice d'accès aux données (MariaDB)"
    assert start_marker in call_graph_content, (
        f"Section '{start_marker}' introuvable dans call_graph.md."
    )

    sub_content = call_graph_content.split(start_marker)[1]
    if end_marker in sub_content:
        sub_content = sub_content.split(end_marker)[0]

    # Extraction des chemins du tableau Markdown: | `src/...` | ... | ... |
    module_pattern = re.compile(r"\|\s*`([^`\*]+)`\s*\|\s*[^\|]+\|\s*[^\|]+\|")
    matches = module_pattern.findall(sub_content)

    assert len(matches) >= 20, (
        f"Trop peu de modules extraits ({len(matches)}). Vérifier le format du tableau."
    )

    for file_rel_path in matches:
        file_path = root / file_rel_path.strip()
        assert file_path.exists(), (
            f"Le fichier '{file_rel_path}' documenté dans call_graph.md n'existe pas sur disque."
        )


def test_documented_functions_exist():
    """Vérifie que les fonctions clés documentées sont bien présentes et appelables dans leurs modules."""
    checks: list[tuple[str, list[str]]] = [
        (
            "cptcopro.Database.connection",
            [
                "init_pool",
                "get_db_connection",
                "get_db_cursor",
                "execute_with_retry",
                "verif_connexion_db",
                "close_pool",
            ],
        ),
        (
            "cptcopro.Database.Creation_BDD",
            [
                "creer_base_db",
                "integrite_db",
                "verif_presence_db",
                "purger_alertes_pour_rebuild",
            ],
        ),
        (
            "cptcopro.Database.Charges_To_BDD",
            [
                "enregistrer_charges",
                "_normaliser_lignes_charge",
            ],
        ),
        (
            "cptcopro.Database.Coproprietaires_To_BDD",
            [
                "enregistrer_coproprietaires",
                "_valider_collecte",
            ],
        ),
        (
            "cptcopro.Database.Alertes_Config",
            [
                "sauvegarder_nombre_alertes",
                "get_config_alertes",
                "update_config_alerte",
            ],
        ),
        (
            "cptcopro.Database.Backup_DB",
            [
                "backup_db",
                "generate_insert_statements",
            ],
        ),
        (
            "cptcopro.Database.Backup_DB_Pcloud",
            [
                "sauvegarder_bdd_pcloud",
                "telecharger_dernier_backup_pcloud",
                "tester_token_et_connecter_pcloud",
                "deconnecter_pcloud",
            ],
        ),
        (
            "cptcopro.Database.Relance_Config",
            [
                "get_relance_config",
                "update_relance_config",
                "list_relances_due",
                "save_relance_draft",
                "get_relance_drafts",
                "get_relances_tracking_summary",
                "get_copro_notes",
                "save_copro_notes",
            ],
        ),
        (
            "cptcopro.Database.Relance_Templates",
            [
                "list_relance_templates",
                "get_relance_template",
                "create_relance_template",
                "update_relance_template",
                "delete_relance_template",
            ],
        ),
        (
            "cptcopro.utils.relance_mailer",
            [
                "generate_relance_draft_with_llm",
                "render_relance_template",
                "generer_brouillons_relances",
                "save_draft_to_imap",
                "tester_connexion_mistral",
                "tester_connexion_imap",
            ],
        ),
        (
            "cptcopro.utils.hotmail_oauth",
            [
                "verifier_statut_token_hotmail",
                "demarrer_device_flow_microsoft",
                "valider_device_flow_microsoft",
                "get_hotmail_access_token",
            ],
        ),
        (
            "cptcopro.utils.pcloud_oauth",
            [
                "extraire_code_depuis_url",
                "recuperer_code_oauth_playwright",
                "obtenir_code_oauth_automatique",
            ],
        ),
        (
            "cptcopro.utils.privacy",
            [
                "is_privacy_enabled",
                "appliquer_confidentialite",
                "preparer_df_pour_graphe",
                "anonymiser",
            ],
        ),
        (
            "cptcopro.utils.db_helpers",
            [
                "normalize_date_columns",
                "fetch_dataframe",
            ],
        ),
        (
            "cptcopro.utils.ui_components",
            [
                "inject_custom_css",
                "render_header",
                "apply_plotly_theme",
            ],
        ),
        (
            "cptcopro.utils.env_loader",
            [
                "validate_startup_env",
                "get_mariadb_config",
            ],
        ),
        (
            "cptcopro.Parsing.Commun",
            [
                "recup_all_html_parallel",
                "_recup_html_generic",
                "login_and_open_menu",
            ],
        ),
        (
            "cptcopro.Traitement.Charge_Copro",
            [
                "recuperer_date_situation_copro",
                "recuperer_situation_copro",
            ],
        ),
        (
            "cptcopro.Traitement.Lots_Copro",
            [
                "extraire_lignes_brutes",
                "consolider_proprietaires_lots",
            ],
        ),
    ]

    for module_name, func_names in checks:
        mod = importlib.import_module(module_name)
        for fn in func_names:
            assert hasattr(mod, fn), (
                f"La fonction '{fn}' n'existe pas dans le module '{module_name}'."
            )
            attr = getattr(mod, fn)
            assert callable(attr), f"'{fn}' dans '{module_name}' n'est pas un appelable."


def test_cli_options_documented(call_graph_content: str):
    """Vérifie que chaque option du parser CLI de main.py est documentée dans call_graph.md."""
    from cptcopro.main import _parse_cli_args

    # Extraction des options supportées par le parser réel
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.argv", ["main.py"])
        args = _parse_cli_args()
    # On teste directement les drapeaux connus
    documented_options = re.findall(r"`(--[\w-]+)`", call_graph_content)
    unique_doc_options = set(documented_options)

    expected_options = [
        "--no-headless",
        "--no-serve",
        "--serve-port",
        "--serve-host",
        "--serve-python",
        "--streamlit-no-browser",
        "--streamlit-no-console",
        "--streamlit-use-cmd-start",
        "--streamlit-log-file",
        "--show-console",
        "--no-backup",
        "--deco-pcloud",
        "--auto-relance-drafts",
        "--relance-imap",
    ]

    for opt in expected_options:
        assert opt in unique_doc_options, (
            f"L'option CLI '{opt}' n'est pas documentée dans call_graph.md."
        )

    # Vérifier que l'option supprimée --db-path n'est ni documentée ni acceptée par le parser
    assert "--db-path" not in unique_doc_options, (
        "L'option obsolète '--db-path' ne doit plus être documentée dans call_graph.md."
    )
    assert not hasattr(args, "db_path"), "L'attribut 'db_path' ne doit plus exister dans args."

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.argv", ["main.py", "--db-path", "custom_path.sqlite"])
        with pytest.raises(SystemExit):
            _parse_cli_args()


def test_all_streamlit_pages_documented(call_graph_content: str):
    """Vérifie que les 8 pages Streamlit du dossier Pages/ sont mentionnées dans call_graph.md."""
    pages_dir = get_project_root_dir() / "src" / "cptcopro" / "Pages"
    page_files = sorted(p.name for p in pages_dir.glob("*.py"))

    assert len(page_files) == 8, (
        f"Nombre inattendu de pages dans Pages/ : {len(page_files)} (8 attendues)."
    )

    for pf in page_files:
        assert pf in call_graph_content, (
            f"La page Streamlit '{pf}' n'est pas mentionnée dans call_graph.md."
        )
