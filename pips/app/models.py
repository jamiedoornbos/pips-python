from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_serializer

from pips.model import Board, Constraint, ConstraintType, Domino, Location, LocationSet, Orientation


class ConstraintModel(BaseModel):
    tiles: list[Location]
    type: ConstraintType
    value: int | None

    @field_serializer('type')
    def serialize_type(self, type: ConstraintType, _info):
        return type.value.name


class PuzzleModel(BaseModel):
    background: list[Location]
    constraints: list[ConstraintModel]
    all_dominoes: Annotated[list[Domino], Field(serialization_alias='dominoes')]

    def to_board(self) -> Board:
        return Board(
            background=LocationSet(self.background),
            constraints=tuple(
                Constraint(tiles=LocationSet(c.tiles), type=c.type, value=c.value) for c in self.constraints
            ),
            dominoes=tuple(self.all_dominoes),
        )


class PlacementModel(BaseModel):
    domino: Domino
    loc: Location
    dir: Annotated[Orientation, BeforeValidator(Orientation.lookup_by_name)]

    @field_serializer('dir')
    def serialize_type(self, dir: Orientation, _info):
        return dir.value.name
