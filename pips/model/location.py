import typing

from .vector import Vector


class Location(typing.NamedTuple):
    x: int
    y: int

    def __add__(self, rhs: Vector):
        return Location(self.x + rhs.dx, self.y + rhs.dy)

    def __sub__(self, rhs: Vector):
        return Location(self.x - rhs.dx, self.y - rhs.dy)

    def __repr__(self):
        return f'({self.x}, {self.y})'
