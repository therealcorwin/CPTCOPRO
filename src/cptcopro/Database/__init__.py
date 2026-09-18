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
    get_relance_config,
    get_relance_destinataires,
    get_relance_drafts,
    get_relances_tracking_summary,
    init_relance_config_if_missing,
    list_relances_due,
    mark_relance_draft_status,
    save_relance_draft,
    update_relance_config,
    upsert_relance_destinataire,
)
from .Relance_Templates import (
    DEFAULT_TEMPLATE_NAME,
    GENERATION_MODES,
    TEMPLATE_PLACEHOLDERS,
    create_relance_template,
    delete_relance_template,
    get_relance_template,
    init_relance_templates_if_missing,
    list_relance_templates,
    update_relance_template,
)

# Alias de compatibilité ascendante pendant la migration
enregistrer_donnees_sqlite = enregistrer_charges

__all__ = [
    "CollecteChargesVideError",
    "CollecteCoproprietairesInvalideError",
    "DEFAULT_ALERT_THRESHOLDS",
    "DEFAULT_RELANCE_CONFIG",
    "DEFAULT_TEMPLATE_NAME",
    "DEFAULT_THRESHOLD_FALLBACK",
    "GENERATION_MODES",
    "IncoherenceLotsError",
    "NOMBRE_LOTS_ATTENDU",
    "TEMPLATE_PLACEHOLDERS",
    "backup_db",
    "create_relance_template",
    "creer_base_db",
    "delete_relance_template",
    "enregistrer_charges",
    "enregistrer_coproprietaires",
    "enregistrer_donnees_sqlite",
    "valider_charges_presentes",
    "valider_nombre_lots",
    "get_config_alertes",
    "get_db_connection",
    "get_db_cursor",
    "get_relance_config",
    "get_relance_destinataires",
    "get_relance_drafts",
    "get_relance_template",
    "get_relances_tracking_summary",
    "get_threshold_for_type",
    "init_config_alerte_if_missing",
    "init_relance_config_if_missing",
    "init_relance_templates_if_missing",
    "integrite_db",
    "list_relance_templates",
    "list_relances_due",
    "mark_relance_draft_status",
    "purger_alertes_pour_rebuild",
    "sauvegarder_nombre_alertes",
    "save_relance_draft",
    "update_config_alerte",
    "update_relance_config",
    "update_relance_template",
    "upsert_relance_destinataire",
    "verif_connexion_db",
    "verif_presence_db",
]
