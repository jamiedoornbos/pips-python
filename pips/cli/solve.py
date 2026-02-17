import click

from pips.data.boardfromstr import read_board_from_string
from pips.solve.solver import Solver


def summary(solver: Solver) -> str:
    opened = ', '.join(f'{depth}: {(count,)}' for depth, count in enumerate(solver.open_count_by_depth()) if count > 0)
    return f'Tree ({opened}) | Solutions ({len(solver.solutions)})'


@click.command()
@click.argument('filename')
def main(filename: str):
    with open(filename, encoding='utf8') as fp:
        board = read_board_from_string(fp.read())

    print(f'Loaded board: {board}')
    solver = Solver(board)
    print('Expanding')
    while True:
        message = summary(solver)
        print(message)
        node = solver.expand_next()
        if node is None:
            break


if __name__ == '__main__':
    main()
