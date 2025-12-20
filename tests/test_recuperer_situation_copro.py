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
    # recuperer_date_situation_copro peut renvoyer soit une chaîne soit un tuple
    res = tp.recuperer_date_situation_copro(parser)
    date_str = _extract_date_from_result(res)
    # recuperer_situation_copro peut accepter 2 ou 3 arguments selon la version
    try:
        data = tp.recuperer_situation_copro(parser, date_str)
    except TypeError:
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
    try:
        data = tp.recuperer_situation_copro(parser, date_str)
    except TypeError:
        data = tp.recuperer_situation_copro(parser, date_str)
    assert len(data) >= 1
    assert data[0][1] == "Legrand"


def test_no_table_returns_empty():
    html = load_fixture("no_table.html")
    parser = HTMLParser(html)
    res = tp.recuperer_date_situation_copro(parser)
    date_str = _extract_date_from_result(res)
    try:
        data = tp.recuperer_situation_copro(parser, date_str)
    except TypeError:
        data = tp.recuperer_situation_copro(parser, date_str)
    assert data == []
