from pydantic import constr

from pips.model import Board, Constraint, ConstraintType, Domino, Location, LocationSet, PipCount


def board_to_str(board: Board, title: str) -> str:
    x_min = min(loc.x for loc in board.background)
    x_max = max(loc.x for loc in board.background)
    y_min = min(loc.y for loc in board.background)
    y_max = max(loc.y for loc in board.background)
    constraint_map = {tile: constraint for constraint in board.constraints for tile in constraint.tiles}
    constraint_keys = {}
    result = ['# Title', title, '# Background']
    for y in range(y_min, y_max + 1):
        result.append('')
        for x in range(x_min, x_max + 1):
            loc = Location(x, y)
            constraint = constraint_map.get(loc)
            if not constraint:
                result[-1] += '@' if loc in board.background else '.'
            else:
                key = constraint_keys.get(constraint)
                if key is None:
                    key = next(ch for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' if ch not in constraint_keys.values())
                    constraint_keys[constraint] = key
                result[-1] += key
    result.append('# Constraints')
    for constraint in board.constraints:
        result.append(f'{constraint_keys[constraint]}: {constraint.type.value.name}')
        if constraint.type.is_sum:
            result[-1] += f' {constraint.value}'
    result.append('# Dominoes')
    result.append(' '.join(f'{domino.left_pips}{domino.right_pips}' for domino in board.all_dominoes))
    return ''.join([f'{line}\n' for line in result])
