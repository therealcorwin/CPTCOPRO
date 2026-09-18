"""Package de traitement et parsing HTML des données copropriété.

Ce package regroupe les modules de traitement du HTML récupéré :
- Charge_Copro : Parsing des charges des copropriétaires
- Lots_Copro : Parsing des lots et consolidation propriétaires-lots
"""

from .Charge_Copro import (
    afficher_etat_coproprietaire,
    normalise_somme,
    recuperer_date_situation_copro,
    recuperer_situation_copro,
)
from .Lots_Copro import (
    afficher_avec_rich,
    consolider_proprietaires_lots,
    detecter_proprietaire,
    est_ligne_lot,
    est_scic,
    extraire_info_lot,
    extraire_lignes_brutes,
    normaliser_prefixes_proprietaire,
)

__all__ = [
    "afficher_avec_rich",
    "afficher_etat_coproprietaire",
    "consolider_proprietaires_lots",
    "detecter_proprietaire",
    "est_ligne_lot",
    "est_scic",
    "extraire_info_lot",
    "extraire_lignes_brutes",
    "normalise_somme",
    "normaliser_prefixes_proprietaire",
    "recuperer_date_situation_copro",
    "recuperer_situation_copro",
]
