import enum
import typing
from dataclasses import dataclass

from .domino import PipCount
from .location import Location
from .locationset import LocationSet


class BoardState:
    def get_pips(self, location: Location) -> PipCount | None:
        raise NotImplementedError()


@dataclass
class _ConstraintType:
    name: str
    is_sum: bool


class ConstraintType(enum.Enum):
    EQUAL = _ConstraintType('eq', is_sum=True)
    GREATER = _ConstraintType('gt', is_sum=True)
    LESS = _ConstraintType('lt', is_sum=True)
    MATCH = _ConstraintType('match', is_sum=False)
    NOT_MATCH = _ConstraintType('notMatch', is_sum=False)

    @property
    def is_sum(self):
        return self.value.is_sum

    @staticmethod
    def from_name(name: str) -> 'ConstraintType':
        for type in ConstraintType:
            if type.value.name == name:
                return type
        raise ValueError(f'Type {name} is not a valid constraint type')


class Constraint(typing.NamedTuple):
    tiles: LocationSet
    type: ConstraintType
    value: int | None

    def is_satisfied(self, board: BoardState) -> bool:
        values = []
        for location in self.tiles:
            pips = board.get_pips(location)
            if pips is None:
                return False
            values.append(pips)

        if self.type.is_sum:
            test_sum = sum(values)
            match self.type:
                case ConstraintType.EQUAL:
                    return test_sum == self.value
                case ConstraintType.GREATER:
                    return test_sum > self.value
                case ConstraintType.LESS:
                    return test_sum < self.value
        else:
            unique = set(values)
            match self.type:
                case ConstraintType.MATCH:
                    return len(unique) == 1
                case ConstraintType.NOT_MATCH:
                    return len(unique) == len(values)

        raise ValueError(f'Abnormal constrtaint state {self}')
