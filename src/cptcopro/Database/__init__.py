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
from .Creation_BDD import verif_presence_db, integrite_db
from .Charges_To_BDD import enregistrer_donnees_sqlite
from .Coproprietaires_To_BDD import enregistrer_coproprietaires
from .Alertes_Config import (
    sauvegarder_nombre_alertes,
    get_config_alertes,
    update_config_alerte,
    get_threshold_for_type,
    init_config_alerte_if_missing,
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
    "integrite_db",
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
    # Backup_DB
    "backup_db",
]
