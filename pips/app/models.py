import typing
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_serializer

from pips.model import (
    Board,
    BoardStatus,
    Constraint,
    ConstraintType,
    Domino,
    Location,
    LocationSet,
    Orientation,
    Placement,
)


class ConstraintModel(BaseModel):
    tiles: list[Location]
    type: Annotated[str, BeforeValidator(lambda t: t.value.name if isinstance(t, ConstraintType) else t)]
    value: int | None


class PuzzleModel(BaseModel):
    background: list[Location]
    constraints: list[ConstraintModel]
    all_dominoes: Annotated[list[Domino], Field(serialization_alias='dominoes')]

    def to_board(self) -> Board:
        return Board(
            background=LocationSet(self.background),
            constraints=tuple(
                Constraint(tiles=LocationSet(c.tiles), type=ConstraintType.from_name(c.type), value=c.value)
                for c in self.constraints
            ),
            dominoes=tuple(self.all_dominoes),
        )

    @classmethod
    def from_board(cls, board: Board) -> PuzzleModel:
        return cls.model_validate(board, from_attributes=True)


class PlacementModel(BaseModel):
    domino: Domino
    loc: Location
    dir: Orientation

    @field_serializer('dir')
    def serialize_type(self, dir: Orientation, _info):
        return dir.value.name

    @staticmethod
    def from_placement(placement: Placement):
        return PlacementModel(domino=placement.domino, loc=placement.pos.loc, dir=placement.pos.dir)


class _SolverNodeExpansionBaseModel(BaseModel):
    id: int
    status: BoardStatus | typing.Literal['unvisited']
    has_solution: bool


class SolverNodeExpansionChildModel(_SolverNodeExpansionBaseModel):
    placement: PlacementModel


class SolverNodeExpansionModel(_SolverNodeExpansionBaseModel):
    placements: list[PlacementModel]
    children: list[SolverNodeExpansionChildModel]
