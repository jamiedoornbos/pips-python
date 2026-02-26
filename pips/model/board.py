import typing

from .constraint import BoardState, Constraint
from .domino import Domino, PipCount
from .locationset import Location, LocationSet
from .placement import Placement

BoardStatus = typing.Literal['won', 'lost', 'incomplete']


class BoardResult(typing.NamedTuple):
    remaining_moves: int
    broken_constraints: list[Constraint]
    status: BoardStatus


class Board(BoardState):
    def __init__(
        self,
        background: LocationSet,
        constraints: tuple[Constraint],
        dominoes: tuple[Domino],
    ):
        self.background: LocationSet = background
        self.constraints: typing.Sequence[Constraint] = constraints
        self.all_dominoes: tuple[Domino] = dominoes
        self._remaining_dominoes: list[Domino] = list(dominoes)
        self._placements: list[Placement] = []
        self._empty_locations: LocationSet = background
        self._board_state: dict[Location, PipCount | None] = {}

    def copy(self, /, reset: bool):
        board = Board(self.background, self.constraints, self.all_dominoes)
        if not reset:
            board._remaining_dominoes = list(self._remaining_dominoes)
            board._placements = [*self._placements]
            board._empty_locations = self._empty_locations
            board._board_state = {**self._board_state}
        return board

    @property
    def placements(self) -> typing.Sequence[Placement]:
        return self._placements

    @property
    def empty_locations(self) -> LocationSet:
        return self._empty_locations

    def get_pips(self, location: Location) -> PipCount | None:
        return self._board_state.get(location)

    def place(self, placement: Placement):
        domino, (location, orientation) = placement

        # check domino belongs to set
        if domino not in self._remaining_dominoes:
            raise ValueError(f'Domino {domino} is not in the remaining ones')

        extent = LocationSet([location, location + orientation.offset])
        for loc in extent:
            if loc not in self.empty_locations:
                if loc not in self.background:
                    raise ValueError(f'Domino placement {placement} is out of bounds at {loc}')
                else:
                    raise ValueError(f'Domino placement {placement} overlaps at {loc}')

        self._placements.append(placement)
        self._remaining_dominoes.remove(domino)
        self._empty_locations = self._empty_locations - extent
        self._board_state[location] = domino.left_pips
        self._board_state[location + orientation.offset] = domino.right_pips

    def test_finished(self) -> BoardResult:
        remaining = len(self._remaining_dominoes)
        if remaining:
            return BoardResult(remaining, [], 'incomplete')
        broken_constraints = [constraint for constraint in self.constraints if not constraint.is_satisfied(self)]
        status = 'lost' if broken_constraints else 'won'
        return BoardResult(remaining, broken_constraints, status)
