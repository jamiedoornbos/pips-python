from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from pips.db.model._base import Base

if TYPE_CHECKING:
    from pips.db.model.solver import Solver


class Puzzle(Base):
    __tablename__ = 'puzzle'
    title: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    background: Mapped[list[int]] = mapped_column(ARRAY(SMALLINT))
    constraints: Mapped[list[dict]] = mapped_column(ARRAY(JSONB))
    dominoes: Mapped[list[int]] = mapped_column(ARRAY(SMALLINT))

    solver: Mapped[Optional[Solver]] = relationship('Solver', back_populates='puzzle')
