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

import re
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console
from rich.table import Table
from selectolax.parser import HTMLParser, Node

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


def _extract_raw_date_text(htmlparser: HTMLParser) -> tuple[str, str]:
    """Extrait le texte brut et le HTML du nœud td#lzA1 ou du document complet."""
    node = htmlparser.css_first("td#lzA1")
    logger.debug(f"Recherche du noeud 'td#lzA1' -> {'trouvé' if node else 'absent'}")
    if node:
        try:
            texte = node.text()
        except Exception:
            texte = ""
        try:
            node_html = node.html or ""
        except Exception:
            node_html = ""
    else:
        logger.warning("Balise td#lzA1 introuvable, recherche de la date dans tout le document.")
        try:
            texte = htmlparser.text()
        except Exception:
            texte = ""
        node_html = ""
    return texte or "", node_html


def _dump_debug_html(htmlparser: HTMLParser, texte_normalise: str, node_html: str) -> None:
    """Enregistre un dump HTML de diagnostic lors d'un échec de détection de date."""
    try:
        if hasattr(htmlparser, "html"):
            full_html = htmlparser.html
        elif hasattr(htmlparser, "raw_html"):
            full_html = htmlparser.raw_html()
        else:
            full_html = str(htmlparser)
    except Exception:
        full_html = ""

    dump_path = Path(__file__).parent / "last_runtime_dump.html"
    try:
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write("<!-- Debug dump: recuperer_date_situation_copro failure -->\n")
            f.write("<!-- texte (repr): -->\n")
            f.write(repr(texte_normalise) + "\n\n")
            f.write("<!-- node HTML (if any): -->\n")
            with suppress(Exception):
                f.write(node_html if node_html else "")
            f.write("\n<!-- full HTML (trunc 200k): -->\n")
            f.write(full_html[:200000] if full_html else "")
        logger.error(f"Date non trouvée — dump HTML écrit dans {dump_path}")
    except Exception as e:
        logger.error(f"Échec écriture dump HTML : {e}")


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
    texte, node_html = _extract_raw_date_text(htmlparser)

    for ch in ("\u00a0", "\u200b", "\u200c", "\u200d"):
        texte = texte.replace(ch, " ")
    texte_normalise = re.sub(r"\s+", " ", texte).strip()
    logger.debug(f"Texte normalisé (repr): {repr(texte_normalise)[:2000]}")

    match = re.search(r"(\d{2}/\d{2}/\d{4})", texte_normalise)
    if not match:
        _dump_debug_html(htmlparser, texte_normalise, node_html)
        raise ValueError("Date de situation introuvable dans td#lzA1")

    date_str = match.group(1)
    logger.info(f"Date trouvée : {date_str}")
    return datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")


def _detect_webdev_headers(table_body: Node) -> dict[str, int]:
    """Déduit les indices de colonnes pour les tables WebDev via les classes wbcolA*."""
    first_row = table_body.css_first("tr")
    indices: dict[str, int] = {}
    if first_row:
        for idx, cell in enumerate(first_row.css("td")):
            cls = cell.attributes.get("class") or ""
            if "wbcolA3" in cls and "Code" not in indices:
                indices["Code"] = idx
            elif "wbcolA4" in cls and "Copropriétaire" not in indices:
                indices["Copropriétaire"] = idx
            elif "wbcolA5" in cls and "Débit" not in indices:
                indices["Débit"] = idx
            elif "wbcolA6" in cls and "Crédit" not in indices:
                indices["Crédit"] = idx
    for i, rh in enumerate(["Code", "Copropriétaire", "Débit", "Crédit"]):
        indices.setdefault(rh, i)
    return indices


def _match_exact_header_row(rows: list[Node]) -> dict[str, int]:
    """Extrait les indices d'en-tête depuis une ligne contenant les libellés complets."""
    for row in rows:
        # Ignorer les lignes conteneurs WebDev contenant des sous-tables
        if row.css("table"):
            continue
        row_cells = [cell.text(strip=True) for cell in row.css("td, th")]
        row_lower = [c.lower() for c in row_cells]
        if "code" in row_lower and any(
            "copropriétaire" in c or "coproprietaire" in c for c in row_lower
        ):
            indices: dict[str, int] = {}
            for idx, c_text in enumerate(row_cells):
                c_low = c_text.lower()
                if c_low == "code" and "Code" not in indices:
                    indices["Code"] = idx
                elif ("copropriétaire" in c_low or "coproprietaire" in c_low) and "Copropriétaire" not in indices:
                    indices["Copropriétaire"] = idx
                elif ("débit" in c_low or "debit" in c_low) and "Débit" not in indices:
                    indices["Débit"] = idx
                elif ("crédit" in c_low or "credit" in c_low) and "Crédit" not in indices:
                    indices["Crédit"] = idx
            if all(k in indices for k in ["Code", "Copropriétaire", "Débit", "Crédit"]):
                logger.debug(f"Ligne d'en-tête identifiée : {row_cells} -> {indices}")
                return indices
    return {}


