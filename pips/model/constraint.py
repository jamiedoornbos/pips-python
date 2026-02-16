import enum
import typing
from dataclasses import dataclass

from .locationset import LocationSet


@dataclass
class _ConstraintType:
    name: str
    is_sum: bool


class ConstraintType(enum.Enum):
    EQUAL = _ConstraintType("eq", is_sum=True)
    GREATER = _ConstraintType("gt", is_sum=True)
    LESS = _ConstraintType("lt", is_sum=True)
    MATCH = _ConstraintType("match", is_sum=False)
    NOT_MATCH = _ConstraintType("notMatch", is_sum=False)

    @property
    def is_sum(self):
        return self.value.is_sum

    @staticmethod
    def from_name(name: str) -> "ConstraintType":
        for type in ConstraintType:
            if type.value.name == name:
                return type
        raise ValueError(f"Type {name} is not a valid constraint type")


class Constraint(typing.NamedTuple):
    tiles: LocationSet
    type: ConstraintType
    value: int | None
