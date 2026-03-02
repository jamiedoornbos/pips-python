import re

import click

from pips.data.boardfromstr import read_board_from_string
from pips.model import Board, Domino, Location, Orientation, Placement, Position
from pips.solve.node import Node, SolverDebug
from pips.solve.solver import Solver


def summary(solver: Solver) -> str:
    opened = '; '.join(f'{depth}: {count:,}' for depth, count in enumerate(solver.open_count_by_depth()) if count > 0)
    return f'Tree ({opened}) | Solutions ({len(solver.solutions)})'


def print_placements(title: str, board: Board):
    print(title)
    for placement in board.placements:
        print(f'  {placement}')


def print_solutions(solver: Solver):
    if solver.solutions:
        for index, solution in enumerate(solver.solutions, 1):
            print_placements(f'Solution #{index}', solution.board)
    else:
        print('No solutions found!')


PLACEMENT = re.compile(
    r'^(?P<left>\d)(?P<right>\d) at \((?P<x>\d+), (?P<y>\d+)\) facing (?P<dir>north|south|east|west)'
)


def create_placement(option: str) -> Placement:
    # 50 at (7, 3) facing south
    if not (match := PLACEMENT.match(option)):
        raise click.ClickException(f'Invalid placement: {option}')
    left, right, x, y = (int(match.group(name)) for name in ('left', 'right', 'x', 'y'))
    return Placement(
        Domino(int(left), int(right)), Position(Location(x, y), Orientation.lookup_by_name(match.group('dir')))
    )


@click.command()
@click.argument('filename')
@click.option('--placement', '-p', type=create_placement, multiple=True)
@click.option('--debug/--no-debug')
def main(filename: str, placement: list[Placement], debug: bool):
    with open(filename, encoding='utf8') as fp:
        board = read_board_from_string(fp.read())

    print(f'Loaded board: {board}')
    if placement:
        for p in placement:
            print(f'  Adding placement {p}')
            board.place(p)
    solver = Solver(board)
    node = Node(board)

    class Debug(SolverDebug):
        def add_message(self, node, message):
            if debug:
                return print(message)

        def is_debugging(self):
            return debug

    location, placements = node.get_best_location_to_expand(solver, Debug())

    print(f'Best location: {location}')
    for placement in placements:
        print(f'  Placements: {placement}')

    # valid_positions = solver.get_valid_positions(board)
    # print(f'Valid positions ({len(valid_positions)})')
    # for position in solver.get_valid_positions(board):
    #     print(f'  {position}')
    # root = solver._nodes[()]

    # print('Expanding to find solutions')
    # last_message = ''
    # while True:
    #     message = summary(solver)
    #     print(f'\r{message}', end='')
    #     if len(last_message) > len(message):
    #         print(' ' * (len(last_message) - len(message)), end='')
    #     last_message = message

    #     node = solver.expand_next()
    #     if node is None:
    #         print()
    #         break

    # print_solutions(solver)


if __name__ == '__main__':
    main()
