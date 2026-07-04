import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

import cachetools
import sqlalchemy as sa
from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException

from pips.app.models import PuzzleModel
from pips.db.puzzles import CatalogShell
from pips.db.session import AsyncSession, get_session
from pips.db.solvers import SolverShell
from pips.model import Board
from pips.solve.shell import BackgroundSolveModel, ResultStatus, Shell, SolverNodeModel, SolverResultModel

logging.basicConfig(level=logging.INFO)

shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    shutdown_event.set()


app = FastAPI(lifespan=lifespan)
logger = logging.getLogger('app')
shell = Shell('samples', 'local-data/puzzles', {'template'})


@cachetools.cached(cache=cachetools.TTLCache(maxsize=10, ttl=60))
def cache() -> dict[str, tuple[Board, ResultStatus]]:
    return shell.get_boards()


@app.get('/')
async def root():
    return {'message': 'Hello World'}


@app.get('/api/puzzleNames')
async def get_puzzle_names(catalog: CatalogShell = Depends(CatalogShell)) -> list[tuple[str, ResultStatus]]:
    titles = await catalog.load_puzzle_titles()
    return [(title, 'not_run') for title in titles]


@app.get('/api/puzzles/{puzzle_name}')
async def get_puzzle(puzzle_name, catalog: CatalogShell = Depends(CatalogShell)) -> PuzzleModel:
    if not (board := await catalog.puzzle(puzzle_name).load()):
        raise HTTPException(404, 'Puzzle not found')
    return board


@app.post('/api/puzzles/{puzzle_name}')
async def update_puzzle(
    puzzle_name, puzzle: Annotated[PuzzleModel, Body(embed=True)], catalog: CatalogShell = Depends(CatalogShell)
) -> PuzzleModel:
    shell = catalog.puzzle(puzzle_name)
    if not await shell.load():
        raise HTTPException(404, 'Puzzle not found')
    board, _version = await shell.update(puzzle.to_board())
    return board


@app.get('/api/puzzles/{puzzle_name}/solverJob')
async def get_solver_job(puzzle_name) -> BackgroundSolveModel | None:
    return shell.puzzle(puzzle_name).get_solver_job()


@app.post('/api/puzzles/{puzzle_name}/solverJob')
async def start_solver_job(puzzle_name, tasks: BackgroundTasks) -> BackgroundSolveModel:
    puzzle = shell.puzzle(puzzle_name)
    job = puzzle.init_background_solve()

    def run():
        puzzle.background_solve(shutdown_event)

    tasks.add_task(run)
    return job


@app.get('/api/puzzles/{puzzle_name}/solverResult')
async def get_solver_result(puzzle_name, catalog: CatalogShell = Depends(CatalogShell)) -> SolverResultModel | None:
    solver = SolverShell(await catalog.puzzle(puzzle_name).latest_version())
    return await solver.get_result()


@app.get('/api/puzzles/{puzzle_name}/solverNodes/ids')
async def get_solver_node_ids(puzzle_name) -> list[str]:
    return shell.puzzle(puzzle_name).get_solver_node_ids()


@app.get('/api/puzzles/{puzzle_name}/solverNodes/solutions')
async def get_won_node_ids(puzzle_name) -> list[str]:
    return shell.puzzle(puzzle_name).get_solver_node_ids('won')


@app.get('/api/puzzles/{puzzle_name}/solverNodes/{node_id:path}')
async def get_solver_node(puzzle_name, node_id) -> SolverNodeModel:
    return shell.puzzle(puzzle_name).get_solver_node(node_id)


@app.get('/api/test-select')
async def test_select(session: AsyncSession = Depends(get_session)):
    result = list(await session.execute(sa.select(sa.literal(1))))
    return {'result': result[0][0]}


@app.post('/api/puzzles')
async def create_puzzle(
    title: Annotated[str, Body()], puzzle: PuzzleModel, catalog: CatalogShell = Depends(CatalogShell)
) -> PuzzleModel:
    return await catalog.puzzle(title).save_new(puzzle.to_board())
