import typing

from .domino import Domino
from .location import Location
from .orientation import Orientation


class Position(typing.NamedTuple):
    loc: Location
    dir: Orientation

    def __str__(self):
        return f'{self.loc} facing {self.dir}'


class Placement(typing.NamedTuple):
    domino: Domino
    pos: Position

    def __str__(self):
        return f'{self.domino} at {self.pos}'
