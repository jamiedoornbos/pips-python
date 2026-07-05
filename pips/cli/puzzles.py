import asyncio
import pathlib

import typer

from pips.app import main
from pips.data.boardtostr import board_to_str
from pips.db.engine import async_session
from pips.db.puzzles import CatalogShell
from pips.db.solvers import SolverShell

app = typer.Typer()


def run_async(coro):
    return asyncio.run(coro)


@app.command()
def list_titles():
    """List distinct puzzle titles stored in the database."""

    async def _run():
        async with async_session() as session:
            catalog = CatalogShell(session)
            titles = await catalog.load_puzzle_titles()
            if not titles:
                print('No puzzles found')
                return
            for title in titles:
                print(title)

    run_async(_run())


@app.command()
def import_samples(force: bool = False):
    """Import samples/ puzzles into the database."""

    async def _run():
        async with async_session() as session:
            samples = main.shell.get_boards()
            catalog = CatalogShell(session)
            existing_titles = set(await catalog.load_puzzle_titles())
            for title, (board, _status) in samples.items():
                if (exists := title in existing_titles) and not force:
                    print(f'Skipping {title} already in db')
                    continue
                puzzle = catalog.puzzle(title)
                if exists:
                    _, version = puzzle.update(board)
                    print(f'Updated puzzle {title} to version {version}')
                else:
                    await puzzle.save_new(board)
                    print(f'Saved new puzzle {title}')

    run_async(_run())


@app.command()
def export_samples(force: bool = False):
    """Export puzzles from the database to samples/."""

    async def _run():
        async with async_session() as session:
            catalog = CatalogShell(session)
            titles = set(await catalog.load_puzzle_titles())
            existing_titles = set(main.shell.get_boards().keys())
            for title in titles:
                if (exists := title in existing_titles) and not force:
                    print(f'Skipping {title} already in samples/')
                    continue
                board = await catalog.puzzle(title).load()
                path = pathlib.Path(main.shell.samples_dir, f'{title}.txt')
                path.write_text(board_to_str(board, title))
                if exists:
                    print(f'Overwrote file {path}')
                else:
                    print(f'Saved new file {title}')

    run_async(_run())


@app.command()
def list_versions(title: str):
    """Shows versions of a puzzle title."""

    async def run():
        async with async_session() as session:
            puzzle = CatalogShell(session).puzzle(title)
            print('Versions:')
            for created_at, version in await puzzle.versions():
                print(f'   {version}: {created_at}')

    run_async(run())


@app.command()
def test_solve(title: str, version: int | None = None):
    # TODO: handle keyboard interrups correctly using tasks and shutdown event
    async def run():
        async with async_session() as session:
            puzzle = CatalogShell(session).puzzle(title)
            solver = SolverShell(puzzle.version(version if version is not None else (await puzzle.versions())[-1][1]))
            await solver.init_solver()
            await solver.solve(asyncio.Event())
            # print(await solver.load())

    run_async(run())


if __name__ == '__main__':
    app()
