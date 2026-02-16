import typing

from .constraint import Constraint
from .domino import Domino
from .locationset import LocationSet
from .placement import Placement

BoardStatus = typing.Literal["won", "lost", "incomplete"]


class Board:
    background: LocationSet
    constraints: typing.Sequence[Constraint]
    all_dominoes: tuple[Domino]
    _remaining_dominoes: list[Domino]
    _placements: list[Placement]
    _empty_locations: LocationSet

    def __init__(
        self,
        background: LocationSet,
        constraints: tuple[Constraint],
        dominoes: tuple[Domino],
    ):
        self.background = background
        self.constraints = constraints
        self.all_dominoes = dominoes
        self._remaining_dominoes = list(dominoes)
        self._placements = []
        self._empty_locations = background

    def copy(self):
        return Board(self.background, self.constraints, self.all_dominoes)

    @property
    def placements(self) -> typing.Sequence[Placement]:
        return self._placements

    def empty_locations(self) -> LocationSet:
        return self._empty_locations
