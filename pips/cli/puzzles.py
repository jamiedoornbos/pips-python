import asyncio

import typer

from pips.app import main
from pips.db.engine import async_session
from pips.db.puzzles import load_puzzle_titles, save_new_puzzle, update_puzzle

app = typer.Typer()


def run_async(coro):
    return asyncio.run(coro)


@app.command()
def list_titles():
    """List distinct puzzle titles stored in the database."""

    async def _run():
        async with async_session() as session:
            titles = await load_puzzle_titles(session)
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
            existing_titles = set(await load_puzzle_titles(session))
            for title, (board, _status) in samples.items():
                if (exists := title in existing_titles) and not force:
                    print(f'Skipping {title} already in db')
                    continue
                if exists:
                    _, version = await update_puzzle(session, title, board)
                    print(f'Updated puzzle {title} to version {version}')
                else:
                    await save_new_puzzle(session, title, board)
                    print(f'Saved new puzzle {title}')

    run_async(_run())


if __name__ == '__main__':
    app()
