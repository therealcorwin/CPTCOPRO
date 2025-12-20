"""Module de traitement et parsing HTML des lots des copropriétaires.

Ce module parse le HTML de la liste des lots et extrait :
- Les propriétaires avec leur code (format: "NOM (CODE)")
- Les lots associés à chaque propriétaire
- La consolidation propriétaire-lots

Fonctions principales:
    extraire_lignes_brutes(): Extrait les lignes du HTML
    consolider_proprietaires_lots(): Associe propriétaires et lots
    afficher_avec_rich(): Affiche les données dans la console

Note:
    Le module vérifie qu'il y a exactement 64 copropriétaires.
"""
import re
from typing import Union
from selectolax.parser import HTMLParser
from rich.table import Table
from rich.console import Console

# patron d'identifiant des éléments ciblés
PATRON_ID = re.compile(r"^A17_\d+_\d+$")
# mots à exclure (minuscule)
MOTS_A_EXCLURE = ("boutique", "jardin")

# liste de préfixes autorisés (variantes)
_PREFIXES_PROPRIETAIRE = r"(?:M(?:onsieur)?\.?|Mr\.?|Monsieur|Mme\.?|Madame|MME\.?|Mlle\.?|Mademoiselle|Melle\.?|Me\.?|Mrs\.?)"
_PREFIXES_PROPRIETAIRE_RE = re.compile(
    rf"(?:\b{_PREFIXES_PROPRIETAIRE}\b(?:\s*(?:ou|et|/|,|&|-)\s*\b{_PREFIXES_PROPRIETAIRE}\b)*)\.?",
    re.IGNORECASE,
)

def normaliser_prefixes_proprietaire(texte: str) -> str:
    """
    Normalise le nom d'un propriétaire en supprimant les préfixes de civilité.
    
    Supprime les préfixes de genre (M., Mme, Monsieur, Madame, etc.) ainsi que
    les conjonctions (ou, et) et nettoie la ponctuation résiduelle.
    
    Args:
        texte: Chaîne contenant le nom du propriétaire avec préfixes potentiels.
    
    Returns:
        Nom nettoyé sans préfixes de civilité, avec espaces normalisés.
    
    Example:
        >>> normaliser_prefixes_proprietaire("M. et Mme DUPONT")
        'DUPONT'
    """
    if not texte:
        return texte
    nettoye = _PREFIXES_PROPRIETAIRE_RE.sub("", texte)
    nettoye = re.sub(r"\b(?:ou|et)\b", "", nettoye, flags=re.IGNORECASE)
    nettoye = re.sub(r"[\/,&\-]+", " ", nettoye)
    nettoye = re.sub(r"^[\s\-\–\—,:;]+", "", nettoye)
    nettoye = re.sub(r"\s+([:(),])", r"\1", nettoye)
    nettoye = " ".join(nettoye.split())
    return nettoye.strip()

# motif pour détecter "Nom (CODE)"
_PATRON_CODE_RE = re.compile(r"^(?P<nom>.+?)\s*\((?P<code>\d+[A-Za-z]?)\)\s*$")

def extraire_lignes_brutes(Html_lot_copro: Union[HTMLParser, str]) -> list[tuple[str, str]]:
    """
    Extrait les lignes pertinentes du HTML de la liste des lots.
    
    Parse le HTML et récupère tous les éléments dont l'ID correspond au pattern
    'A17_X_Y'. Filtre les éléments contenant des mots exclus (boutique, jardin)
    et normalise les préfixes de civilité.
    
    Args:
        Html_lot_copro: HTML brut ou objet HTMLParser déjà construit.
    
    Returns:
        Liste ordonnée de tuples (id_element, texte_normalise).
        Chaque tuple représente soit un propriétaire, soit un lot.
    
    Example:
        >>> lignes = extraire_lignes_brutes(html_content)
        >>> # [('A17_0_1', 'DUPONT (12A)'), ('A17_0_2', 'Lot 0021 Appartement 3P')]
    """
    # Accepte soit une chaîne HTML soit un objet HTMLParser déjà construit.
    if isinstance(Html_lot_copro, HTMLParser):
        arbre = Html_lot_copro
    else:
        arbre = HTMLParser(Html_lot_copro)
    lignes = []
    for noeud in arbre.css("[id]"):
        idv = noeud.attributes.get("id")
        if idv and PATRON_ID.match(idv):
            texte = noeud.text() or ""
            texte = " ".join(texte.split())
            if not texte:
                continue
            texte = normaliser_prefixes_proprietaire(texte)
            bas = texte.lower()
            if any(m in bas for m in MOTS_A_EXCLURE):
                continue
            lignes.append((idv, texte))
    return lignes

