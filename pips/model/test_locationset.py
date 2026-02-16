from .locationset import Location, LocationSet
from .orientation import Orientation


def test_connected_regions():
    locations = LocationSet([Location(0, 0)])
    assert locations.connected_regions() == [locations]

    for orientation in Orientation:
        loc = Location(0, 0)
        locations = LocationSet([loc, loc + orientation.offset])
        assert locations.connected_regions() == [locations]

    locations = LocationSet([loc1 := Location(0, 0), loc2 := Location(1, 1)])
    assert set(locations.connected_regions()) == (set([LocationSet([loc1]), LocationSet([loc2])]))
