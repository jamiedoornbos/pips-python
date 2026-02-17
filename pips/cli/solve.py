import click

from pips.data.boardfromstr import read_board_from_string
from pips.model import Board
from pips.solve.node import Node
from pips.solve.solver import Solver


def summary(solver: Solver) -> str:
    opened = '; '.join(f'{depth}: {count:,}' for depth, count in enumerate(solver.open_count_by_depth()) if count > 0)
    return f'Tree ({opened}) | Solutions ({len(solver.solutions)})'


def print_placements(title: str, board: Board):
    print(title)
    for placement in board.placements:
        print(f'  {placement}')


@click.command()
@click.argument('filename')
def main(filename: str):
    with open(filename, encoding='utf8') as fp:
        board = read_board_from_string(fp.read())

    print(f'Loaded board: {board}')
    solver = Solver(board)
    print('Expanding to find solutions')
    last_message = ''
    while True:
        message = summary(solver)
        print(f'\r{message}', end='')
        if len(last_message) > len(message):
            print(' ' * (len(last_message) - len(message)), end='')
        last_message = message

        node = solver.expand_next()
        if node is None:
            print()
            break

    if solver.solutions:
        for index, solution in enumerate(solver.solutions, 1):
            print_placements(f'Solution #{index}', solution.board)
    else:
        print('No solutions found!')


if __name__ == '__main__':
    main()
