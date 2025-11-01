from cptcopro.Traitement_Lots_Copro import consolider_proprietaires_lots


def test_proprietaire_with_single_lot():
    elements = [
        ("A17_1_1", "Plop PLOP (3825A)"),
        ("A17_1_2", "Lot 0009: Appartement 3 p"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 1
    e = out[0]
    assert e["proprietaire"] == "Plop PLOP"
    assert e["code"] == "3825A"
    assert e["num_apt"] == "9"
    assert e["type_apt"] == "3p"


def test_proprietaire_with_multiple_lots():
    elements = [
        ("A17_1_1", "JEAN (100)"),
        ("A17_1_2", "Lot 001: Appartement 2 p"),
        ("A17_1_3", "Lot 002: Appartement 3 p"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 2
    nums = [o["num_apt"] for o in out]
    assert "1" in nums and "2" in nums


def test_lot_without_proprietaire():
    elements = [
        ("A17_1_1", "Lot 010: Appartement 1 p"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 1
    e = out[0]
    assert e["proprietaire"] is None
    assert e["num_apt"] == "10"


def test_proprietaire_without_lot():
    elements = [
        ("A17_1_1", "ALICE (555)"),
    ]
    out = consolider_proprietaires_lots(elements)
    assert len(out) == 1
    e = out[0]
    assert e["proprietaire"] == "ALICE"
    assert e["num_apt"] == ""
    assert e["type_apt"] == ""
