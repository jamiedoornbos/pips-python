from .location import Location
from .orientation import Orientation


class LocationSet(frozenset[Location]):
    def __sub__(self, rhs: LocationSet):
        return LocationSet(super().__sub__(rhs))

    def connected_regions(self) -> list[LocationSet]:
        remaining, regions = self, []
        while len(remaining):
            open, connected = {next(iter(remaining))}, set()
            while len(open):
                connected.add(location := open.pop())
                for orientation in Orientation:
                    neighbor = location + orientation.offset
                    if neighbor in remaining and neighbor not in connected and neighbor not in open:
                        open.add(neighbor)
            regions.append(region := LocationSet(connected))
            remaining = remaining - region
        return regions
