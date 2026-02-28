from typing import Annotated

from pydantic import BaseModel, Field, field_serializer, BeforeValidator

from pips.model import ConstraintType, Domino, Location, Orientation


class ConstraintModel(BaseModel):
    tiles: list
    type: ConstraintType
    value: int | None

    @field_serializer('type')
    def serialize_type(self, type: ConstraintType, _info):
        return type.value.name


class PuzzleModel(BaseModel):
    background: list
    constraints: list[ConstraintModel]
    all_dominoes: Annotated[list[Domino], Field(serialization_alias='dominoes')]


class PlacementModel(BaseModel):
    domino: Domino
    loc: Location
    dir: Annotated[Orientation, BeforeValidator(Orientation.lookup_by_name)]

    @field_serializer('dir')
    def serialize_type(self, dir: Orientation, _info):
        return dir.value.name