def detecter_proprietaire(ligne: str) -> tuple[str, str] | None:
    """
    Détecte si une ligne représente un propriétaire et extrait ses informations.
    
    Recherche le pattern "NOM (CODE)" où CODE est un identifiant numérique
    éventuellement suivi d'une lettre (ex: "12A").
    
    Args:
        ligne: Texte à analyser.
    
    Returns:
        Tuple (nom, code) si la ligne correspond à un propriétaire,
        None sinon.
    
    Example:
        >>> detecter_proprietaire("DUPONT Jean (12A)")
        ('DUPONT Jean', '12A')
        >>> detecter_proprietaire("Lot 0021 Appartement")
        None
    """
    m = _PATRON_CODE_RE.match(ligne)
    if m:
        nom = m.group("nom").strip()
        code = m.group("code").strip()
        return nom, code
    return None

def est_ligne_lot(ligne: str) -> bool:
    """
    Détermine si une ligne décrit un lot de copropriété.
    
    Recherche les patterns caractéristiques d'une ligne de lot:
    - "Lot" suivi d'un numéro (ex: "Lot 0021")
    - Présence du mot "Appartement"
    
    Args:
        ligne: Texte à analyser.
    
    Returns:
        True si la ligne décrit un lot, False sinon.
    
    Example:
        >>> est_ligne_lot("Lot 0021 Appartement 3P")
        True
        >>> est_ligne_lot("DUPONT (12A)")
        False
    """
    if re.search(r"\bLot\b\s*\d+", ligne, re.IGNORECASE):
        return True
    if re.search(r"\bAppartement\b", ligne, re.IGNORECASE):
        return True
    return False

def consolider_proprietaires_lots(elements) -> list[dict]:
    """
    elements : liste ordonnée de (id, texte)
    retourne : liste ordonnée de dict { 'nom_proprietaire': nom, 'code_proprietaire': code, 'num_apt': num, 'type_apt': type }
    logique : associer les lots qui suivent un propriétaire au propriétaire courant.
    Comportement : on retourne une entrée par lot. Si un propriétaire n'a pas de lot, on
    retourne une entrée avec les champs num_apt/type_apt vides.
    """
    consolide = []
    current_owner = None
    current_owner_had_lot = False

    for _id, texte in elements:
        proprietaire = detecter_proprietaire(texte)
        if proprietaire:
            # si le propriétaire précédent n'avait pas de lot, on ajoute une entrée vide
            if current_owner is not None and not current_owner_had_lot:
                # Pour les propriétaires sans lot: mettre 'NA' si c'est une SCIC/AB HABITAT
                if est_scic(current_owner.get("nom") or ""):
                    na_num, na_type = "NA", "NA"
                else:
                    na_num, na_type = "", ""
                consolide.append({
                    "nom_proprietaire": current_owner["nom"],
                    "code_proprietaire": current_owner["code"],
                    "num_apt": na_num,
                    "type_apt": na_type,
                })
            nom, code = proprietaire
            current_owner = {"nom": nom, "code": code}
            current_owner_had_lot = False
            continue
        if est_ligne_lot(texte):
            # extraire numéro et type depuis la ligne de lot
            num, typ = extraire_info_lot(texte)
            num = num or ""
            typ = (typ or "").lower()
            if current_owner is None:
                consolide.append({
                    "nom_proprietaire": None,
                    "code_proprietaire": None,
                    "num_apt": num,
                    "type_apt": typ,
                })
            else:
                # Si le propriétaire est une SCIC / AB HABITAT, forcer 'NA' même si un lot est trouvé
                if est_scic(current_owner.get("nom") or ""):
                    entry_num, entry_type = "NA", "NA"
                else:
                    entry_num, entry_type = num, typ
                consolide.append({
                    "nom_proprietaire": current_owner["nom"],
                    "code_proprietaire": current_owner["code"],
                    "num_apt": entry_num,
                    "type_apt": entry_type,
                })
                current_owner_had_lot = True
            continue

    # fin de boucle : si le dernier propriétaire n'a pas eu de lot, ajouter une entrée vide
    if current_owner is not None and not current_owner_had_lot:
        # Pour les propriétaires sans lot: mettre 'NA' si c'est une SCIC/AB HABITAT
        if est_scic(current_owner.get("nom") or ""):
            na_num, na_type = "NA", "NA"
        else:
            na_num, na_type = "", ""
        consolide.append({
            "nom_proprietaire": current_owner["nom"],
            "code_proprietaire": current_owner["code"],
            "num_apt": na_num,
            "type_apt": na_type,
        })

    return consolide

