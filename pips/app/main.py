import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

import cachetools
import sqlalchemy as sa
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import NoResultFound

from pips.app.models import PlacementModel, PuzzleModel, SolverNodeExpansionChildModel, SolverNodeExpansionModel
from pips.db.puzzles import CatalogShell, bytes_to_placements
from pips.db.session import AsyncSession, get_session
from pips.db.solvers import SolverShell
from pips.model import Board
from pips.solve.shell import BackgroundSolveModel, ResultStatus, Shell, SolverNodeModel, SolverResultModel

logging.basicConfig(level=logging.INFO)

shutdown_event = asyncio.Event()
running_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    shutdown_event.set()
    if running_tasks:
        await asyncio.gather(*running_tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan)
logger = logging.getLogger('app')
shell = Shell('samples', 'local-data/puzzles', {'template'})


@cachetools.cached(cache=cachetools.TTLCache(maxsize=10, ttl=60))
def cache() -> dict[str, tuple[Board, ResultStatus]]:
    return shell.get_boards()


@app.exception_handler(NoResultFound)
async def no_result_found_handler(request: Request, exc: NoResultFound) -> JSONResponse:
    raise HTTPException(404, 'not found')


@app.get('/')
async def root():
    return {'message': 'Hello World'}


@app.get('/api/puzzleNames')
async def get_puzzle_names(catalog: CatalogShell = Depends(CatalogShell)) -> list[tuple[str, ResultStatus]]:
    titles = await catalog.load_puzzle_titles()
    return [(title, status or 'not_run') for title, status in titles]


@app.get('/api/puzzles/{puzzle_name}')
async def get_puzzle(puzzle_name, catalog: CatalogShell = Depends(CatalogShell)) -> PuzzleModel:
    if not (board := await catalog.puzzle(puzzle_name).load()):
        raise HTTPException(404, 'Puzzle not found')
    return PuzzleModel.from_board(board)


@app.post('/api/puzzles/{puzzle_name}')
async def update_puzzle(
    puzzle_name, puzzle: Annotated[PuzzleModel, Body(embed=True)], catalog: CatalogShell = Depends(CatalogShell)
) -> PuzzleModel:
    shell = catalog.puzzle(puzzle_name)
    if not await shell.load():
        raise HTTPException(404, 'Puzzle not found')
    board, _version = await shell.update(puzzle.to_board())
    return PuzzleModel.from_board(board)


async def _solver_shell(catalog: CatalogShell, puzzle_name: str) -> SolverShell:
    if (version := await catalog.puzzle(puzzle_name).latest_version()) is None:
        raise HTTPException(404, f'Puzzle {puzzle_name} not found')
    return SolverShell(version)


@app.get('/api/puzzles/{puzzle_name}/solverJob')
async def get_solver_job(
    puzzle_name: str, catalog: CatalogShell = Depends(CatalogShell)
) -> BackgroundSolveModel | None:
    shell = await _solver_shell(catalog, puzzle_name)
    solver = await shell.load()
    if not solver.lock:
        raise HTTPException(404, 'not found')

    return BackgroundSolveModel(
        thread='', iterations=solver.iterations, start_time=solver.started_at, output=[], is_running=True
    )


@app.post('/api/puzzles/{puzzle_name}/solverJob')
async def start_solver_job(puzzle_name: str, catalog: CatalogShell = Depends(CatalogShell)) -> BackgroundSolveModel:
    shell = await _solver_shell(catalog, puzzle_name)
    await shell.init_solver()
    solver = await shell.load()

    task = asyncio.create_task(shell.background_solve(shutdown_event))
    running_tasks.add(task)
    task.add_done_callback(running_tasks.discard)

    return BackgroundSolveModel(
        thread='', iterations=solver.iterations, start_time=solver.started_at, output=[], is_running=True
    )


@app.get('/api/puzzles/{puzzle_name}/solverResult')
async def get_solver_result(puzzle_name, catalog: CatalogShell = Depends(CatalogShell)) -> SolverResultModel | None:
    solver = await _solver_shell(catalog, puzzle_name)
    return await solver.get_result()


@app.get('/api/puzzles/{puzzle_name}/solverNodes/ids')
async def get_solver_node_ids(puzzle_name) -> list[str]:
    return shell.puzzle(puzzle_name).get_solver_node_ids()


@app.get('/api/puzzles/{puzzle_name}/solverNodes/solutions')
async def get_won_node_ids(puzzle_name: str, catalog: CatalogShell = Depends(CatalogShell)) -> list[str]:
    solver = await _solver_shell(catalog, puzzle_name)
    nodes = await solver.get_solutions()
    return [f'A{node.id}' for node in nodes]


@app.get('/api/puzzles/{puzzle_name}/solverNodes/{node_id}')
async def get_solver_node(
    puzzle_name: str, node_id: str, catalog: CatalogShell = Depends(CatalogShell)
) -> SolverNodeModel:
    node = await SolverShell.load_node(catalog.session, int(node_id[1:]))
    return SolverNodeModel(
        puzzle_name=node.solver.puzzle_title,
        id=f'A{node.id}',
        status=node.status.value,
        placements=list(map(PlacementModel.from_placement, bytes_to_placements(node.puzzle_state.placements))),
    )


@app.get('/api/puzzles/{puzzle_name}/solverNodes/{node_id}/expansion')
async def get_solver_node_expansion(
    puzzle_name: str, node_id: int, catalog: CatalogShell = Depends(CatalogShell)
) -> SolverNodeExpansionModel:
    solver = await _solver_shell(catalog, puzzle_name)
    expansion = await solver.node(node_id).load_expansion()
    return SolverNodeExpansionModel(
        id=expansion.id,
        status=expansion.status.value,
        has_solution=expansion.has_solution,
        placements=list(map(PlacementModel.from_placement, expansion.placements)),
        children=[
            SolverNodeExpansionChildModel(
                id=child.id,
                status=child.status.value,
                has_solution=child.has_solution,
                placement=PlacementModel.from_placement(child.placement),
            )
            for child in expansion.children
        ],
    )


@app.get('/api/test-select')
async def test_select(session: AsyncSession = Depends(get_session)):
    result = list(await session.execute(sa.select(sa.literal(1))))
    return {'result': result[0][0]}


@app.post('/api/puzzles')
async def create_puzzle(
    title: Annotated[str, Body()], puzzle: PuzzleModel, catalog: CatalogShell = Depends(CatalogShell)
) -> PuzzleModel:
    return PuzzleModel.from_board(await catalog.puzzle(title).save_new(puzzle.to_board()))
