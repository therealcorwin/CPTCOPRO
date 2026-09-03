"""Package Database - Gestion de la base de données SQLite.

Ce package contient les modules pour :
- Vérification des prérequis (Verif_Prerequis_BDD)
- Création et intégrité de la base (Creation_BDD)
- Insertion des charges (Charges_To_BDD)
- Insertion des copropriétaires (Coproprietaires_To_BDD)
- Configuration des alertes (Alertes_Config)
- Sauvegarde de la base (Backup_DB)
"""

from .Alertes_Config import (
    get_config_alertes,
    get_threshold_for_type,
    init_config_alerte_if_missing,
    sauvegarder_nombre_alertes,
    update_config_alerte,
)
from .Backup_DB import backup_db
from .Charges_To_BDD import enregistrer_donnees_sqlite
from .constants import DEFAULT_ALERT_THRESHOLDS, DEFAULT_THRESHOLD_FALLBACK
from .Coproprietaires_To_BDD import enregistrer_coproprietaires
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
from .Verif_Prerequis_BDD import verif_repertoire_db

__all__ = [
    "DEFAULT_ALERT_THRESHOLDS",
    "DEFAULT_RELANCE_CONFIG",
    "DEFAULT_TEMPLATE_NAME",
    "DEFAULT_THRESHOLD_FALLBACK",
    "GENERATION_MODES",
    "TEMPLATE_PLACEHOLDERS",
    "backup_db",
    "create_relance_template",
    "creer_base_db",
    "delete_relance_template",
    "enregistrer_coproprietaires",
    "enregistrer_donnees_sqlite",
    "get_config_alertes",
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
    "verif_presence_db",
    "verif_repertoire_db",
]
