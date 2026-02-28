import logging
from typing import Optional

import cachetools
from fastapi import FastAPI, HTTPException

from pips.app.models import PuzzleModel
from pips.model import Board
from pips.solve.shell import Shell, SolverJobModel, SolverResultModel

logging.basicConfig(level=logging.INFO)

app = FastAPI()
logger = logging.getLogger('app')
shell = Shell('samples', {'template'})


@cachetools.cached(cache=cachetools.TTLCache(maxsize=10, ttl=60))
def cache() -> dict[str, Board]:
    return shell.get_boards()


@app.get('/')
async def root():
    return {'message': 'Hello World'}


@app.get('/api/puzzleNames')
async def read_item() -> list[str]:
    return list(cache().keys())


@app.get('/api/puzzles/{puzzle_name}')
async def get_puzzle(puzzle_name) -> PuzzleModel:
    board = cache().get(puzzle_name)
    if not board:
        raise HTTPException(404, 'Puzzle not found')
    return board


@app.get('/api/puzzles/{puzzle_name}/solverJob')
async def get_solver_job(puzzle_name) -> SolverJobModel | None:
    return shell.get_solver_job(puzzle_name)


@app.post('/api/puzzles/{puzzle_name}/solverJob')
async def start_solver_job(puzzle_name) -> SolverJobModel:
    return shell.launch_solver(puzzle_name)


@app.get('/api/puzzles/{puzzle_name}/solverResult')
async def get_solver_result(puzzle_name) -> SolverResultModel | None:
    return shell.get_solver_result(puzzle_name)
