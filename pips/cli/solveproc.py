import gc

import click

from pips.cli.solve import print_solutions
from pips.data.boardfromstr import read_board_from_string
from pips.solve.solver import Solver


@click.command()
@click.argument('filename')
def main(filename: str):
    with open(filename, encoding='utf8') as fp:
        board = read_board_from_string(fp.read())

    print(f'Loaded board: {filename}')
    solver = Solver(board)
    open_nodes = 0
    zdepth = 0
    operations = 0
    while True:
        if solver.expand_next() is None:
            break
        operations += 1
        depth = len(solver._open)

        if depth != zdepth and depth > 1 and len(solver._open[depth - 2]) == 0:
            open_nodes = len(solver._open[depth - 1])
            zdepth = depth
            print(f'Completed depth {depth - 2}; {open_nodes:,} open nodes')

        if operations % 100_000 == 0:
            opened = '; '.join(
                f'depth {depth}: {len(nodes):,}' for depth, nodes in enumerate(solver._open) if len(nodes) > 0
            )
            print(f'Progress {opened}')
            gc.collect()

    print_solutions(solver)


if __name__ == '__main__':
    main()