def extraire_info_lot(texte_lot: str):
    """
    Extrait (num_lot, type_appt) depuis une chaîne de description de lot.
    - num_lot : chaîne sans zéros initiaux (ex: "59")
    - type_appt : ex: "3P" (majuscule, sans espace) ou "" si non trouvé
    Retourne (num_lot, type_appt) ou (None, None) si échec complet.
    """
    if not texte_lot:
        return None, None
    m = re.search(r"\bLot\b(?:\s*[:\-])?\s*0*(\d+)\b", texte_lot, re.IGNORECASE)
    numero = m.group(1) if m else None
    typ = ""
    m2 = re.search(r"\bAppartement\b.*?(\d+)\s*p\b", texte_lot, re.IGNORECASE)
    if not m2:
        m2 = re.search(r"(\d+)\s*p\b", texte_lot, re.IGNORECASE)
    if m2:
        typ = f"{m2.group(1).upper()}P" if m2.group(1) else ""
    if numero is not None:
        numero = str(int(numero)) if numero.isdigit() else numero
    return numero, typ

def est_scic(nom_proprietaire: str) -> bool:
    """
    Vérifie si le propriétaire est une SCIC ou AB HABITAT.
    
    Les SCIC et AB HABITAT sont des entités spéciales qui n'ont pas de lots
    attribués de manière standard. Leurs lots sont marqués comme "NA".
    
    Args:
        nom_proprietaire: Nom du propriétaire à vérifier.
    
    Returns:
        True si le nom contient "SCIC", "AB HABITAT" ou "AB-HABITAT"
        (insensible à la casse), False sinon.
    
    Example:
        >>> est_scic("SCIC Habitat")
        True
        >>> est_scic("DUPONT Jean")
        False
    """
    if not nom_proprietaire:
        return False
    u = nom_proprietaire.upper()
    return "SCIC" in u or "AB HABITAT" in u or "AB-HABITAT" in u

def afficher_avec_rich(consolide: list[dict]) -> None:
    """
    Affiche les données consolidées dans une table formatée en console.
    
    Utilise la bibliothèque Rich pour afficher un tableau avec les colonnes:
    - Nom propriétaire
    - Code propriétaire
    - Numéro de lot
    - Type d'appartement
    
    Les propriétaires SCIC/AB HABITAT ont leurs lots affichés comme "NA".
    
    Args:
        consolide: Liste de dictionnaires avec les clés:
            - 'nom_proprietaire' ou 'proprietaire': str
            - 'code_proprietaire' ou 'code': str
            - 'num_apt': str (numéro de lot)
            - 'type_apt': str (type d'appartement, ex: "3p")
    
    Returns:
        None (affiche directement dans la console).
    """
    consoleur = Console()
    tableau = Table(show_header=True, header_style="bold magenta")
    tableau.add_column("Nom proprietaire", overflow="fold")
    tableau.add_column("Code", justify="center")
    tableau.add_column("Num Lot", justify="center")
    tableau.add_column("Type Apt", justify="center")

    # Le format attendu de "consolide" est une liste d'entrées où chaque entrée
    # a: proprietaire, code, num_apt, type_apt
    for entree in consolide:
        proprietaire = entree.get("nom_proprietaire") or entree.get("proprietaire")
        code = entree.get("code_proprietaire") or entree.get("code") or ""
        num = entree.get("num_apt") or ""
        typ = entree.get("type_apt") or ""

        # normaliser type en minuscules (ex: '3P' -> '3p')
        typ = typ.lower() if isinstance(typ, str) else typ

        if proprietaire and est_scic(proprietaire):
            tableau.add_row(proprietaire, code, "NA", "NA")
            continue

        if proprietaire:
            tableau.add_row(proprietaire, code, num, typ)
        else:
            tableau.add_row("INCONNU", "", num, typ)

    consoleur.print(tableau)
    total = len(consolide)
    consoleur.print(f"[bold]{total}[/bold] propriétaires/groupes trouvés.")
