import os
import re
import uuid

import click

import pips.app.models
from pips.model import Board, Domino, Location, Orientation, Placement, Position
from pips.solve.node import Node, SolverDebug
from pips.solve.shell import Shell, SolverNodeModel
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
@click.argument('puzzle-name')
@click.option('--placement', '-p', 'start_placements', type=create_placement, multiple=True)
@click.option('--start-node', '-s', 'start_node_id')
@click.option('--debug/--no-debug')
@click.option('--save-nodes/--no-save-nodes')
def main(puzzle_name: str, start_placements: list[Placement], debug: bool, start_node_id: str, save_nodes: bool):
    shell = Shell('samples', 'local-data/puzzles', set())
    board = shell.get_board(puzzle_name)

    print(f'Loaded board: {board}')
    if start_node_id:
        if not (start_node := shell.get_solver_node(puzzle_name, start_node_id)):
            raise click.ClickException(f'Node {start_node_id} not found')
        print(f'  Adding placements from node {start_node_id}')
        start_placements += tuple(
            Placement(Domino(*p.domino), Position(Location(*p.loc), p.dir)) for p in start_node.placements
        )

    if start_placements:
        for placement in start_placements:
            print(f'  Adding placement {placement}')
            board.place(placement)
    solver = Solver(board)
    node = Node(board)

    class Debug(SolverDebug):
        def add_message(self, _node, message):
            if debug:
                return print(message)

        def is_debugging(self):
            return debug

    location, placements = node.get_best_location_to_expand(solver, Debug())

    def to_pydantic(placement: Placement) -> pips.app.models.PlacementModel:
        return pips.app.models.PlacementModel(
            domino=placement.domino,
            loc=placement.pos.loc,
            dir=placement.pos.dir.value.name,
        )

    print(f'Best location: {location}')
    for placement in placements:
        print(f'  Placements: {placement}')
        if save_nodes:
            node_id = uuid.uuid4()
            pydantic_placements = [to_pydantic(p) for p in [*start_placements, placement]]
            os.makedirs(shell._data_file(puzzle_name, 'nodes'), exist_ok=True)
            with open(shell._data_file(puzzle_name, f'nodes/{node_id}'), 'w') as fp:
                fp.write(
                    SolverNodeModel(
                        puzzle_name=puzzle_name, id=str(node_id), placements=pydantic_placements
                    ).model_dump_json(indent=2)
                )
            print(f'    Saved node {node_id}')

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
