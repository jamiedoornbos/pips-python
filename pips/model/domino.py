import typing

PipCount = typing.Literal[0, 1, 2, 3, 4, 5, 6]


class Domino(typing.NamedTuple):
    left_pips: PipCount
    right_pips: PipCount

    @property
    def pips(self) -> iter[PipCount]:
        yield self.left_pips
        yield self.right_pips

    def __str__(self):
        return f"{self.left_pips}{self.right_pips}"

    def __repr__(self):
        return f"{self.left_pips}{self.right_pips}"
