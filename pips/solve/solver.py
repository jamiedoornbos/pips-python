import typing

from pips.model import Board, Constraint, Location, LocationSet, Orientation, Placement

from .node import Node


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
    return (pl.loc.y, pl.loc.x, pl.dif, pl.domino.left_pips, pl.domino.right_pips)


def _board_state_key(placements: list[Placement]):
    placements.sort(key=_sort_key)
    return tuple(placements)


class Solver:
    _nodes: dict[tuple[Placement, ...], Node]
    _open: list[list[Node]]
    _constraint_map: dict[Location, Constraint]
    _valid_placements: dict[tuple[_Placement, ...], tuple[_Placement, ...]]
    _solutions: list[Node]

    def __init__(self, board: Board):
        self._nodes = {(): (node := Node(board.copy()))}
        self._open = [[node]]
        self._constraint_map = {}
        self._valid_placements = {}
        self._solutions = []
        for constraint in board.constraints:
            for tile in constraint.tiles:
                self._constraint_map[tile] = constraint

    def get_constraint(self, loc: Location) -> Constraint | None:
        return self._constraint_map.get(loc, None)

    def get_valid_placements(self, board: Board) -> list[_Placement]:
        # strip dominoes and sort
        placements = sorted(_Placement(pl.location, pl.orientation) for pl in board._placements)
        # lookup
        if (valid := self._valid_placements.get(key := tuple(placements))) is None:
            # calculate
            self._valid_placements[key] = valid = []
            for region in board.empty_locations().connected_regions():
                for loc in region:
                    for dir in Orientation:
                        if (placement := _Placement(loc, dir)).is_valid(region):
                            valid.append(placement)
        return valid


"""
export default class Solver {
  addNode(parent: SolverNode, placement: DominoPlacement): [SolverNode, boolean] {
    const key = boardStateKey([...parent.board.placements, placement]);
    const tier = parent.board.placements.length + 1;
    const previousNode = this._nodes[key];
    if (previousNode) {
      return [previousNode, true];
    }
    const board = parent.board.copy();
    board.place(placement.domino, placement.location, placement.orientation);
    const newNode = new SolverNode(board);
    let openNodes = this._open[tier];
    if (!openNodes) {
      this._open[tier] = openNodes = [];
    }
    openNodes.push(newNode);
    this._numOpenNodes++;
    this._nodes[key] = newNode;
    return [newNode, false];
  }

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

  expandNext(): SolverNode | null {
    const tier = _.find(this._open, (tier) => tier && tier.length > 0);
    if (!tier || !tier.length) {
      return null;
    }

    const node = tier.pop()!;
    if (!node.open) {
      throw new Error('Open node is already closed');
    }

    this._numOpenNodes--;
    node.expand(this);
    if (node.solved) {
      this._solutions.push(node);
    }
    return node;

    // if (!node.expanded) {
    //   node.expand();
    //   return;
    // }
    // if (node.open) {
    //   const unexpandedChild = _.find(node.children, ['expanded', false]);
    //   if (unexpandedChild) {
    //     unexpandedChild.expand();
    //     return;
    //   }
    //   // TODO: get highest scorer here?
    //   const openChild = _.find(node.children, ['open', true]);
    //   if (openChild) {
    //     this._stack.push(openChild);
    //     this.expandNext();
    //     return;
    //   }
    //   node._closed = 'All children closed';
    //   this._stack.pop();
    // }
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
