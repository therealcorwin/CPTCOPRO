from selectolax.parser import HTMLParser
import os
import pytest

from cptcopro import Traitement_Charge_Copro as tp


def load_fixture(name: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "fixtures")
    path = os.path.normpath(os.path.join(base, name))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_normalize_amount_various():
    cases = {
        "1 234,56": 1234.56,
        "1.234,56": 1234.56,
        "1234.56": 1234.56,
        "+1 234,56": 1234.56,
        "\xa0 1 234,56 €": 1234.56,
        "": 0.0,
        None: 0.0,
    }
    for inp, expected in cases.items():
        assert tp.normalise_somme(inp) == pytest.approx(expected, rel=1e-6)


def test_recuperer_date_situation_copro_from_fixture():
    html = load_fixture("Solde_copro2_fixture.html")
    parser = HTMLParser(html)
    date_str, last_check = tp.recuperer_date_situation_copro(parser)
    # date_str should be ISO format YYYY-MM-DD (the parser converts from DD/MM/YYYY)
    assert len(date_str) == 10
    assert date_str.count("-") == 2
    # last_check should be today's date in YYYY-MM-DD format
    assert len(last_check) == 10