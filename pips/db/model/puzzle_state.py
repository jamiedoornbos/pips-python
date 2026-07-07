from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKeyConstraint, Integer, LargeBinary, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from pips.db.model._base import Base
from pips.db.model.puzzle import Puzzle


class PuzzleState(Base):
    __tablename__ = 'puzzle_state'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    puzzle_title: Mapped[str] = mapped_column(Text, nullable=False)
    puzzle_version: Mapped[int] = mapped_column(Integer, nullable=False)
    placements: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    puzzle: Mapped[Puzzle] = relationship(Puzzle)
    __table_args__ = (
        ForeignKeyConstraint([puzzle_title, puzzle_version], [Puzzle.title, Puzzle.version]),
        UniqueConstraint('placements', puzzle_title, puzzle_version, placements),
    )
