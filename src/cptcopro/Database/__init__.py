"""Package Database - Gestion de la base de données MariaDB.

Ce package contient les modules pour :
- Gestion des connexions (connection)
- Création et intégrité de la base (Creation_BDD)
- Insertion des charges (Charges_To_BDD)
- Insertion des copropriétaires (Coproprietaires_To_BDD)
- Configuration des alertes (Alertes_Config)
- Sauvegarde de la base (Backup_DB)
- Gestion des relances (Relance_Config, Relance_Templates)
"""

from .Alertes_Config import (
    get_config_alertes,
    get_threshold_for_type,
    init_config_alerte_if_missing,
    sauvegarder_nombre_alertes,
    update_config_alerte,
)
from .Backup_DB import backup_db
from .Charges_To_BDD import (
    CollecteChargesVideError,
    enregistrer_charges,
    valider_charges_presentes,
)
from .connection import get_db_connection, get_db_cursor, verif_connexion_db
from .constants import (
    DEFAULT_ALERT_THRESHOLDS,
    DEFAULT_THRESHOLD_FALLBACK,
    NOMBRE_LOTS_ATTENDU,
)
from .Coproprietaires_To_BDD import (
    CollecteCoproprietairesInvalideError,
    IncoherenceLotsError,
    enregistrer_coproprietaires,
    valider_nombre_lots,
)
from .Creation_BDD import (
    creer_base_db,
    integrite_db,
    purger_alertes_pour_rebuild,
    verif_presence_db,
)
from .Relance_Config import (
    DEFAULT_RELANCE_CONFIG,
    get_copro_notes,
    get_relance_config,
    get_relance_destinataires,
    get_relance_drafts,
    get_relances_tracking_summary,
    init_relance_config_if_missing,
    list_relances_due,
    mark_relance_draft_status,
    save_copro_notes,
    save_relance_draft,
    update_relance_config,
    upsert_relance_destinataire,
)
from .Relance_Snippets import (
    DEFAULT_SNIPPETS,
    create_relance_snippet,
    delete_relance_snippet,
    get_relance_snippet,
    init_relance_snippets_if_missing,
    list_relance_snippets,
    reset_default_relance_snippets,
    update_relance_snippet,
)
from .Relance_Templates import (
    DEFAULT_TEMPLATE_NAME,
    GENERATION_MODES,
    TEMPLATE_PLACEHOLDERS,
    create_relance_template,
    delete_relance_template,
    get_all_template_placeholders,
    get_relance_template,
    init_relance_templates_if_missing,
    list_relance_templates,
    update_relance_template,
)
from .Relance_Variables import (
    create_relance_variable,
    delete_relance_variable,
    get_custom_variables_dict,
    get_relance_variable,
    list_relance_variables,
    normalize_variable_name,
    update_relance_variable,
)

# Alias de compatibilité ascendante pendant la migration
enregistrer_donnees_sqlite = enregistrer_charges

__all__ = [
    "DEFAULT_ALERT_THRESHOLDS",
    "DEFAULT_RELANCE_CONFIG",
    "DEFAULT_SNIPPETS",
    "DEFAULT_TEMPLATE_NAME",
    "DEFAULT_THRESHOLD_FALLBACK",
    "GENERATION_MODES",
    "NOMBRE_LOTS_ATTENDU",
    "TEMPLATE_PLACEHOLDERS",
    "CollecteChargesVideError",
    "CollecteCoproprietairesInvalideError",
    "IncoherenceLotsError",
    "backup_db",
    "create_relance_snippet",
    "create_relance_template",
    "create_relance_variable",
    "creer_base_db",
    "delete_relance_snippet",
    "delete_relance_template",
    "delete_relance_variable",
    "enregistrer_charges",
    "enregistrer_coproprietaires",
    "enregistrer_donnees_sqlite",
    "get_all_template_placeholders",
    "get_config_alertes",
    "get_copro_notes",
    "get_custom_variables_dict",
    "get_db_connection",
    "get_db_cursor",
    "get_relance_config",
    "get_relance_destinataires",
    "get_relance_drafts",
    "get_relance_snippet",
    "get_relance_template",
    "get_relance_variable",
    "get_relances_tracking_summary",
    "get_threshold_for_type",
    "init_config_alerte_if_missing",
    "init_relance_config_if_missing",
    "init_relance_snippets_if_missing",
    "init_relance_templates_if_missing",
    "integrite_db",
    "list_relance_snippets",
    "list_relance_templates",
    "list_relance_variables",
    "list_relances_due",
    "mark_relance_draft_status",
    "normalize_variable_name",
    "purger_alertes_pour_rebuild",
    "reset_default_relance_snippets",
    "sauvegarder_nombre_alertes",
    "save_copro_notes",
    "save_relance_draft",
    "update_config_alerte",
    "update_relance_config",
    "update_relance_snippet",
    "update_relance_template",
    "update_relance_variable",
    "upsert_relance_destinataire",
    "valider_charges_presentes",
    "valider_nombre_lots",
    "verif_connexion_db",
    "verif_presence_db",
]
