import typing

from pips.model import Board, Constraint, Location, LocationSet, Orientation, Placement

from .node import Node, SolverCaches, SolverDebug


class _Placement(typing.NamedTuple):
    loc: Location
    dir: Orientation

    def is_valid(self, region: LocationSet):
        if (opposite := self.loc + self.dir.offset) not in region:
            return False
        new_empty_tiles = region - LocationSet([self.loc, opposite])
        for new_region in new_empty_tiles.connected_regions():
            if len(new_region) % 2 == 1:
                return False
        return True


def _sort_key(pl: Placement):
    return (pl.location.y, pl.location.x, pl.orientation, pl.domino.left_pips, pl.domino.right_pips)


def _board_state_key(placements: list[Placement]):
    placements.sort(key=_sort_key)
    return tuple(placements)


class Solver(SolverCaches, SolverDebug):
    _nodes: dict[tuple[Placement, ...], Node]
    _open: list[list[Node]]
    _constraint_map: dict[Location, Constraint]
    _valid_placements: dict[tuple[_Placement, ...], tuple[_Placement, ...]]
    _solutions: list[Node]

    def __init__(self, board: Board):
        self._nodes = {(): (node := Node(board.copy(reset=True)))}
        self._open = [[node]]
        self._constraint_map = {}
        self._valid_placements = {}
        self._solutions = []
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

    def get_valid_placements(self, board: Board) -> list[_Placement]:
        # strip dominoes and sort
        placements = sorted(_Placement(pl.location, pl.orientation) for pl in board._placements)
        # lookup
        if (valid := self._valid_placements.get(key := tuple(placements))) is None:
            # calculate
            self._valid_placements[key] = valid = []
            for region in board.empty_locations.connected_regions():
                for loc in region:
                    for dir in Orientation:
                        if (placement := _Placement(loc, dir)).is_valid(region):
                            valid.append(placement)
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

        return node

    def add_node(self, parent, placement):
        state_key = _board_state_key([*parent.board.placements, placement])
        existing = self._nodes.get(state_key)
        if existing:
            return existing, True

        board = parent.board.copy(reset=False)
        board.place(placement.domino, placement.location, placement.orientation)
        tier = len(state_key)
        while len(self._open) <= tier:
            self._open.append([])
        self._open[tier].append(child := Node(board))
        self._nodes[state_key] = child
        return child, False


"""



export default class Solver {

  get numOpenNodes(): number {
    return this._numOpenNodes;
  }

  get depthOpens(): Record<number, number> {
    return _.fromPairs(_.map(this._open, (tier, index) => [index, tier.length]));
  }

  get solutions(): readonly SolverNode[] {
    return this._solutions;
  }

  get root(): SolverNode {
    return this._nodes[''];
  }

  buildStack(node: SolverNode): SolverNode[] {
    const placements = node.board.placements;
    if (placements.length === 0) {
      return [node];
    }
    const parent = this._nodes[boardStateKey(placements.slice(0, placements.length - 1))];
    const stack = this.buildStack(parent);
    stack.push(node);
    return stack;
  }
}
"""
