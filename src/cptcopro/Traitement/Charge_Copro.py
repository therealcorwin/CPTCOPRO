"""Module de traitement et parsing HTML des charges des copropriétaires.

Ce module parse le HTML récupéré depuis l'extranet du syndic et extrait :
- La date de la situation (depuis td#lzA1)
- Le tableau des charges (depuis table#ctzA1)
- Les montants débit/crédit normalisés

Fonctions principales:
    recuperer_date_situation_copro(): Extrait la date de situation
    recuperer_situation_copro(): Extrait les données du tableau des charges
    afficher_etat_coproprietaire(): Affiche les données dans la console (rich)
"""
from selectolax.parser import HTMLParser  # type: ignore
from datetime import datetime
import re
from typing import Any
from rich.console import Console
from rich.table import Table
from loguru import logger
from pathlib import Path

logger.remove()
logger = logger.bind(type_log="TRAITEMENT")


def normalise_somme(s: str) -> float:
    """Normalise une chaîne représentant un montant en float.

    Supporte espaces insécables, séparateurs de milliers '.', virgule décimale,
    signes +/-, et supprime caractères non numériques.
    """
    if not s:
        return 0.0
    # remplacer NBSP par espace et trim
    s_clean = s.replace("\xa0", " ").strip()
    # ne garder que chiffres, signes, point et virgule
    s_clean = re.sub(r"[^0-9+\-\.,]", "", s_clean)
    if not s_clean:
        return 0.0
    # si à la fois '.' et ',' : on suppose '.' milliers et ',' décimal
    if "." in s_clean and "," in s_clean:
        s_clean = s_clean.replace(".", "")
        s_clean = s_clean.replace(",", ".")
    else:
        # remplacer virgule décimale par point
        s_clean = s_clean.replace(",", ".")
    # supprimer '+' éventuel
    s_clean = s_clean.replace("+", "")
    try:
        return float(s_clean)
    except Exception:
        return 0.0


def recuperer_date_situation_copro(htmlparser: HTMLParser) -> str:
    """
    Extrait la date de la situation des copropriétaires à partir d'un noeud HTML spécifié.

    La fonction recherche une balise "td" avec l'identifiant "lzA1" dans le document HTML,
    extrait le texte de la balise, nettoie le texte pour faciliter la recherche,
    et extrait la date au format JJ/MM/AAAA après le motif spécifié.

    Parameters:
    - HTMLParser (HTMLParser): Un objet HTMLParser contenant le document HTML à analyser.

    Returns:
    - str: La date extrait au format JJ/MM/AAAA.
    """
    node = htmlparser.css_first("td#lzA1")
    logger.debug(f"Recherche du noeud 'td#lzA1' -> {'trouvé' if node else 'absent'}")

    if node:
        try:
            texte = node.text()
        except Exception:
            texte = ""
        # essayer aussi d'obtenir le HTML du noeud pour debug
        try:
            node_html = node.html()
        except Exception:
            node_html = ""
        logger.debug(f"Contenu node.text() repr: {repr(texte)}")
        logger.debug(f"Contenu node.html() (trunc) repr: {repr(node_html)[:2000]}")
    else:
        # Fallback : chercher la date dans tout le document si la balise précise est absente
        logger.warning(
            "Balise td#lzA1 introuvable, recherche de la date dans tout le document."
        )
        try:
            texte = htmlparser.text()
            logger.debug(f"Contenu document text() (trunc) repr: {repr(texte)[:2000]}")
        except Exception:
            texte = ""

    # Normaliser le texte pour faciliter la recherche (remplacer NBSP, etc.)
    if texte is None:
        texte = ""
    # remplacer NBSP et quelques espaces invisibles communs
    for ch in ("\u00A0", "\u200B", "\u200C", "\u200D"):
        texte = texte.replace(ch, " ")
    texte_normalise = re.sub(r"\s+", " ", texte).strip()
    logger.debug(f"Texte normalisé (repr): {repr(texte_normalise)[:2000]}")

    # Extraire la date au format JJ/MM/AAAA
    match = re.search(r"(\d{2}/\d{2}/\d{4})", texte_normalise)
    if not match:
        # Avant d'échouer, sauvegarder un dump pour analyser le HTML reçu
        try:
            if hasattr(htmlparser, "html"):
                full_html = getattr(htmlparser, "html")
            elif hasattr(htmlparser, "raw_html"):
                full_html = htmlparser.raw_html()
            else:
                full_html = str(htmlparser)
        except Exception:
            full_html = ""

        dump_path = Path(__file__) / "last_runtime_dump.html"        
        try:
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dump_path, "w", encoding="utf-8") as f:
                f.write("<!-- Debug dump: recuperer_date_situation_copro failure -->\n")
                f.write("<!-- texte (repr): -->\n")
                f.write(repr(texte_normalise) + "\n\n")
                f.write("<!-- node HTML (if any): -->\n")
                try:
                    f.write(node_html if node_html else "")
                except Exception:
                    pass
                f.write("\n<!-- full HTML (trunc 200k): -->\n")
                f.write(full_html[:200000])
            logger.error(f"Date non trouvée — dump HTML écrit dans {dump_path}")
        except Exception as e:
            logger.error(f"Échec écriture dump HTML : {e}")

        raise ValueError("Date de situation introuvable dans td#lzA1")

    date_str = match.group(1)
    logger.info(f"Date trouvée : {date_str}")

    date_situation_copro = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    return date_situation_copro


