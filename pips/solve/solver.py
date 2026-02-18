import typing

from pips.model import Board, BoardStatus, Constraint, Location, LocationSet, Orientation, Placement, Position

from .node import Node, SolverCaches, SolverDebug


def _is_valid(loc: Location, dir: Orientation, region: LocationSet):
    if (opposite := loc + dir.offset) not in region:
        return False
    new_empty_tiles = region - LocationSet([loc, opposite])
    for new_region in new_empty_tiles.connected_regions():
        if len(new_region) % 2 == 1:
            return False
    return True


def _board_state_key(placements: list[Placement]):
    placements.sort()
    return tuple(placements)


class Solver(SolverCaches, SolverDebug):
    def __init__(self, board: Board):
        self._nodes: dict[tuple[Placement, ...], Node | BoardStatus] = {(): (node := Node(board.copy(reset=True)))}
        self._open: list[list[Node]] = [[node]]
        self._constraint_map: dict[Location, Constraint] = {}
        self._valid_positions: dict[tuple[Position, ...], tuple[Position, ...]] = {}
        self._solutions: list[Node] = []
        for constraint in board.constraints:
            for tile in constraint.tiles:
                self._constraint_map[tile] = constraint

    def open_count_by_depth(self) -> list[int]:
        return [len(tier) for tier in self._open]

    def get_constraint(self, loc: Location) -> Constraint | None:
        return self._constraint_map.get(loc, None)

    @property
    def solutions(self) -> typing.Sequence[Node]:
        return self._solutions

    def get_valid_positions(self, board: Board) -> list[Position]:
        # strip dominoes and sort
        placements = sorted(pl.pos for pl in board.placements)
        # lookup
        if (valid := self._valid_positions.get(key := tuple(placements))) is None:
            # calculate
            self._valid_positions[key] = valid = tuple(
                Position(loc, dir)
                for region in board.empty_locations.connected_regions()
                for loc in region
                for dir in Orientation
                if _is_valid(loc, dir, region)
            )
        return valid

    def expand_next(self) -> Node | None:
        open_tier = next((tier for tier in self._open if len(tier) > 0), None)
        if not open_tier:
            return None

        node = open_tier.pop()
        if not node.open:
            raise ValueError('Open node is already closed')

        node.expand(self, self)
        if node.solved:
            self._solutions.append(node)

        # free memory
        self._nodes[_board_state_key(node._board.placements)] = node.status

        return node

    def add_node(self, parent: Node, placement: Placement):
        state_key = _board_state_key([*parent.board.placements, placement])
        existing = self._nodes.get(state_key)
        if existing:
            return existing, True

        board = parent.board.copy(reset=False)
        board.place(placement)
        tier = len(state_key)
        while len(self._open) <= tier:
            self._open.append([])
        self._open[tier].append(child := Node(board))
        self._nodes[state_key] = child
        return child, False
