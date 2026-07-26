import collections
import itertools
import math
import typing

from pips.model import (
    MAX_PIPS,
    Board,
    BoardStatus,
    Constraint,
    ConstraintType,
    Location,
    PipCount,
    Placement,
    Position,
)


class SolverCaches:
    def add_node(self, parent: Node, placement: Placement) -> tuple[Node | BoardStatus, bool]:
        raise NotImplementedError()

    async def add_node_async(self, parent: Node, placement: Placement) -> tuple[Node | BoardStatus, bool]:
        raise NotImplementedError()

    def get_constraint(self, loc: Location) -> Constraint | None:
        raise NotImplementedError()

    def get_valid_positions(self, board: Board) -> list[Position]:
        raise NotImplementedError()


class SolverDebug:
    def add_message(self, node: Node, message: str):
        pass

    def is_debugging(self):
        return False


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

    def _compute_placements(self, solver: SolverCaches, debug: SolverDebug) -> list[Placement]:
        if not self.board.empty_locations:
            self._status = self._board.test_finished().status
            return []

        # check that each constraint is potentially solvable
        available_pips: list[PipCount] = []
        for domino in self._board.remaining_dominoes:
            for pips in domino.pips:
                available_pips.append(pips)

        for constraint in self._board.constraints:
            if not self._can_meet(constraint, available_pips):
                debug.add_message(self, f'Aborted expansion because constraint {constraint} is not solvable')
                self._status = 'lost'
                return []

        # to_place = self._expand_using_brute_force(solver, debug)
        _, to_place = self._expand_using_ranked_locations(solver, debug)
        return to_place

    def _finish_expand(self, placed: list[tuple[Placement, Node, bool]], debug: SolverDebug):
        child_count = 0
        for placement, _child, existed in placed:
            if existed:
                debug.add_message(
                    self, f'Skipped placement {placement} since it resulted in a board that was already visited'
                )
                continue
            child_count += 1

        if not self._status:
            debug.add_message(self, f'Found {len(placed)} placements and added {child_count} unique children')

            # set closure status
            self._status = 'incomplete'

    def expand(self, solver: SolverCaches, debug: SolverDebug):
        to_place = self._compute_placements(solver, debug)
        new_nodes = [(placement, *solver.add_node(self, placement)) for placement in to_place]
        self._finish_expand(new_nodes, debug)

    async def expand_async(self, solver: SolverCaches, debug: SolverDebug):
        to_place = self._compute_placements(solver, debug)
        new_nodes = [(placement, *(await solver.add_node_async(self, placement))) for placement in to_place]
        self._finish_expand(new_nodes, debug)

    def _expand_using_brute_force(self, solver: SolverCaches, debug: SolverDebug) -> list[Placement]:
        # find the valid location and orientation pairs
        valid_positions = solver.get_valid_positions(self._board)
        to_place: list[Placement] = []
        for domino in self._board.remaining_dominoes:
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
                return []

        return to_place

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

                    def check_sum(test):
                        return test == value
                case ConstraintType.LESS:

                    def check_sum(test):
                        return test < value
                case ConstraintType.GREATER:

                    def check_sum(test):
                        return test > value
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
        if slots[1].loc not in self._board.empty_locations:
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

    @staticmethod
    def _rank_constraint(constraint: Constraint) -> float:
        """Rank constraints"""
        if constraint.type.is_sum:
            avg_pip_count = constraint.value / len(constraint.tiles)
            return 1 + (3 - math.fabs(avg_pip_count - 3)) ** 2
        return len(constraint.tiles)

    @staticmethod
    def _rank_position(position: Position, solver: SolverCaches):
        """Rank positions by constraints they touch"""
        constraints = [
            solver.get_constraint(position.loc),
            solver.get_constraint(position.loc + position.dir.offset),
        ]
        rank_constraint = Node._rank_constraint
        if constraints[0]:
            rank = rank_constraint(constraints[0])
            if constraints[0] == constraints[1] or not constraints[1]:
                return rank
            else:
                return (rank + rank_constraint(constraints[1])) / 2
        elif constraints[1]:
            return rank_constraint(constraints[1])
        return 30

    def _rank_available_locations(
        self, solver: SolverCaches, debug: SolverDebug
    ) -> list[tuple[Location, list[Position]]]:
        position_ranks = {
            position: self._rank_position(position, solver) for position in solver.get_valid_positions(self.board)
        }
        location_positions: dict[Location, list[Position]] = collections.defaultdict(list)
        for position in position_ranks.keys():
            location_positions[position.loc].append(position)
            location_positions[position.loc + position.dir.offset].append(position)

        location_ranks = sorted(
            (sum(position_ranks[position] for position in positions), location, positions)
            for location, positions in location_positions.items()
        )
        if debug.is_debugging():
            debug.add_message(self, 'Location Ranks')
            for rank, location, positions in location_ranks:
                debug.add_message(self, f'  {rank}: {location}: {[str(pos) for pos in positions]}')
        return [(location, positions) for _, location, positions in location_ranks]

    def _expand_using_ranked_locations(
        self, solver: SolverCaches, debug: SolverDebug
    ) -> tuple[Location, list[Placement]]:
        remaining = self._board._remaining_dominoes
        placement_cache: dict[Placement, str] = {}
        best_location: Location | None = None
        best_placements: list[Placement] | None = None
        for location, positions in self._rank_available_locations(solver, debug):
            valid_placements = []
            for placement in (
                Placement(domino, position) for domino, position in itertools.product(remaining, positions)
            ):
                if not (expand_result := placement_cache.get(placement)):
                    violation = self._expand_at(solver, placement)
                    placement_cache[placement] = expand_result = violation if violation else 'ok'
                if expand_result == 'ok':
                    valid_placements.append(placement)
                    if best_placements and len(valid_placements) >= len(best_placements):
                        debug.add_message(self, f'Location {location} defeated after exceeding {len(best_placements)}')
                        break
            if len(valid_placements) == 0:
                debug.add_message(self, f'Aborted expansion because location {location} has no valid placements')
                self._status = 'lost'
                return None, []

            if not best_placements or len(valid_placements) < len(best_placements):
                debug.add_message(
                    self, f'New current winner: location {location} with {len(valid_placements)} placements'
                )
                best_location = location
                best_placements = valid_placements

        if not best_location:
            debug.add_message(self, f'No best location found for expansion')
            return None, []

        return best_location, best_placements

        # positions = sorted(solver.get_valid_positions(self.board), key=rank_position)
        # remaining = self._board._remaining_dominoes
        # best_domino_placements = (None, [])
        # for position in positions:
        #     print(f'{position}')
