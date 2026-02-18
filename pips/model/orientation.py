import enum
from dataclasses import dataclass

from .vector import Vector


@dataclass
class _Orientation:
    name: str
    offset: Vector


class Orientation(enum.Enum):
    NORTH = _Orientation('north', Vector(0, -1))
    EAST = _Orientation('east', Vector(1, 0))
    SOUTH = _Orientation('south', Vector(0, 1))
    WEST = _Orientation('west', Vector(-1, 0))

    @property
    def offset(self):
        return self.value.offset

    def __str__(self):
        return self.value.name
