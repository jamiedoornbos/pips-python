import logging
import threading
from contextlib import asynccontextmanager

import cachetools
from fastapi import BackgroundTasks, FastAPI, HTTPException

from pips.app.models import PuzzleModel
from pips.model import Board
from pips.solve.shell import BackgroundSolveModel, ResultStatus, Shell, SolverNodeModel, SolverResultModel

logging.basicConfig(level=logging.INFO)

shutdown_event = threading.Event()


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
async def get_puzzle_names() -> list[tuple[str, ResultStatus]]:
    return [(name, board[1]) for name, board in cache().items()]


@app.get('/api/puzzles/{puzzle_name}')
async def get_puzzle(puzzle_name) -> PuzzleModel:
    board, status = cache().get(puzzle_name)
    if not board:
        raise HTTPException(404, 'Puzzle not found')
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
async def get_solver_result(puzzle_name) -> SolverResultModel | None:
    return shell.puzzle(puzzle_name).get_solver_result()


@app.get('/api/puzzles/{puzzle_name}/solverNodes/ids')
async def get_solver_node_ids(puzzle_name) -> list[str]:
    return shell.puzzle(puzzle_name).get_solver_node_ids()


@app.get('/api/puzzles/{puzzle_name}/solverNodes/solutions')
async def get_won_node_ids(puzzle_name) -> list[str]:
    return shell.puzzle(puzzle_name).get_solver_node_ids('won')


@app.get('/api/puzzles/{puzzle_name}/solverNodes/{node_id:path}')
async def get_solver_node(puzzle_name, node_id) -> SolverNodeModel:
    return shell.puzzle(puzzle_name).get_solver_node(node_id)
