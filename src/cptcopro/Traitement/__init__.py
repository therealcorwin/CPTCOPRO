"""Package de traitement et parsing HTML des données copropriété.

Ce package regroupe les modules de traitement du HTML récupéré :
- Charge_Copro : Parsing des charges des copropriétaires
- Lots_Copro : Parsing des lots et consolidation propriétaires-lots
"""
from .Charge_Copro import (
    normalise_somme,
    recuperer_date_situation_copro,
    recuperer_situation_copro,
    afficher_etat_coproprietaire,
)
from .Lots_Copro import (
    extraire_lignes_brutes,
    consolider_proprietaires_lots,
    afficher_avec_rich,
    detecter_proprietaire,
    est_ligne_lot,
    extraire_info_lot,
    est_scic,
    normaliser_prefixes_proprietaire,
)

__all__ = [
    # Charge_Copro
    "normalise_somme",
    "recuperer_date_situation_copro",
    "recuperer_situation_copro",
    "afficher_etat_coproprietaire",
    # Lots_Copro
    "extraire_lignes_brutes",
    "consolider_proprietaires_lots",
    "afficher_avec_rich",
    "detecter_proprietaire",
    "est_ligne_lot",
    "extraire_info_lot",
    "est_scic",
    "normaliser_prefixes_proprietaire",
]
