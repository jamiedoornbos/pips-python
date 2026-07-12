"""Run benchmarks for a given puzzle"""

import asyncio
import os
import threading
import time
import typing
from urllib.parse import urlparse

import typer

from pips.app import main
from pips.db.engine import async_session
from pips.db.puzzles import CatalogShell
from pips.db.solvers import SolverShell

app = typer.Typer()


T = typing.TypeVar('T', bound=tuple)


class Bench:
    def __init__(self):
        self.times = [time.time_ns()]

    def mark(self):
        self.times.append(time.time_ns())

    def result(self, type: T = tuple) -> T[float, ...]:
        return type(*(self.times[idx] - self.times[idx - 1] for idx in range(1, len(self.times))))


class Result(typing.NamedTuple):
    load_time: float
    init_time: float
    run_time: float


def run_file_based(puzzle_name: str) -> Result:
    bench = Bench()
    puzzle = main.shell.puzzle(puzzle_name)
    bench.mark()
    puzzle.init_background_solve()
    bench.mark()
    puzzle.background_solve(threading.Event())
    bench.mark()
    return bench.result(Result)


async def run_db_based(puzzle_name: str) -> Result:
    bench = Bench()
    async with async_session() as session:
        catalog = CatalogShell(session)
        version = await catalog.puzzle(puzzle_name).latest_version()
        bench.mark()
        shell = SolverShell(version)
        await shell.init_solver()
        bench.mark()
        await shell.solve(asyncio.Event())
        bench.mark()
    return bench.result(Result)


@app.command('file')
def benchmark_file(puzzle_name: str):
    # prepare the bench by deleting all nodes
    print(f'Resetting {puzzle_name}')
    main.shell.puzzle(puzzle_name).reset_background_solver()
    result = run_file_based(puzzle_name)
    print(f'FS benchmark for {puzzle_name}: {result}')


@app.command('db')
def benchmark_db(puzzle_name: str):
    async def run():
        async with async_session() as session:
            catalog = CatalogShell(session)
            version = await catalog.puzzle(puzzle_name).latest_version()
            await SolverShell(version).reset_solver()
            await session.commit()
        return await run_db_based(puzzle_name)

    result = asyncio.run(run())
    host = urlparse(os.environ['DATABASE_URL']).hostname
    print(f'Database benchmark for {puzzle_name} ({host}): {result}')


if __name__ == '__main__':
    app()
