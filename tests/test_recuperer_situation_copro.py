from selectolax.parser import HTMLParser
import os

from cptcopro.Traitement import Charge_Copro as tp


def load_fixture(name: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "fixtures")
    path = os.path.normpath(os.path.join(base, name))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_date_from_result(res):
    """Return date string from recuperer_date_situation_copro result.

    If res is a tuple (date, last_check) return the first element, otherwise return res.
    """
    if isinstance(res, tuple):
        return res[0]
    return res


def test_table_with_classes():
    html = load_fixture("table_with_classes.html")
    parser = HTMLParser(html)
    res = tp.recuperer_date_situation_copro(parser)
    date_str = _extract_date_from_result(res)
    data = tp.recuperer_situation_copro(parser, date_str)
    # should find two rows (we added two copropriétaires)
    assert len(data) >= 2
    # first tuple code matches
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

