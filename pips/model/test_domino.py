from .domino import Domino


def test_pips_iteration():
    domino = Domino(0, 2)
    pips = list(domino.pips)
    assert pips == [0, 2]
