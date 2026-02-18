import collections
import itertools
import typing

from pips.model import (
    MAX_PIPS,
    Board,
    BoardStatus,
    Constraint,
    ConstraintType,
    Location,
    Orientation,
    PipCount,
    Placement,
    Position,
)


class SolverCaches:
    def add_node(self, parent: Node, placement: Placement) -> tuple[Node | BoardStatus, bool]:
        raise NotImplementedError()

    def get_constraint(self, loc: Location) -> Constraint | None:
        raise NotImplementedError()

    def get_valid_positions(self, board: Board) -> list[Position]:
        raise NotImplementedError()


class SolverDebug:
    def add_message(self, node: Node, message: str):
        pass


class Node:
    def __init__(self, board: Board):
        self._board = board
        self._status: BoardStatus | None = None

    @property
    def board(self) -> Board:
        return self._board

    @property
    def open(self) -> bool:
        return self._status is None

    @property
    def solved(self) -> bool:
        return self._status == 'won'

    @property
    def status(self) -> BoardStatus | None:
        return self._status

    def expand(self, solver: SolverCaches, debug: SolverDebug):
        # check that each constraint is potentially solvable
        remaining = self._board._remaining_dominoes
        available_pips: list[PipCount] = []
        for domino in remaining:
            for pips in domino.pips:
                available_pips.append(pips)

        for constraint in self._board.constraints:
            if not self._can_meet(constraint, available_pips):
                debug.add_message(self, f'Aborted expansion because constraint {constraint} is not solvable')
                self._status = 'lost'
                return

        # find the valid location and orientation pairs
        valid_positions = solver.get_valid_positions(self._board)
        to_place: list[Placement] = []
        for domino in remaining:
            valid_count = 0
            for position in valid_positions:
                test_placement = Placement(domino, position)
                if rejection := self._expand_at(solver, test_placement):
                    debug.add_message(self, rejection)
                    continue
                to_place.append(test_placement)
                valid_count += 1
            if valid_count == 0:
                debug.add_message(self, f'Aborted expansion because {domino} has no valid placements')
                self._status = 'lost'
                return

        # spawn the children
        child_count = 0
        for placement in to_place:
            _child_node, existed = solver.add_node(self, placement)
            if existed:
                debug.add_message(
                    self, f'Skipped placement {placement} since it resulted in a board that was already visited'
                )
                continue
            child_count += 1

        debug.add_message(self, f'Found {len(to_place)} placements and added {child_count} unique children')

        # set closure status
        self._status = self._board.test_finished().status if len(remaining) == 0 else 'incomplete'

    def _can_meet(self, constraint: Constraint, available_pips: list[PipCount]):
        all_slots = [self._board.get_pips(location) for location in constraint.tiles]
        filled_slots = [pips for pips in all_slots if pips is not None]
        empty_count = len(all_slots) - len(filled_slots)

        if empty_count == 0:
            return True

        if constraint.type.is_sum:
            current_sum = sum(filled_slots)
            value = constraint.value
            match constraint.type:
                case ConstraintType.EQUAL:
                    check_sum = lambda test: test == value
                case ConstraintType.LESS:
                    check_sum = lambda test: test < value
                case ConstraintType.GREATER:
                    check_sum = lambda test: test > value
                case _:
                    raise ValueError(f'Invalid sum constraint: {constraint}')
            for combo in itertools.combinations(available_pips, r=empty_count):
                if check_sum(current_sum + sum(combo)):
                    return True
            return False

        match constraint.type:
            case ConstraintType.MATCH:
                if len(filled_slots):
                    count = sum(1 for pips in available_pips if pips == filled_slots[0])
                    return count >= empty_count
                else:
                    return any(count >= empty_count for count in collections.Counter(available_pips).values())
            case ConstraintType.NOT_MATCH:
                return len(set(available_pips + filled_slots)) >= len(all_slots)
            case _:
                raise ValueError(f'Invalid match constraint: {constraint}')

    class _Slot(typing.NamedTuple):
        loc: Location
        pips: PipCount
        constraint: Constraint | None

    def _expand_at(self, solver: SolverCaches, placement: Placement):
        domino, (loc, dir) = placement
        slots = tuple(
            Node._Slot(loc, pips, solver.get_constraint(loc))
            for loc, pips in ((loc, domino.left_pips), (loc + dir.offset, domino.right_pips))
        )

        violation = None

        # check out of bounds (only the right side)
        if slots[1][0] not in self._board.empty_locations:
            violation = 'it is off the board'
        else:
            if slots[0].constraint and slots[0].constraint == slots[1].constraint:
                # both slots in same constraint
                violation = self._get_violation(slots[0].constraint, domino.left_pips, domino.right_pips)
            else:
                for slot in slots:
                    if slot.constraint:
                        violation = self._get_violation(slot.constraint, slot.pips)
                        if violation:
                            violation = f'it violates the constraint {slot.constraint}: {violation}'
                            break

        return f'Rejected placement of {placement} because {violation}' if violation else None

    def _get_violation(self, constraint: Constraint, *pips: PipCount) -> str | None:
        all_slots = [self._board.get_pips(location) for location in constraint.tiles]
        filled_slots = [pips for pips in all_slots if pips is not None]
        empty_count = len(all_slots) - len(filled_slots) - len(pips)
        if constraint.type.is_sum:
            new_sum = sum(filled_slots) + sum(pips)
            value = constraint.value
            match constraint.type:
                case ConstraintType.EQUAL:
                    if new_sum > value:
                        return 'sum exceeds eq value'
                    if empty_count == 0 and new_sum != value:
                        return 'final sum is not eq value'
                    if new_sum + empty_count * MAX_PIPS < value:
                        return 'eq value is unattainable'
                case ConstraintType.GREATER:
                    if empty_count == 0 and new_sum <= value:
                        return 'sum is not gt value'
                    if new_sum + empty_count * MAX_PIPS <= value:
                        return 'gt value is unattainable'
                case ConstraintType.LESS:
                    if new_sum >= value:
                        return 'sum is more than lt value'
        else:
            new_pips = [*filled_slots, *pips]
            uniq = set(new_pips)
            match constraint.type:
                case ConstraintType.MATCH:
                    if len(uniq) != 1:
                        return 'unmatching pips added'
                case ConstraintType.NOT_MATCH:
                    if len(uniq) < len(new_pips):
                        return 'matching pips added'

        return None
