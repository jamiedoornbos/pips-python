import typing

from .domino import Domino
from .location import Location
from .orientation import Orientation


class Placement(typing.NamedTuple):
    domino: Domino
    location: Location
    orientation: Orientation