def _fallback_header_indices(first_header_row: Node | None) -> dict[str, int]:
    """Déduit les indices d'en-tête à partir de motifs partiels ou de positions par défaut."""
    indices: dict[str, int] = {}
    if first_header_row:
        first_cells = [cell.text(strip=True) for cell in first_header_row.css("td, th")]
        for idx, c_text in enumerate(first_cells):
            c_low = c_text.lower()
            if "code" in c_low and "Code" not in indices:
                indices["Code"] = idx
            elif "copro" in c_low and "Copropriétaire" not in indices:
                indices["Copropriétaire"] = idx
            elif ("déb" in c_low or "deb" in c_low) and "Débit" not in indices:
                indices["Débit"] = idx
            elif ("créd" in c_low or "cred" in c_low) and "Crédit" not in indices:
                indices["Crédit"] = idx

    for i, rh in enumerate(["Code", "Copropriétaire", "Débit", "Crédit"]):
        indices.setdefault(rh, i)
    logger.debug(f"Indices d'en-têtes complétés : {indices}")
    return indices


def _detect_charge_table_headers(table: Node) -> dict[str, int]:
    """Détecte les index des colonnes obligatoires dans la table des charges."""
    # 1. Vérification prioritaire des classes WebDev standards ttA*
    classes_cells = table.css("td.ttA3, td.ttA4, td.ttA5, td.ttA6, th.ttA3, th.ttA4, th.ttA5, th.ttA6")
    if len(classes_cells) == 4:
        indices: dict[str, int] = {}
        for idx, cell in enumerate(classes_cells):
            cls = cell.attributes.get("class") or ""
            if "ttA3" in cls:
                indices["Code"] = idx
            elif "ttA4" in cls:
                indices["Copropriétaire"] = idx
            elif "ttA5" in cls:
                indices["Débit"] = idx
            elif "ttA6" in cls:
                indices["Crédit"] = idx
        if len(indices) == 4:
            return indices

    indices = _match_exact_header_row(table.css("tr"))
    required_headers = ["Code", "Copropriétaire", "Débit", "Crédit"]
    if not all(k in indices for k in required_headers):
        indices = _fallback_header_indices(table.css_first("tr"))
    return indices


def _is_ignorable_charge_row(code: str, nom: str) -> bool:
    """Détermine si une ligne de charge correspond à un en-tête ou à un sélecteur parasite."""
    if not code or not nom:
        return True
    ignorable_codes = {"code", "copropriétaire", "coproprietaire", "informations", "en-tete1"}
    ignorable_names = {"copropriétaire", "coproprietaire", "nom", "nom propriétaire", "en-tete2"}
    if code.lower() in ignorable_codes or nom.lower() in ignorable_names:
        return True
    if len(code) > 30 or len(nom) > 150:
        logger.debug(f"Ligne de menu/filtre ignorée : code='{code[:30]}...'")
        return True
    return False


def _parse_single_charge_row(
    cells: list[str], header_indices: dict[str, int], date_suivi_copro: str
) -> tuple[str, str, float, float, str] | None:
    """Extrait et valide une ligne individuelle du tableau des charges."""
    try:
        code_proprietaire = cells[header_indices["Code"]].strip()
        nom_proprietaire = cells[header_indices["Copropriétaire"]].strip()
        if _is_ignorable_charge_row(code_proprietaire, nom_proprietaire):
            return None

        debit_cell = cells[header_indices["Débit"]] if "Débit" in header_indices else ""
        credit_cell = cells[header_indices["Crédit"]] if "Crédit" in header_indices else ""
        debit = normalise_somme(debit_cell)
        credit = normalise_somme(credit_cell)
        return (code_proprietaire, nom_proprietaire, debit, credit, date_suivi_copro)
    except (IndexError, ValueError) as e:
        logger.error(f"Erreur : {e}. Ligne mal formatée ou données invalides.")
        return None


def recuperer_situation_copro(htmlparser: HTMLParser, date_suivi_copro: str) -> list[Any]:
    """
    Extrait les informations de situation des copropriétaires à partir d'un document HTML.

    Parameters:
    - htmlparser (HTMLParser): Un objet HTMLParser contenant le document HTML à analyser.
    - date_suivi_copro (str): Une chaîne de caractères représentant la date au format JJ/MM/AAAA.

    Returns:
    - list[Any]: Liste de tuples (code_proprietaire, nom_proprietaire, debit, credit, date).
    """
    # 1. Sélection de la table de données :
    # Sur WebDev réel, table#A1_TB contient exclusivement les lignes du corps du tableau.
    # Dans les fixtures simplifiées ou tables classiques, table#ctzA1 est la table principale.
    table_body = htmlparser.css_first("table#A1_TB")
    if table_body:
        header_indices = _detect_webdev_headers(table_body)
        target_table = table_body
    else:
        target_table = htmlparser.css_first("table#ctzA1")
        if not target_table:
            logger.error("Tableau introuvable dans le document HTML.")
            return []
        header_indices = _detect_charge_table_headers(target_table)

    required_headers = ["Code", "Copropriétaire", "Débit", "Crédit"]
    min_cols = max(header_indices[k] for k in required_headers if k in header_indices) + 1
    data: list[Any] = []

    for row in target_table.css("tr"):
        # Ignorer les lignes conteneurs englobantes avec des sous-tables
        if row.css("table"):
            continue
        cells = [cell.text(strip=True) for cell in row.css("td")]
        if len(cells) >= min_cols:
            parsed = _parse_single_charge_row(cells, header_indices, date_suivi_copro)
            if parsed is not None:
                data.append(parsed)
        elif any(cells):
            logger.warning("Erreur : Ligne mal formatée, certaines colonnes sont manquantes.")

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
    for row in data:
        if isinstance(row, (tuple, list)) and len(row) >= 4:
            table_copro.add_row(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
            )

    # Affichage du tableau dans la console
    console.print(table_copro)
