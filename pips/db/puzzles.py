import typing

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pips.db.model.puzzle import Puzzle
from pips.model.board import Board
from pips.model.constraint import Constraint
from pips.model.domino import Domino
from pips.model.location import Location
from pips.model.locationset import LocationSet


def _loc_to_int(loc: Location) -> int:
    return (loc.y << 7) | loc.x


def _int_to_loc(xy: int) -> Location:
    return Location(xy >> 7, xy & 0x7f)


def _loc_list_to_int_list(locs: typing.Iterable[Location]) -> list[int]:
    return [_loc_to_int(loc) for loc in locs]


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
    puzzle.dominoes = [domino.left_pips * 10 + domino.right_pips for domino in board.all_dominoes]


async def save_new_puzzle(session: AsyncSession, title: str, board: Board) -> Board:
    puzzle = Puzzle(title=title, version=0)
    _board_to_puzzle(board, puzzle)
    session.add(puzzle)
    await session.commit()
    return puzzle_to_board(puzzle)


async def update_puzzle(session: AsyncSession, title: str, board: Board) -> tuple[Board, int]:
    puzzle = Puzzle(
        title=title,
        version=session.execute(select(func.max(Puzzle.version)).where(Puzzle.title == title)).scalars().one() + 1,
    )
    _board_to_puzzle(board, puzzle)
    session.add(puzzle)
    await session.commit()
    return puzzle_to_board(puzzle), puzzle.version


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


def puzzle_to_board(puzzle: Puzzle) -> Board:
    return Board(
        LocationSet(_int_to_loc(loc) for loc in puzzle.background),
        tuple(
            Constraint(LocationSet(_int_to_loc(loc) for loc in con['tiles']), con['type'], con['value'])
            for con in puzzle.constraints
        ),
        [Domino(dom // 10, dom % 10) for dom in puzzle.dominoes],
    )
