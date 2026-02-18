from .placement import Domino, Location, Orientation, Placement, Position


def test_placement():
    placement = Placement(Domino(2, 3), Position(Location(1, 1), Orientation.EAST))
    assert str(placement) == '23 at (1, 1) facing east'
