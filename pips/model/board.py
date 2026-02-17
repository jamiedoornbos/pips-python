import typing

from .constraint import Constraint
from .domino import Domino, PipCount
from .locationset import Location, LocationSet
from .orientation import Orientation
from .placement import Placement

BoardStatus = typing.Literal['won', 'lost', 'incomplete']


class Board:
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

    def place(self, domino: Domino, location: Location, orientation: Orientation):
        placement = Placement(domino, location, orientation)

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


"""

import _ from 'lodash';

import { BoardState } from './board-state';
import Constraint from './constraint';
import Domino, { PipCount } from './domino';
import DominoPlacement from './domino-placement';
import { Tile } from './tile';
import { TileSet } from './tile-set';
import { Orientation, VECTORS } from './vectors';

export type BoardStatus = 'won' | 'lost' | 'incomplete';

export type BoardResult = {
  remainingMoves: number;
  brokenConstraints: Constraint[];
  status: BoardStatus;
};

export default class Board implements BoardState {
  _background: TileSet;
  _constraints: Constraint[];
  _dominoes: Domino[];
  _placements: DominoPlacement[];
  _remainingDomnioes: Domino[];
  _emptyTiles: TileSet;
  _boardState: Record<number, Record<number, PipCount>>;

  constructor(background: TileSet, constraints: Constraint[], dominoes: Domino[]) {
    this._background = background;
    this._constraints = constraints.slice();
    this._dominoes = dominoes.slice();
    this._remainingDomnioes = dominoes.slice();
    this._emptyTiles = this._background;
    this._placements = [];
    this._boardState = {};
  }

  get background(): TileSet {
    return this._background;
  }

  get constraints(): readonly Constraint[] {
    return this._constraints;
  }

  get dominoes(): readonly Domino[] {
    return this._dominoes;
  }

  get placements(): readonly DominoPlacement[] {
    return this._placements;
  }

  getPips(x: number, y: number) {
    const column = this._boardState[x];
    if (!column) {
      return null;
    }
    const val = column[y];
    return val === undefined ? null : val;
  }

  copy(): Board {
    const newBoard = new Board(this._background, this._constraints, this._dominoes);
    newBoard._placements = this._placements.slice();
    newBoard._boardState = _.cloneDeep(this._boardState);
    newBoard._remainingDomnioes = this._remainingDomnioes.slice();
    newBoard._emptyTiles = this._emptyTiles;
    return newBoard;
  }

  reset() {
    this._placements = [];
    this._remainingDomnioes = this._dominoes.slice();
    this._emptyTiles = this._background;
    this._boardState = {};
  }

  unplace(domino: Domino) {
    const index = _.findIndex(this._placements, (placement) => placement.domino.equals(domino));
    if (index === -1) {
      throw new Error(`Domino ${domino} is not on the board`);
    }
    const placement = this._placements[index];
    this._emptyTiles = new TileSet([...this._emptyTiles, ...placement]);
    this._remainingDomnioes.push(placement.domino);
    this._placements.splice(index, 1);
    delete this._boardState[placement.location.x][placement.location.y];
  }

  place(domino: Domino, location: Tile, orientation: Orientation) {
    // check domino belongs to set
    const index = _.findIndex(this._remainingDomnioes, (d) => d.equals(domino));
    if (index === -1) {
      throw new Error(`Domino ${domino} is not in the remaining ones`);
    }

    const extent = VECTORS[orientation].map(location.add.bind(location));

    // check not out of bounds
    for (const pt of extent) {
      if (!this._background.has(pt)) {
        throw new Error(`Domino placement ${orientation} is out of bounds at ${pt}`);
      }
    }

    // check overlap with other dominoes
    for (const placement of this._placements) {
      for (const pt1 of placement) {
        for (const pt2 of extent) {
          if (pt1.equals(pt2)) {
            throw new Error(`DomionoPlacement overlaps another: ${placement}`);
          }
        }
      }
    }

    const placement = new DominoPlacement(domino, location, orientation);
    this._placements.push(placement);
    this._remainingDomnioes.splice(index, 1);
    this._emptyTiles = this._emptyTiles.without(placement);
    domino._pips.forEach((pips, index) => {
      const tile = location.add(VECTORS[orientation][index]);
      this._boardState[tile.x] = this._boardState[tile.x] || {};
      this._boardState[tile.x][tile.y] = pips;
    });
  }

  testFinished(): BoardResult {
    const remainingMoves = this.remainingDominoes.length;
    const brokenConstraints: Constraint[] =
      remainingMoves === 0 ? this.constraints.filter((constraint) => !constraint.isSatisfied(this)) : [];
    const status = remainingMoves === 0 ? (brokenConstraints.length === 0 ? 'won' : 'lost') : 'incomplete';
    return {
      remainingMoves,
      brokenConstraints,
      status,
    };
  }

  get remainingDominoes(): readonly Domino[] {
    return this._remainingDomnioes;
  }

  get emptyTiles(): TileSet {
    return this._emptyTiles;
  }
}

"""
