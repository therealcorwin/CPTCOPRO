"""Package de parsing HTML avec Playwright.

Ce package regroupe les modules de récupération du HTML depuis l'extranet du syndic :
- Commun : Orchestration parallèle et authentification
- Charge_Copro : Navigation spécifique pour les charges
- Lots_Copro : Navigation spécifique pour les lots
"""

from .Charge_Copro import recup_charges_coproprietaires
from .Commun import (
    login_and_open_menu,
    recup_all_html_parallel,
    recup_html_charges,
    recup_html_lots,
)
from .Lots_Copro import recup_lots_coproprietaires

__all__ = [
    "login_and_open_menu",
    "recup_all_html_parallel",
    "recup_charges_coproprietaires",
    "recup_html_charges",
    "recup_html_lots",
    "recup_lots_coproprietaires",
]
