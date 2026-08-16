import struct
import typing
from datetime import datetime

from fastapi import Depends
from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pips.db import Puzzle, PuzzleState
from pips.db.model.solver import Solver
from pips.db.session import get_session
from pips.model import Board, Constraint, Domino, Location, LocationSet, Orientation, Placement, Position
from pips.model.constraint import ConstraintType
from pips.solve.shell import ResultStatus

_ORIENTATION_INTS = {Orientation.EAST: 0, Orientation.SOUTH: 1, Orientation.WEST: 2, Orientation.NORTH: 3}

_INT_ORIENTATIONS = {value: key for key, value in _ORIENTATION_INTS.items()}


def loc_to_int(loc: Location) -> int:
    return (loc.y << 7) | loc.x


def int_to_loc(xy: int) -> Location:
    return Location(xy & 0x7F, xy >> 7)


def loc_list_to_int_list(locs: typing.Iterable[Location]) -> list[int]:
    return [loc_to_int(loc) for loc in locs]


def domino_to_int(domino: Domino) -> int:
    return (domino.left_pips << 4) | domino.right_pips


def int_to_domino(dom: int) -> Domino:
    return Domino(dom >> 4, dom & 0xF)


def board_to_puzzle(board: Board, puzzle: Puzzle):
    if any(loc.x < 0 or loc.y < 0 for loc in board.background):
        raise ValueError('Background has negative coordinate')
    if any(loc.x < 0 or loc.y < 0 for constraint in board.constraints for loc in constraint.tiles):
        raise ValueError('Constraint has negative coordinate')

    puzzle.background = loc_list_to_int_list(board.background)
    puzzle.constraints = [
        {
            'tiles': loc_list_to_int_list(constraint.tiles),
            'type': constraint.type.value.name,
            'value': constraint.value,
        }
        for constraint in board.constraints
    ]
    puzzle.dominoes = [domino_to_int(domino) for domino in board.all_dominoes]


def puzzle_to_board(puzzle: Puzzle) -> Board:
    return Board(
        LocationSet(int_to_loc(loc) for loc in puzzle.background),
        tuple(
            Constraint(
                LocationSet(int_to_loc(loc) for loc in con['tiles']),
                ConstraintType.from_name(con['type']),
                con['value'],
            )
            for con in puzzle.constraints
        ),
        tuple(int_to_domino(dom) for dom in puzzle.dominoes),
    )


def placement_to_int(placement: Placement) -> int:
    loc = loc_to_int(placement.pos.loc)  # 14 bits
    orientation = _ORIENTATION_INTS[placement.pos.dir]  # 2 bits
    domino = domino_to_int(placement.domino)  # 8 bits
    return (loc) | (orientation << 14) | (domino << 16)


def int_to_placement(pl: int) -> Placement:
    loc = int_to_loc(pl & 0x3FFF)
    orientation = _INT_ORIENTATIONS[(pl >> 14) & 0x3]
    domino = int_to_domino(pl >> 16)
    return Placement(domino, Position(loc, orientation))


def placements_to_bytes(placements: typing.Sequence[Placement]) -> bytes:
    return struct.pack(f'{len(placements)}i', *sorted(map(placement_to_int, placements)))


def bytes_to_placements(placements: bytes) -> list[Placement]:
    return [int_to_placement(int_placement) for int_placement in struct.unpack(f'{len(placements) // 4}i', placements)]


def _latest_versions() -> tuple[Select, type[Puzzle]]:
    ranked = select(
        Puzzle,
        func.row_number()
        .over(
            partition_by=Puzzle.title,
            order_by=Puzzle.version.desc(),
        )
        .label('row'),
    ).subquery()

    LatestPuzzle = aliased(Puzzle, ranked)

    return select(LatestPuzzle).where(ranked.c.row == 1), LatestPuzzle


