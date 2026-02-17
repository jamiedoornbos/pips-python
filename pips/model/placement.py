import typing

from .domino import Domino
from .location import Location
from .orientation import Orientation


class Placement(typing.NamedTuple):
    domino: Domino
    location: Location
    orientation: Orientation

    def __repr__(self):
        return f'{self.domino} at {self.location} facing {self.orientation}'
