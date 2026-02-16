from pips.model import Board, Constraint, ConstraintType, Domino, Location, LocationSet, Orientation

from .solver import Solver


def test_valid_placements():
    background = LocationSet([Location(x, 0) for x in range(4)])
    constraint = Constraint(LocationSet([Location(x, 0) for x in (1, 2)]), ConstraintType.MATCH, None)
    board = Board(background, (constraint,), (Domino(0, 0), Domino(0, 1)))
    solver = Solver(board)
    valid = sorted(solver.get_valid_placements(board))
    assert len(valid) == 4

    def check(index, x, y, dir):
        assert valid[index].loc == Location(x, y)
        assert valid[index].dir == dir

    check(0, 0, 0, Orientation.EAST)
    check(1, 1, 0, Orientation.WEST)
    check(2, 2, 0, Orientation.EAST)
    check(3, 3, 0, Orientation.WEST)
