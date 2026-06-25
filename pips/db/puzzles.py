import hashlib
import struct
import typing

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pips.db.model.puzzle import Puzzle, PuzzleState
from pips.model import Board, Constraint, Domino, Location, LocationSet, Orientation, Placement, Position


def _loc_to_int(loc: Location) -> int:
    return (loc.y << 7) | loc.x


def _int_to_loc(xy: int) -> Location:
    return Location(xy & 0x7F, xy >> 7)


def _loc_list_to_int_list(locs: typing.Iterable[Location]) -> list[int]:
    return [_loc_to_int(loc) for loc in locs]


def _domino_to_int(domino: Domino) -> int:
    return (domino.left_pips << 4) | domino.right_pips


def _int_to_domino(dom: int) -> Domino:
    return Domino(dom >> 4, dom & 0xF)


def _board_to_puzzle(board: Board, puzzle: Puzzle):
    if any(loc.x < 0 or loc.y < 0 for loc in board.background):
        raise ValueError('Background has negative coordinate')
    if any(loc.x < 0 or loc.y < 0 for constraint in board.constraints for loc in constraint.tiles):
        raise ValueError('Constraint has negative coordinate')

    puzzle.background = _loc_list_to_int_list(board.background)
    puzzle.constraints = [
        {
            'tiles': _loc_list_to_int_list(constraint.tiles),
            'type': constraint.type.value.name,
            'value': constraint.value,
        }
        for constraint in board.constraints
    ]
    puzzle.dominoes = [_domino_to_int(domino) for domino in board.all_dominoes]


async def save_new_puzzle(session: AsyncSession, title: str, board: Board) -> Board:
    puzzle = Puzzle(title=title, version=0)
    _board_to_puzzle(board, puzzle)
    session.add(puzzle)
    await session.commit()
    return _puzzle_to_board(puzzle)


async def update_puzzle(session: AsyncSession, title: str, board: Board) -> tuple[Board, int]:
    puzzle = Puzzle(
        title=title,
        version=session.execute(select(func.max(Puzzle.version)).where(Puzzle.title == title)).scalars().one() + 1,
    )
    _board_to_puzzle(board, puzzle)
    session.add(puzzle)
    await session.commit()
    return _puzzle_to_board(puzzle), puzzle.version


async def load_puzzle(session: AsyncSession, title: str, version: int | None = None) -> Board:
    if version is not None:
        puzzle = await session.get(Puzzle, (title, version))
    else:
        query, LatestPuzzle = _latest_versions()
        query = query.where(LatestPuzzle.title == title)
        puzzle = (await session.execute(query)).scalars().first()
    return _puzzle_to_board(puzzle)


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


async def load_puzzle_titles(session: AsyncSession) -> list[str]:
    stmt, LatestPuzzle = _latest_versions()
    stmt = stmt.with_only_columns(LatestPuzzle.title).order_by(LatestPuzzle.created_at)
    return (await session.execute(stmt)).scalars().all()


def _puzzle_to_board(puzzle: Puzzle) -> Board:
    return Board(
        LocationSet(_int_to_loc(loc) for loc in puzzle.background),
        tuple(
            Constraint(LocationSet(_int_to_loc(loc) for loc in con['tiles']), con['type'], con['value'])
            for con in puzzle.constraints
        ),
        [_int_to_domino(dom) for dom in puzzle.dominoes],
    )


_ORIENTATION_INTS = {Orientation.EAST: 0, Orientation.SOUTH: 1, Orientation.WEST: 2, Orientation.NORTH: 3}

_INT_ORIENTATIONS = {value: key for key, value in _ORIENTATION_INTS.items()}


def _placement_to_int(placement: Placement) -> int:
    loc = _loc_to_int(placement.pos.loc)  # 14 bits
    orientation = _ORIENTATION_INTS[placement.pos.dir]  # 2 bits
    domino = _domino_to_int(placement.domino)  # 8 bits
    return (loc) | (orientation << 14) | (domino << 16)


def _int_to_placement(pl: int) -> Placement:
    loc = _int_to_loc(pl & 0x3FFF)
    orientation = _INT_ORIENTATIONS[(pl >> 14) & 0x3]
    domino = _int_to_domino(pl >> 16)
    return Placement(domino, Position(loc, orientation))


async def upsert_board(session: AsyncSession, title: str, version: int, board: Board) -> tuple[int, bool]:
    """Inserts the board and returns True if it is new."""
    if not len(board.placements):
        raise ValueError('Board has no placements')
    placements = [_placement_to_int(placement) for placement in board.placements]
    placements.sort()
    hash_ = hashlib.sha256(struct.pack(f'{len(placements)}i', *placements)).hexdigest()
    for state in (
        (
            await session.execute(
                select(PuzzleState).where(
                    PuzzleState.puzzle_title == title,
                    PuzzleState.puzzle_version == version,
                    PuzzleState.placements_hash == hash_,
                )
            )
        )
        .scalars()
        .all()
    ):
        if state.placements == placements:
            return state.id, True
    new_state = PuzzleState()
    session.add(new_state)
    await session.commit()
    return new_state.id, False
