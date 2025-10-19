from selectolax.parser import HTMLParser
import os

from cptcopro import Traitement_Parsing as tp


def load_fixture(name: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "fixtures")
    path = os.path.normpath(os.path.join(base, name))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_table_with_classes():
    html = load_fixture("table_with_classes.html")
    parser = HTMLParser(html)
    date_str, last_check = tp.recuperer_date_situation_copro(parser)
    data = tp.recuperer_situation_copro(parser, date_str, last_check)
    # should find two rows (we added two copropriétaires)
    assert len(data) >= 2
    # first tuple code matches
    assert data[0][0] == "001"


def test_table_without_classes_fallback():
    html = load_fixture("table_without_classes.html")
    parser = HTMLParser(html)
    date_str, last_check = tp.recuperer_date_situation_copro(parser)
    data = tp.recuperer_situation_copro(parser, date_str, last_check)
    assert len(data) >= 1
    assert data[0][1] == "Legrand"


def test_no_table_returns_empty():
    html = load_fixture("no_table.html")
    parser = HTMLParser(html)
    date_str, last_check = tp.recuperer_date_situation_copro(parser)
    data = tp.recuperer_situation_copro(parser, date_str, last_check)
    assert data == []
