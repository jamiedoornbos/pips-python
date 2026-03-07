import logging

import cachetools
from fastapi import FastAPI, HTTPException

from pips.app.models import PuzzleModel
from pips.model import Board
from pips.solve.shell import ResultStatus, Shell, SolverJobModel, SolverNodeModel, SolverResultModel

logging.basicConfig(level=logging.INFO)

app = FastAPI()
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
async def get_solver_job(puzzle_name) -> SolverJobModel | None:
    return shell.puzzle(puzzle_name).get_solver_job()


@app.post('/api/puzzles/{puzzle_name}/solverJob')
async def start_solver_job(puzzle_name) -> SolverJobModel:
    return shell.puzzle(puzzle_name).launch_solver()


@app.get('/api/puzzles/{puzzle_name}/solverResult')
async def get_solver_result(puzzle_name) -> SolverResultModel | None:
    return shell.puzzle(puzzle_name).get_solver_result()


@app.get('/api/puzzles/{puzzle_name}/solverNodes/ids')
async def get_solver_node_ids(puzzle_name) -> list[str]:
    return shell.puzzle(puzzle_name).get_solver_node_ids()


@app.get('/api/puzzles/{puzzle_name}/solverNodes/{node_id:path}')
async def get_solver_node(puzzle_name, node_id) -> SolverNodeModel:
    return shell.puzzle(puzzle_name).get_solver_node(node_id)


@app.post('/api/puzzles/{puzzle_name}/runOneStep')
async def run_one_step(puzzle_name) -> SolverNodeModel | None:
    return shell.puzzle(puzzle_name).run_one_step()