def recuperer_situation_copro(
    htmlparser: HTMLParser, date_suivi_copro: str) -> list[Any]:
    """
    Extrait les informations de situation des copropriétaires à partir d'un document HTML.

    La fonction recherche une table spécifique dans le document HTML, extrait les en-têtes et les données des lignes,
    puis nettoie et convertit les données pour les renvoyer sous forme de liste de tuples.

    Parameters:
    - HTMLParser (HTMLParser): Un objet HTMLParser contenant le document HTML à analyser.
    - date_suivi_copro (str): Une chaîne de caractères représentant la date au format JJ/MM/AAAA.

        Returns:
        - list[Any]: Une liste de tuples contenant les données des copropriétaires.
            Chaque tuple a le format suivant : (code_proprietaire, nom_proprietaire, debit, credit, date).
    """
    # Trouver la table dans le document HTML
    table = htmlparser.css_first("table#ctzA1")

    data = []

    if table:
        # Extraire les en-têtes du tableau
        headers = [
            header.text(strip=True)
            for header in table.css("td.ttA3, td.ttA4, td.ttA5, td.ttA6")
        ]
        # Fallback : si aucune en-tête avec classes, essayer la première ligne du tableau
        if not headers:
            first_row = table.css_first("tr")
            if first_row:
                headers = [cell.text(strip=True) for cell in first_row.css("td")]

        logger.debug(f"En-têtes extraites : {headers}")  # Debug : Vérifier les en-têtes

        # Vérifier que les en-têtes nécessaires sont présents; si non, on infère par position
        required_headers = ["Code", "Copropriétaire", "Débit", "Crédit"]
        header_indices = {}
        for idx, h in enumerate(headers):
            header_indices[h] = idx

        # Si noms attendus non trouvés, fallback positionnel (0..3)
        missing = [rh for rh in required_headers if rh not in header_indices]
        if missing:
            # map positions
            logger.warning(
                f"En-têtes attendues manquantes {missing}, utilisation du mapping positionnel."
            )
            for i, rh in enumerate(required_headers):
                header_indices[rh] = i

        logger.debug(
            f"Indices des en-têtes : {header_indices}"
        )  # Debug : Vérifier les indices des colonnes

        # Extraire les données des lignes du tableau
        data = []
        # Prendre à partir de la 3ème ligne (index 2) pour être moins agressif sur les différents HTML
        rows = table.css("tr")[2:]
        for row in rows:
            cells = [cell.text(strip=True) for cell in row.css("td")]
            logger.debug(
                f"Ligne extraite : {cells}"
            )  # Debug : Vérifier les cellules extraites
            if len(cells) >= len(
                headers
            ):  # Vérifier que la ligne contient suffisamment de colonnes
                try:
                    # Vérifier que toutes les colonnes nécessaires sont présentes
                    code_proprietaire = cells[header_indices["Code"]]
                    nom_proprietaire = cells[header_indices["Copropriétaire"]]
                    debit_cell = (
                        cells[header_indices["Débit"]]
                        if header_indices.get("Débit") is not None
                        else ""
                    )
                    credit_cell = (
                        cells[header_indices["Crédit"]]
                        if header_indices.get("Crédit") is not None
                        else ""
                    )

                    debit = normalise_somme(debit_cell)
                    credit = normalise_somme(credit_cell)

                    # Ajouter les données nettoyées et converties à la liste
                    data.append(
                        (
                            code_proprietaire,
                            nom_proprietaire,
                            debit,
                            credit,
                            date_suivi_copro,
                        )
                    )
                except (IndexError, ValueError) as e:
                    logger.error(
                        f"Erreur : {e}. Ligne mal formatée ou données invalides."
                    )
                    continue
            else:
                logger.warning(
                    "Erreur : Ligne mal formatée, certaines colonnes sont manquantes."
                )
    else:
        logger.error("Tableau introuvable dans le document HTML.")
    return data


def afficher_etat_coproprietaire(data: list[Any], date_suivi_copro: str) -> None:
    """
    Affiche les informations de situation des copropriétaires dans un tableau formaté.

    La fonction prend une liste de données et une date en entrée,
    crée un tableau avec les informations des copropriétaires,
    puis affiche le tableau dans la console.

    Parameters:
        - data (list[Any]): Une liste de tuples contenant les données des copropriétaires.
            Chaque tuple doit avoir le format suivant : (code_proprietaire, nom_proprietaire, debit, credit, date).
    - date_suivi_copro (str): Une chaîne de caractères représentant la date au format JJ/MM/AAAA.

    Returns:
    - None
    """
    console = Console()
    # Création du tableau avec les en-têtes
    table_copro = Table(title=f"Suivi des Copropriétaires au : {date_suivi_copro}")
    table_copro.add_column("Code propriétaire", style="cyan", justify="center")
    table_copro.add_column("Nom propriétaire", style="magenta", justify="center")
    table_copro.add_column("Débit", style="red", justify="right")
    table_copro.add_column("Crédit", style="green", justify="right")

    # Ajout des lignes de données au tableau
    for (
        code_proprietaire,
        nom_proprietaire,
        debit,
        credit,
        date_suivi_copro,
    ) in data[3:]:
        table_copro.add_row(
            str(code_proprietaire),
            str(nom_proprietaire),
            str(debit),
            str(credit),
        )

    # Affichage du tableau dans la console
    console.print(table_copro)
