"""Constantes pour le module Parsing.

Ce fichier centralise les codes d'erreur retournés par les fonctions
de parsing. Tous les codes commencent par 'KO_' suivi d'une description.

Les appelants peuvent vérifier `result.startswith("KO_")` pour détecter
une erreur, ou comparer à une constante spécifique pour un traitement ciblé.
"""

# === Codes d'erreur de login_and_open_menu() ===
ERROR_GO_TO_URL = "KO_GO_TO_URL"
ERROR_FILL_LOGIN = "KO_FILL_LOGIN"
ERROR_FILL_PASSWORD = "KO_FILL_PASSWORD"
ERROR_CLICK_LOGIN = "KO_CLICK_LOGIN"
ERROR_WAIT_FOR_LOAD = "KO_WAIT_FOR_LOAD"
ERROR_CLICK_MENU = "KO_CLICK_MENU"

# === Codes d'erreur génériques ===
ERROR_OPEN_BROWSER = "KO_OPEN_BROWSER"

# === Codes d'erreur de recup_charges_coproprietaires() ===
ERROR_CLICK_SOLDE_COPRO = "KO_CLICK_SOLDE_COPRO"

# === Codes d'erreur de recup_lots_coproprietaires() ===
ERROR_CLICK_LISTE_COPRO = "KO_CLICK_LISTE_COPRO"
ERROR_CLICK_LISTE_COPRO_EXPANDED = "KO_CLICK_LISTE_COPRO_EXPANDED"

# === Codes d'erreur communs ===
ERROR_WAIT_FOR_FINAL_LOAD = "KO_WAIT_FOR_FINAL_LOAD"
ERROR_GET_HTML = "KO_GET_HTML"
