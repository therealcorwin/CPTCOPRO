"""Package Database - Gestion de la base de données SQLite.

Ce package contient les modules pour :
- Vérification des prérequis (Verif_Prerequis_BDD)
- Création et intégrité de la base (Creation_BDD)
- Insertion des charges (Charges_To_BDD)
- Insertion des copropriétaires (Coproprietaires_To_BDD)
- Configuration des alertes (Alertes_Config)
- Sauvegarde de la base (Backup_DB)
- Dédoublonnage des données (Dedoublonnage)
"""

from .constants import DEFAULT_ALERT_THRESHOLDS, DEFAULT_THRESHOLD_FALLBACK
from .Verif_Prerequis_BDD import verif_repertoire_db
from .Creation_BDD import verif_presence_db, creer_base_db, integrite_db, purger_alertes_pour_rebuild
from .Charges_To_BDD import enregistrer_donnees_sqlite
from .Coproprietaires_To_BDD import enregistrer_coproprietaires
from .Alertes_Config import (
    sauvegarder_nombre_alertes,
    get_config_alertes,
    update_config_alerte,
    get_threshold_for_type,
    init_config_alerte_if_missing,
)
from .Relance_Config import (
    DEFAULT_RELANCE_CONFIG,
    get_relance_config,
    update_relance_config,
    init_relance_config_if_missing,
    upsert_relance_destinataire,
    get_relance_destinataires,
    list_relances_due,
    save_relance_draft,
    get_relance_drafts,
    mark_relance_draft_status,
)
from .Relance_Templates import (
    DEFAULT_TEMPLATE_NAME,
    TEMPLATE_PLACEHOLDERS,
    GENERATION_MODES,
    init_relance_templates_if_missing,
    list_relance_templates,
    get_relance_template,
    create_relance_template,
    update_relance_template,
    delete_relance_template,
)
from .Backup_DB import backup_db

__all__ = [
    # Constants
    "DEFAULT_ALERT_THRESHOLDS",
    "DEFAULT_THRESHOLD_FALLBACK",
    # Verif_Prerequis_BDD
    "verif_repertoire_db",
    # Creation_BDD
    "verif_presence_db",
    "creer_base_db",
    "integrite_db",
    "purger_alertes_pour_rebuild",
    # Charges_To_BDD
    "enregistrer_donnees_sqlite",
    # Coproprietaires_To_BDD
    "enregistrer_coproprietaires",
    # Alertes_Config
    "sauvegarder_nombre_alertes",
    "get_config_alertes",
    "update_config_alerte",
    "get_threshold_for_type",
    "init_config_alerte_if_missing",
    # Relance_Config
    "DEFAULT_RELANCE_CONFIG",
    "get_relance_config",
    "update_relance_config",
    "init_relance_config_if_missing",
    "upsert_relance_destinataire",
    "get_relance_destinataires",
    "list_relances_due",
    "save_relance_draft",
    "get_relance_drafts",
    "mark_relance_draft_status",
    # Relance_Templates
    "DEFAULT_TEMPLATE_NAME",
    "TEMPLATE_PLACEHOLDERS",
    "GENERATION_MODES",
    "init_relance_templates_if_missing",
    "list_relance_templates",
    "get_relance_template",
    "create_relance_template",
    "update_relance_template",
    "delete_relance_template",
    # Backup_DB
    "backup_db",
]
