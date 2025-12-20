"""Constantes partagées pour les modules de base de données.

Ce module contient les constantes utilisées par les différents modules
de gestion de la base de données.
"""

# Seuils d'alerte par défaut par type d'appartement
# Ces valeurs sont utilisées pour initialiser la table config_alerte
DEFAULT_ALERT_THRESHOLDS = {
    "2p": {"charge_moyenne": 1500.0, "taux": 1.33, "threshold": 2000.0},
    "3p": {"charge_moyenne": 1800.0, "taux": 1.33, "threshold": 2400.0},
    "4p": {"charge_moyenne": 2100.0, "taux": 1.33, "threshold": 2800.0},
    "5p": {"charge_moyenne": 2400.0, "taux": 1.33, "threshold": 3200.0},
}

# Seuil par défaut pour les types non configurés (NA, inconnu, etc.)
DEFAULT_THRESHOLD_FALLBACK = 2000.0