class CatalogShell:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    def puzzle(self, title: str) -> PuzzleShell:
        return PuzzleShell(self, title)

    async def load_puzzle_titles(self) -> list[tuple[str, ResultStatus]]:
        stmt, LatestPuzzle = _latest_versions()
        stmt = (
            stmt.join(
                Solver,
                (LatestPuzzle.title == Solver.puzzle_title) & (LatestPuzzle.version == Solver.puzzle_version),
                isouter=True,
            )
            .with_only_columns(LatestPuzzle.title, Solver.status)
            .order_by(LatestPuzzle.created_at.desc())
        )
        return [
            (title, status.value if status else 'not_run') for title, status in (await self.session.execute(stmt)).all()
        ]


class PuzzleShell:
    def __init__(self, catalog: CatalogShell, title: str):
        self.catalog = catalog
        self.title = title

    @property
    def session(self) -> AsyncSession:
        return self.catalog.session

    def version(self, version: int) -> PuzzleVersionShell:
        return PuzzleVersionShell(self, version)

    async def latest_version(self) -> PuzzleVersionShell | None:
        query = select(func.max(Puzzle.version)).where(Puzzle.title == self.title)
        if (version := (await self.session.execute(query)).scalar()) is None:
            return None
        return self.version(version)

    async def versions(self) -> list[tuple[datetime, int]]:
        query = select(Puzzle).where(Puzzle.title == self.title).order_by(Puzzle.version.asc())
        puzzles = (await self.session.execute(query)).scalars().all()
        return [(puzzle.created_at, puzzle.version) for puzzle in puzzles]

    async def load(self, version: int | None = None) -> Board | None:
        if version is not None:
            puzzle = await self.session.get(Puzzle, (self.title, version))
        else:
            query, LatestPuzzle = _latest_versions()
            query = query.where(LatestPuzzle.title == self.title)
            puzzle = (await self.session.execute(query)).scalars().first()
        if puzzle is None:
            return None
        return puzzle_to_board(puzzle)

    async def save_new(self, board: Board) -> Board:
        puzzle = Puzzle(title=self.title, version=0)
        board_to_puzzle(board, puzzle)
        self.session.add(puzzle)
        await self.session.commit()
        return puzzle_to_board(puzzle)

    async def update(self, board: Board) -> tuple[Board, int]:
        version = await self.session.scalar(select(func.max(Puzzle.version)).where(Puzzle.title == self.title))
        if version is None:
            raise RuntimeError(f'Puzzle {self.title} not found')
        puzzle = Puzzle(
            title=self.title,
            version=version + 1,
        )
        board_to_puzzle(board, puzzle)
        self.session.add(puzzle)
        await self.session.commit()
        return puzzle_to_board(puzzle), puzzle.version


class PuzzleVersionShell:
    def __init__(self, puzzle: PuzzleShell, version: int):
        self.puzzle = puzzle
        self.version = version

    @property
    def session(self) -> AsyncSession:
        return self.puzzle.session

    @property
    def title(self) -> str:
        return self.puzzle.title

    async def load(self) -> Board | None:
        return await self.puzzle.load(self.version)

    async def upsert_board(self, board: Board, *new_placements: Placement) -> PuzzleState:
        """Inserts or fetches the state matching the board plus new placements and returns the row."""
        return await self.upsert_state(*board.placements, *new_placements)

    async def upsert_state(self, *board_placements: Placement) -> PuzzleState:
        """Inserts or fetches the state matching the placements and returns the row."""
        placements = placements_to_bytes(board_placements)
        stmt = (
            pg_insert(PuzzleState)
            .values(puzzle_title=self.title, puzzle_version=self.version, placements=placements)
            .on_conflict_do_update(
                index_elements=[PuzzleState.puzzle_title, PuzzleState.puzzle_version, PuzzleState.placements],
                set_={'placements': placements},  # no-op to fire RETURNING
            )
            .returning(PuzzleState)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def get_states(self) -> typing.Sequence[PuzzleState]:
        return (
            (
                await self.session.execute(
                    select(PuzzleState).where(
                        PuzzleState.puzzle_title == self.title, PuzzleState.puzzle_version == self.version
                    )
                )
            )
            .scalars()
            .all()
        )
