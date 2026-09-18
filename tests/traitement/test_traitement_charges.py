"""Tests pour le traitement et le parsing HTML des charges (Traitement/Charge_Copro.py)."""

from __future__ import annotations

import pytest
from selectolax.parser import HTMLParser

from cptcopro.Traitement import Charge_Copro as tp
from tests.conftest import load_fixture


def _extract_date_from_result(res: str | tuple[str, str | None]) -> str:
    """Extrait la chaîne de date du résultat de recuperer_date_situation_copro."""
    if isinstance(res, tuple):
        return res[0]
    return res


# ---------------------------------------------------------------------------
# Tests normalise_somme
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_val, expected",
    [
        ("1 234,56", 1234.56),
        ("1.234,56", 1234.56),
        ("1234.56", 1234.56),
        ("+1 234,56", 1234.56),
        ("-1 234,56", -1234.56),
        ("\xa0 1 234,56 €", 1234.56),
        ("0,00", 0.0),
        ("0.00", 0.0),
        ("", 0.0),
        (None, 0.0),
        ("invalide", 0.0),
        ("150,00 €", 150.0),
    ],
)
def test_normalise_somme_various_formats(input_val, expected):
    """Vérifie la robustesse de normalise_somme sur différents formats monétaires."""
    assert tp.normalise_somme(input_val) == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests recuperer_date_situation_copro
# ---------------------------------------------------------------------------


def test_recuperer_date_situation_copro_from_fixture():
    """Vérifie l'extraction de date depuis la fixture Solde_copro2."""
    html = load_fixture("Solde_copro2_fixture.html")
    parser = HTMLParser(html)
    res = tp.recuperer_date_situation_copro(parser)
    date_str = _extract_date_from_result(res)
    assert len(date_str) == 10
    assert date_str.count("-") == 2


def test_recuperer_date_situation_copro_fallback_full_document():
    """Vérifie le repli sur le texte complet si la balise td#lzA1 est absente."""
    html = "<html><body><div>Situation des copropriétaires au 15/03/2026</div></body></html>"
    parser = HTMLParser(html)
    date_str = tp.recuperer_date_situation_copro(parser)
    assert date_str == "2026-03-15"


def test_extract_raw_date_text():
    """Vérifie la fonction interne _extract_raw_date_text."""
    html_with_node = (
        '<html><body><table><tr><td id="lzA1">Date au 01/01/2026</td></tr></table></body></html>'
    )
    texte, node_html = tp._extract_raw_date_text(HTMLParser(html_with_node))
    assert "01/01/2026" in texte
    assert "lzA1" in node_html

    html_without_node = "<html><body><div>Autre contenu</div></body></html>"
    texte2, node_html2 = tp._extract_raw_date_text(HTMLParser(html_without_node))
    assert "Autre contenu" in texte2
    assert node_html2 == ""


# ---------------------------------------------------------------------------
# Tests recuperer_situation_copro
# ---------------------------------------------------------------------------


def test_table_with_classes():
    html = load_fixture("table_with_classes.html")
    parser = HTMLParser(html)
    res = tp.recuperer_date_situation_copro(parser)
    date_str = _extract_date_from_result(res)
    data = tp.recuperer_situation_copro(parser, date_str)
    assert len(data) >= 2
    assert data[0][0] == "001"


def test_table_without_classes_fallback():
    html = load_fixture("table_without_classes.html")
    parser = HTMLParser(html)
    res = tp.recuperer_date_situation_copro(parser)
    date_str = _extract_date_from_result(res)
    data = tp.recuperer_situation_copro(parser, date_str)
    assert len(data) >= 1
    assert data[0][1] == "Legrand"


def test_no_table_returns_empty():
    html = load_fixture("no_table.html")
    parser = HTMLParser(html)
    res = tp.recuperer_date_situation_copro(parser)
    date_str = _extract_date_from_result(res)
    data = tp.recuperer_situation_copro(parser, date_str)
    assert data == []


def test_multiheader_and_select_rows_filtered():
    html = """
    <html>
      <body>
        <td id="lzA1">Solde des copropriétaires au 29/08/2026</td>
        <table id="ctzA1">
          <tr><td class="ttA3">Informations</td><td class="ttA4"></td><td class="ttA5"></td><td class="ttA6"></td></tr>
          <tr><td>Code</td><td>Copropriétaire</td><td>Débit</td><td>Crédit</td></tr>
          <tr></tr>
          <tr><td>558AAB-HABITAT480AADRIEN J. / RAMOS...</td><td>558A</td><td>0,00</td><td>0,00</td></tr>
          <tr><td>001</td><td>Dupont Jean</td><td>150,00</td><td>0,00</td></tr>
          <tr><td>002</td><td>Martin Paul</td><td>0,00</td><td>80,00</td></tr>
        </table>
      </body>
    </html>
    """
    parser = HTMLParser(html)
    data = tp.recuperer_situation_copro(parser, "2026-08-29")
    assert len(data) == 2
    assert data[0][0] == "001"
    assert data[0][1] == "Dupont Jean"
    assert data[1][0] == "002"
    assert data[1][1] == "Martin Paul"


def test_webdev_nested_tables_structure():
    """Vérifie la robustesse face à la structure WebDev réelle avec sous-tables imbriquées."""
    html = """
    <html>
      <body>
        <td id="lzA1">Solde des copropriétaires au 10/09/2026 de l'immeuble 0052</td>
        <table id="ctzA1">
          <tr><td>Solde des copropriétaires...</td></tr>
          <tr id="ttA1">
            <td id="tzclzA1">
              <table id="A1_TITRES_POS">
                <tr>
                  <td><div id="A1_TITRES_1"><table><tr><td class="ttA3">Code</td></tr></table></div></td>
                  <td><div id="A1_TITRES_2"><table><tr><td class="ttA4">Copropriétaire</td></tr></table></div></td>
                  <td><div id="A1_TITRES_3"><table><tr><td class="ttA5">Débit</td></tr></table></div></td>
                  <td><div id="A1_TITRES_4"><table><tr><td class="ttA6">Crédit</td></tr></table></div></td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td id="tzdlzA1">
              <table id="A1_TB">
                <tr id="A1_0">
                  <td class="aligncenter wbcolA3">558A</td>
                  <td class="wbcolA4">AB-HABITAT</td>
                  <td class="wbcolA5"></td>
                  <td class="wbcolA6"></td>
                </tr>
                <tr id="A1_1">
                  <td class="aligncenter wbcolA3">480A</td>
                  <td class="wbcolA4">ADRIEN J.</td>
                  <td class="wbcolA5"></td>
                  <td class="wbcolA6">197,16 €</td>
                </tr>
                <tr id="A1_2">
                  <td class="aligncenter wbcolA3">3485A</td>
                  <td class="wbcolA4">AOUDOU OUMAROU</td>
                  <td class="wbcolA5">3 548,12 €</td>
                  <td class="wbcolA6"></td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    parser = HTMLParser(html)
    date_str = tp.recuperer_date_situation_copro(parser)
    assert date_str == "2026-09-10"

    data = tp.recuperer_situation_copro(parser, date_str)
    assert len(data) == 3
    assert data[0] == ("558A", "AB-HABITAT", 0.0, 0.0, "2026-09-10")
    assert data[1] == ("480A", "ADRIEN J.", 0.0, 197.16, "2026-09-10")
    assert data[2] == ("3485A", "AOUDOU OUMAROU", 3548.12, 0.0, "2026-09-10")
